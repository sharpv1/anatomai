import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import IntegrityError

from app.core.errors import ApplicationError
from app.core.idempotency import StoredResponse, run_idempotent
from app.db.models import IdempotencyRequest

pytestmark = pytest.mark.integration


async def test_replay_conflict_and_scoping(database):
    actor, key = uuid4(), uuid4()
    calls = 0

    async def action(session):
        nonlocal calls
        calls += 1
        return StoredResponse(201, {"result": "created"}, resource_id=key)

    async def call(actor_id=actor, operation="test.create", payload=None):
        async with database.sessions.begin() as session:
            return await run_idempotent(
                session,
                actor_id=actor_id,
                operation=operation,
                key=key,
                payload=payload or {"a": 1, "b": 2},
                action=action,
            )

    first = await call()
    replay = await call(payload={"b": 2, "a": 1})
    assert not first.replayed and replay.replayed
    assert first.response == replay.response
    assert calls == 1
    with pytest.raises(ApplicationError, match="IDEMPOTENCY_KEY_REUSED"):
        await call(payload={"a": 99})
    await call(actor_id=uuid4())
    await call(operation="test.other")
    assert calls == 3


async def test_callback_failure_rolls_back_domain_write_and_idempotency(database):
    actor, key = uuid4(), uuid4()
    async with database.engine.connect() as connection:
        await connection.execute(
            text("CREATE TEMP TABLE test_effects (value integer) ON COMMIT PRESERVE ROWS")
        )
        await connection.commit()
        from sqlalchemy.ext.asyncio import AsyncSession

        async with AsyncSession(bind=connection) as session:

            async def failure(session):
                await session.execute(text("INSERT INTO test_effects VALUES (1)"))
                raise RuntimeError("domain failed")

            with pytest.raises(RuntimeError, match="domain failed"):
                async with session.begin():
                    await run_idempotent(
                        session,
                        actor_id=actor,
                        operation="test.rollback",
                        key=key,
                        payload={},
                        action=failure,
                    )

            async def success(session):
                await session.execute(text("INSERT INTO test_effects VALUES (2)"))
                return StoredResponse(200, {"ok": True})

            async with session.begin():
                result = await run_idempotent(
                    session,
                    actor_id=actor,
                    operation="test.rollback",
                    key=key,
                    payload={},
                    action=success,
                )
                assert not result.replayed
            assert (await session.scalars(text("SELECT value FROM test_effects"))).all() == [2]


async def test_concurrent_same_key_runs_domain_action_once(database):
    actor, key = uuid4(), uuid4()
    entered, release = asyncio.Event(), asyncio.Event()
    calls = 0

    async def action(session):
        nonlocal calls
        calls += 1
        entered.set()
        await release.wait()
        return StoredResponse(200, {"ok": True})

    async def call():
        async with database.sessions.begin() as session:
            return await run_idempotent(
                session,
                actor_id=actor,
                operation="test.concurrent",
                key=key,
                payload={},
                action=action,
            )

    async with asyncio.timeout(5):
        first = asyncio.create_task(call())
        await entered.wait()
        second = asyncio.create_task(call())
        await asyncio.sleep(0.05)
        release.set()
        results = await asyncio.gather(first, second)
    assert calls == 1
    assert sorted(result.replayed for result in results) == [False, True]


async def test_expired_record_can_be_reused_but_does_not_supply_business_deduplication(database):
    actor, key = uuid4(), uuid4()

    async def action(session):
        return StoredResponse(200, {"ok": True})

    async def call(payload):
        async with database.sessions.begin() as session:
            return await run_idempotent(
                session,
                actor_id=actor,
                operation="test.ttl",
                key=key,
                payload=payload,
                action=action,
            )

    await call({"revision": 1})
    async with database.sessions.begin() as session:
        await session.execute(
            update(IdempotencyRequest)
            .where(IdempotencyRequest.actor_id == actor)
            .values(
                created_at=datetime.now(UTC) - timedelta(days=2),
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )
        )
    assert not (await call({"revision": 2})).replayed
    assert (await call({"revision": 2})).replayed


async def test_requires_explicit_transaction(database):
    async def action(session):
        return StoredResponse(200, {})

    async with database.sessions() as session:
        with pytest.raises(RuntimeError, match="explicit caller-owned transaction"):
            await run_idempotent(
                session,
                actor_id=uuid4(),
                operation="test.no_transaction",
                key=uuid4(),
                payload={},
                action=action,
            )
        assert (
            await session.scalar(select(func.count()).select_from(IdempotencyRequest))
        ) is not None


@pytest.mark.parametrize("status,projection", [(None, {}), (500, {}), (200, [])])
async def test_database_rejects_invalid_completed_response(database, status, projection):
    with pytest.raises(IntegrityError):
        async with database.sessions.begin() as session:
            session.add(
                IdempotencyRequest(
                    id=uuid4(),
                    actor_id=uuid4(),
                    operation="test.constraint",
                    key=uuid4(),
                    request_hash="a" * 64,
                    outcome="completed",
                    response_status=status,
                    response_projection=projection,
                    expires_at=datetime.now(UTC) + timedelta(days=1),
                )
            )
