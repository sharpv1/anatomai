import asyncio
from unittest.mock import AsyncMock
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.health import database_dependency
from app.core.errors import ApplicationError
from app.identity.dependencies import enforce_access
from app.main import create_app


@pytest.fixture
async def client(settings, monkeypatch):
    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    app = create_app(settings)
    app.dependency_overrides[enforce_access] = lambda: None
    fake = AsyncMock()
    fake.check_ready.return_value = None
    app.dependency_overrides[database_dependency] = lambda: fake

    @app.get("/test-validation/{number}")
    async def validation(number: int):
        return {"number": number}

    @app.get("/test-error")
    async def error():
        raise RuntimeError("never expose secret-connection-string")

    @app.get("/test-conflict")
    async def conflict():
        raise ApplicationError("CONFLICT", "Конфликт состояния.")

    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as http:
            yield http, fake


async def test_liveness_never_connects_to_database(client):
    http, fake = client
    response = await http.get("/live")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "alive"
    assert UUID(response.json()["meta"]["request_id"])
    assert response.headers["cache-control"] == "no-store"
    fake.check_ready.assert_not_called()


async def test_readiness_checks_database(client):
    http, fake = client
    response = await http.get("/ready")
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ready"
    fake.check_ready.assert_awaited_once()


async def test_database_failure_is_503_without_secrets_and_liveness_stays_alive(client):
    http, fake = client
    fake.check_ready.side_effect = RuntimeError("secret-connection-string")
    response = await http.get("/ready")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "SERVICE_NOT_READY"
    assert "secret" not in response.text
    assert (await http.get("/live")).status_code == 200


async def test_readiness_is_bounded(client):
    http, fake = client
    http._transport.app.state.settings = http._transport.app.state.settings.model_copy(
        update={"readiness_timeout_seconds": 0.1}
    )

    async def slow():
        await asyncio.sleep(2)

    fake.check_ready.side_effect = slow
    async with asyncio.timeout(0.5):
        assert (await http.get("/ready")).status_code == 503


@pytest.mark.parametrize(
    "path,status,code",
    [
        ("/not-found", 404, "HTTP_404"),
        ("/test-validation/secret-value", 422, "VALIDATION_ERROR"),
        ("/test-error", 500, "INTERNAL_ERROR"),
        ("/test-conflict", 409, "CONFLICT"),
    ],
)
async def test_uniform_errors_and_request_id(client, path, status, code):
    http, _ = client
    request_id = str(uuid4())
    response = await http.get(path, headers={"X-Request-ID": request_id})
    assert response.status_code == status
    assert response.headers["x-request-id"] == request_id
    assert response.json()["error"]["request_id"] == request_id
    assert response.json()["error"]["code"] == code
    assert "secret" not in response.text


async def test_method_not_allowed_and_untrusted_request_id(client):
    http, _ = client
    response = await http.post("/live", headers={"X-Request-ID": "untrusted-value"})
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
    assert UUID(response.headers["x-request-id"])


async def test_database_pool_is_disposed_on_shutdown(settings, monkeypatch):
    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    fake = AsyncMock()
    monkeypatch.setattr("app.main.Database", lambda settings: fake)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        fake.dispose.assert_not_called()
    fake.dispose.assert_awaited_once()


async def test_openapi_declares_the_actual_error_envelope(client):
    http, _ = client
    schema = (await http.get("/openapi.json")).json()
    for path, status in (("/ready", "503"), ("/test-validation/{number}", "422")):
        response = schema["paths"][path]["get"]["responses"][status]
        assert response["content"]["application/json"]["schema"]["$ref"].endswith("ErrorEnvelope")


async def test_request_ids_are_isolated_between_concurrent_requests(client):
    http, _ = client
    ids = [str(uuid4()), str(uuid4())]
    responses = await asyncio.gather(
        *[http.get("/ready", headers={"X-Request-ID": request_id}) for request_id in ids]
    )
    assert [response.json()["meta"]["request_id"] for response in responses] == ids
