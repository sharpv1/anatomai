import hashlib
import hmac
import re
from collections import OrderedDict
from time import monotonic
from uuid import UUID

from fastapi import Request
from starlette.datastructures import Headers
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.config import Settings
from app.core.errors import ApplicationError, error_response

COOKIE_NAME = "__Host-medexa_session"


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode()).digest()


def csrf_token(key: str, session_id: UUID, token: str) -> str:
    return hmac.digest(
        key.encode(), b"medexa-csrf-v1\0" + session_id.bytes + b"\0" + token.encode(), "sha256"
    ).hex()


def require_origin(headers: Headers, settings: Settings, *, mutation: bool) -> None:
    origins = headers.getlist("origin")
    if headers.get("sec-fetch-site") == "cross-site" or (
        origins and origins != [settings.app_origin]
    ):
        raise ApplicationError("ORIGIN_DENIED", "Источник запроса не разрешён.", 403)
    if mutation and origins != [settings.app_origin]:
        raise ApplicationError("ORIGIN_DENIED", "Требуется разрешённый Origin.", 403)


def cookie_token(request: Request) -> str | None:
    values = [
        piece.split("=", 1)[1].strip()
        for header in request.headers.getlist("cookie")
        for piece in header.split(";")
        if "=" in piece and piece.split("=", 1)[0].strip() == COOKIE_NAME
    ]
    if len(values) > 1:
        raise ApplicationError("AUTH_REQUIRED", "Сессия не подтверждена.", 401)
    if not values or not re.fullmatch(r"[A-Za-z0-9_-]{43}", values[0]):
        return None
    return values[0]


class LoginLimiter:
    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.windows: OrderedDict[str, tuple[float, int]] = OrderedDict()

    def take(self, client: str, *, now: float | None = None) -> None:
        current = monotonic() if now is None else now
        start, count = self.windows.pop(client, (current, 0))
        if current - start >= 60:
            start, count = current, 0
        self.windows[client] = (start, count + 1)
        if len(self.windows) > 2048:
            self.windows.popitem(last=False)
        if count >= self.limit:
            raise ApplicationError("RATE_LIMITED", "Повторите запрос позже.", 429)


class IdentityRequestMiddleware:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app, self.settings = app, settings
        self.limiter = LoginLimiter(settings.login_rate_limit)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not scope["path"].startswith("/api/v1/"):
            await self.app(scope, receive, send)
            return
        try:
            headers = Headers(scope=scope)
            if scope["path"] == "/api/v1/auth/telegram":
                require_origin(headers, self.settings, mutation=True)
                self.limiter.take((scope.get("client") or ("unknown", 0))[0])
            length = headers.get("content-length")
            if length is not None and (
                not length.isascii()
                or not length.isdigit()
                or len(length) > 10
                or int(length) > 32768
            ):
                raise ApplicationError("REQUEST_TOO_LARGE", "Запрос слишком большой.", 413)
            if scope["scheme"] != "https":
                raise ApplicationError("HTTPS_REQUIRED", "Требуется HTTPS.", 403)
            size = 0
            messages: list[Message] = []
            while True:
                message = await receive()
                size += len(message.get("body", b""))
                if size > 32768:
                    raise ApplicationError("REQUEST_TOO_LARGE", "Запрос слишком большой.", 413)
                messages.append(message)
                if message["type"] == "http.disconnect" or not message.get("more_body", False):
                    break

            async def bounded_receive() -> Message:
                if messages:
                    return messages.pop(0)
                return await receive()

            await self.app(scope, bounded_receive, send)
        except ApplicationError as exc:
            response = error_response(
                request_id=scope["state"]["request_id"],
                code=exc.code,
                message=exc.message,
                status_code=exc.status_code,
            )
            if exc.status_code == 429:
                response.headers["Retry-After"] = "60"
            await response(scope, receive, send)
