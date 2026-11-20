from dataclasses import dataclass, field
from uuid import UUID

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, JsonValue
from starlette.exceptions import HTTPException


@dataclass
class ApplicationError(Exception):
    code: str
    message: str
    status_code: int = 409
    details: dict[str, JsonValue] = field(default_factory=dict)


class ErrorData(BaseModel):
    code: str
    message: str
    details: dict[str, JsonValue]
    request_id: UUID


class ErrorEnvelope(BaseModel):
    error: ErrorData


def error_response(
    *,
    request_id: str,
    code: str,
    message: str,
    status_code: int,
    details: dict[str, JsonValue] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
                "request_id": request_id,
            }
        },
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApplicationError)
    async def application_error(request: Request, exc: ApplicationError) -> JSONResponse:
        return error_response(
            request_id=request.state.request_id,
            code=exc.code,
            message=exc.message,
            details=exc.details,
            status_code=exc.status_code,
        )

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Validation inputs/messages can contain credentials. Return locations/types only.
        fields: list[JsonValue] = [
            {"location": list(error["loc"]), "code": error["type"]} for error in exc.errors()[:20]
        ]
        return error_response(
            request_id=request.state.request_id,
            code="VALIDATION_ERROR",
            message="Некорректные параметры запроса.",
            status_code=422,
            details={"fields": fields},
        )

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
        response = error_response(
            request_id=request.state.request_id,
            code=f"HTTP_{exc.status_code}",
            message="Запрос не может быть выполнен.",
            status_code=exc.status_code,
        )
        for header, value in (exc.headers or {}).items():
            if header.lower() in {"retry-after", "allow", "www-authenticate"}:
                response.headers[header] = value
        return response
