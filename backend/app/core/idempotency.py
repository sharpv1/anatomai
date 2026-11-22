import hashlib
import json
import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from pydantic import JsonValue
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ApplicationError
from app.db.models import IdempotencyRequest


def request_fingerprint(payload: JsonValue) -> str:
    canonical = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


@dataclass(frozen=True)
class StoredResponse:
    status_code: int
    body: dict[str, JsonValue]
    resource_id: UUID | None = None

    def __post_init__(self) -> None:
        if not 200 <= self.status_code < 300:
            raise ValueError("Only successful domain responses can be cached")
        if len(json.dumps(self.body, allow_nan=False).encode()) > 1_000_000:
            raise ValueError("Response projection is too large")


@dataclass(frozen=True)
class IdempotentResult:
    response: StoredResponse
    replayed: bool


async def run_idempotent(
    session: AsyncSession,
    *,
    actor_id: UUID,
    operation: str,
    key: UUID,
    payload: JsonValue,
    action: Callable[[AsyncSession], Awaitable[StoredResponse]],
    ttl: timedelta = timedelta(days=7),
) -> IdempotentResult:
    """Caller owns one transaction for the record AND all domain writes.

    Never call external HTTP, commit(), rollback() or create background work in action.
    Only a sanitized domain projection belongs in body (no cookies, credentials or secrets).
    Payload must include method, resource IDs, relevant query and validated body;
    hashing a body alone would incorrectly replay requests to another resource.
    Permanent business UNIQUE constraints remain necessary after the TTL expires.
    """
    if not session.in_transaction():
        raise RuntimeError("run_idempotent requires an explicit caller-owned transaction")
    if not re.fullmatch(r"[a-z][a-z0-9_.:-]{0,127}", operation):
        raise ValueError("Use a stable, namespaced operation")
    if ttl <= timedelta(0):
        raise ValueError("TTL must be positive")
    digest = request_fingerprint(payload)
    now = datetime.now(UTC)
    inserted = await session.execute(
        insert(IdempotencyRequest)
        .values(
            id=uuid4(),
            actor_id=actor_id,
            operation=operation,
            key=key,
            request_hash=digest,
            outcome="processing",
            expires_at=now + ttl,
        )
        .on_conflict_do_nothing(constraint="uq_idempotency_scope_key")
        .returning(IdempotencyRequest.id)
    )
    inserted_id = inserted.scalar_one_or_none()
    record = (
        await session.execute(
            select(IdempotencyRequest)
            .where(
                IdempotencyRequest.actor_id == actor_id,
                IdempotencyRequest.operation == operation,
                IdempotencyRequest.key == key,
            )
            .with_for_update()
        )
    ).scalar_one()
    now = datetime.now(UTC)
    expired = record.expires_at <= now
    if not expired and record.request_hash != digest:
        raise ApplicationError(
            "IDEMPOTENCY_KEY_REUSED", "Ключ уже использован для другого запроса."
        )
    if not expired and record.outcome == "completed":
        assert record.response_status is not None and record.response_projection is not None
        return IdempotentResult(
            StoredResponse(record.response_status, record.response_projection, record.resource_id),
            replayed=True,
        )
    # A processing row is never committed by this service. The INSERT conflict has waited
    # for a concurrent transaction, so an existing processing row signals a caller bug.
    if not expired and inserted_id is None:
        raise ApplicationError("IDEMPOTENCY_IN_PROGRESS", "Запрос ещё обрабатывается.")
    if expired:
        record.request_hash = digest
        record.created_at = now
        record.expires_at = now + ttl
    response = await action(session)
    if not session.in_transaction():
        raise RuntimeError("Idempotent action must not end the caller's transaction")
    record.outcome = "completed"
    record.response_status = response.status_code
    record.response_projection = response.body
    record.resource_id = response.resource_id
    await session.flush()
    return IdempotentResult(response, replayed=False)
