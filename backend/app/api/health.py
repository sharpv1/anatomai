import asyncio
import logging
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.core.errors import ApplicationError
from app.db.database import Database
from app.identity.policy import access

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


class Meta(BaseModel):
    request_id: UUID
    server_time: datetime
    schema_version: Literal["1"] = "1"


class HealthData(BaseModel):
    status: Literal["alive", "ready"]


class HealthResponse(BaseModel):
    data: HealthData
    meta: Meta


def database_dependency(request: Request) -> Database:
    database: Database = request.app.state.database
    return database


def health_response(request: Request, status: Literal["alive", "ready"]) -> HealthResponse:
    return HealthResponse(
        data=HealthData(status=status),
        meta=Meta(request_id=request.state.request_id, server_time=datetime.now(UTC)),
    )


@router.get("/live", response_model=HealthResponse)
@access("public.health")
async def live(request: Request) -> HealthResponse:
    return health_response(request, "alive")


@router.get("/ready", response_model=HealthResponse)
@access("public.health")
async def ready(
    request: Request, database: Annotated[Database, Depends(database_dependency)]
) -> HealthResponse:
    try:
        async with asyncio.timeout(request.app.state.settings.readiness_timeout_seconds):
            await database.check_ready()
    except Exception as exc:
        logger.warning("readiness_failed", extra={"error_type": type(exc).__name__})
        raise ApplicationError(
            code="SERVICE_NOT_READY",
            message="Сервис временно не готов к работе.",
            status_code=503,
        ) from None
    return health_response(request, "ready")
