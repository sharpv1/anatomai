import logging
from time import perf_counter
from uuid import UUID, uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response
from app.core.logging import request_id_context

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        supplied = Headers(scope=scope).get("x-request-id", "")
        try:
            request_id = str(UUID(supplied)) if len(supplied) == 36 else str(uuid4())
        except ValueError:
            request_id = str(uuid4())
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        started = perf_counter()
        status = 500
        response_started = False

        async def send_response(message: Message) -> None:
            nonlocal status, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status = message["status"]
                headers = MutableHeaders(scope=message)
                headers["X-Request-ID"] = request_id
                headers["Cache-Control"] = "no-store"
                headers["Referrer-Policy"] = "no-referrer"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        try:
            await self.app(scope, receive, send_response)
        except Exception as exc:
            logger.error("request_failed", extra={"error_type": type(exc).__name__})
            if response_started:
                # A partial streaming response cannot be replaced with JSON.
                raise
            response = error_response(
                request_id=request_id,
                code="INTERNAL_ERROR",
                message="Внутренняя ошибка сервиса.",
                status_code=500,
            )
            await response(scope, receive, send_response)
        finally:
            route = scope.get("route")
            logger.info(
                "http_request",
                extra={
                    "method": scope["method"],
                    "route": getattr(route, "path", "<unmatched>"),
                    "status": status,
                    "duration_ms": round((perf_counter() - started) * 1000, 2),
                },
            )
            request_id_context.reset(token)
