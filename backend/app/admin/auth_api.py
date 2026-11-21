import re
from uuid import UUID

from fastapi import APIRouter, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, SecretStr, field_validator

from app.admin.mfa import utcnow, verify_step_up
from app.admin.models import StepUp
from app.core.errors import error_response
from app.identity.api import meta
from app.identity.dependencies import current_db, current_identity
from app.identity.policy import access
from app.identity.schemas import Envelope
from app.identity.service import audit

router = APIRouter(prefix="/api/v1/admin/auth", tags=["admin MFA"])


class StepUpProof(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    code: SecretStr

    @field_validator("code")
    @classmethod
    def six_digits(cls, value: SecretStr) -> SecretStr:
        if not re.fullmatch(r"[0-9]{6}", value.get_secret_value()):
            raise ValueError("Use six TOTP digits")
        return value


@router.post("/step-up", response_model=Envelope[dict[str, str]])
@access("admin.step_up")
async def confirm(body: StepUpProof, request: Request) -> Envelope[dict[str, str]] | JSONResponse:
    grant, failure = await verify_step_up(
        current_db(request),
        request.app.state.settings,
        current_identity(request),
        body.code.get_secret_value(),
        UUID(request.state.request_id),
    )
    if failure is not None:
        # Return after staging failure/audit, allowing the dependency transaction to commit.
        # Raising here would roll back the rate limiter and permit unlimited guesses.
        response = error_response(
            request_id=request.state.request_id,
            code=failure.code,
            message=failure.message,
            status_code=failure.status_code,
        )
        if failure.status_code == 429:
            response.headers["Retry-After"] = "300"
        return response
    assert grant is not None
    return Envelope(
        data={
            "verified_at": grant.verified_at.isoformat(),
            "expires_at": grant.expires_at.isoformat(),
        },
        meta=meta(request),
    )


@router.delete("/step-up", status_code=204)
@access("admin.step_up")
async def revoke(request: Request) -> Response:
    identity, db = current_identity(request), current_db(request)
    grant = await db.get(StepUp, identity.session.id, with_for_update=True)
    if grant is not None and grant.revoked_at is None:
        grant.revoked_at = utcnow()
        audit(
            db,
            actor=identity.user.id,
            action="mfa.revoked",
            entity_type="session",
            entity_id=identity.session.id,
            request_id=UUID(request.state.request_id),
        )
    return Response(status_code=204)
