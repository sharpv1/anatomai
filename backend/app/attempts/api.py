from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, Request, Response
from sqlalchemy import select

from app.attempts.models import Attempt
from app.attempts.schemas import (
    Abandon,
    AttemptView,
    Finish,
    ItemAction,
    LearningResult,
    Start,
    Submit,
)
from app.attempts.service import command, error, etag, owned, result_data, view
from app.identity.api import meta
from app.identity.dependencies import current_db, current_identity
from app.identity.policy import access
from app.identity.schemas import Envelope

router = APIRouter(prefix="/api/v1", tags=["learning attempts"])
Key = Annotated[UUID, Header(alias="Idempotency-Key")]


def envelope(request: Request, response: Response, data: dict[str, Any]) -> Any:
    response.headers["ETag"] = f'"attempt-{data["id"]}-{data["version"]}"'
    return Envelope(data=data, meta=meta(request))


@router.post("/attempts", status_code=201, response_model=Envelope[AttemptView])
@access("attempts.self")
async def start(body: Start, key: Key, request: Request, response: Response) -> Any:
    return envelope(request, response, await command(request, key, "start", body))


@router.get("/me/active-attempt", response_model=Envelope[AttemptView | None])
@access("attempts.self")
async def active(request: Request, response: Response) -> Any:
    a = await current_db(request).scalar(
        select(Attempt).where(
            Attempt.user_id == current_identity(request).user.id, Attempt.status == "in_progress"
        )
    )
    if a is None:
        return Envelope(data=None, meta=meta(request))
    return envelope(request, response, await view(current_db(request), a))


@router.get("/attempts/{attempt_id}", response_model=Envelope[AttemptView])
@access("attempts.self")
async def resume(attempt_id: UUID, request: Request, response: Response) -> Any:
    return envelope(
        request, response, await view(current_db(request), await owned(request, attempt_id))
    )


@router.get("/attempts/{attempt_id}/result", response_model=Envelope[LearningResult])
@access("attempts.self")
async def result(attempt_id: UUID, request: Request, response: Response) -> Any:
    a = await owned(request, attempt_id)
    if a.status != "completed":
        raise error("RESULT_NOT_AVAILABLE", "Результат доступен только завершённой попытке.")
    response.headers["ETag"] = etag(a)
    return Envelope(data=result_data(a), meta=meta(request))


@router.post("/attempts/{attempt_id}/items/{item_id}/submit", response_model=Envelope[AttemptView])
@access("attempts.self")
async def submit(
    attempt_id: UUID, item_id: UUID, body: Submit, key: Key, request: Request, response: Response
) -> Any:
    return envelope(
        request, response, await command(request, key, "submit", body, attempt_id, item_id)
    )


@router.post("/attempts/{attempt_id}/advance", response_model=Envelope[AttemptView])
@access("attempts.self")
async def advance(
    attempt_id: UUID, body: ItemAction, key: Key, request: Request, response: Response
) -> Any:
    return envelope(
        request, response, await command(request, key, "advance", body, attempt_id, body.item_id)
    )


@router.post("/attempts/{attempt_id}/skip", response_model=Envelope[AttemptView])
@access("attempts.self")
async def skip(
    attempt_id: UUID, body: ItemAction, key: Key, request: Request, response: Response
) -> Any:
    return envelope(
        request, response, await command(request, key, "skip", body, attempt_id, body.item_id)
    )


@router.post("/attempts/{attempt_id}/finish", response_model=Envelope[AttemptView])
@access("attempts.self")
async def finish(
    attempt_id: UUID, body: Finish, key: Key, request: Request, response: Response
) -> Any:
    return envelope(request, response, await command(request, key, "finish", body, attempt_id))


@router.post("/attempts/{attempt_id}/abandon", response_model=Envelope[AttemptView])
@access("attempts.self")
async def abandon(
    attempt_id: UUID, body: Abandon, key: Key, request: Request, response: Response
) -> Any:
    return envelope(request, response, await command(request, key, "abandon", body, attempt_id))
