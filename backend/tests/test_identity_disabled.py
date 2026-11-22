import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import ValidationError

from app.core.config import Settings
from app.main import create_app


async def test_no_fallback_auth_without_secrets(settings, monkeypatch):
    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://localhost"
        ) as client:
            r = await client.post(
                "/api/v1/auth/telegram",
                json={"init_data": "not-a-proof"},
                headers={"Origin": "https://localhost"},
            )
            assert r.status_code == 503
            assert r.json()["error"]["code"] == "AUTH_NOT_CONFIGURED"
            assert "set-cookie" not in r.headers
            schema = (await client.get("/openapi.json")).json()
            for status in ("401", "403", "409", "413", "429", "503"):
                assert status in schema["paths"]["/api/v1/auth/telegram"]["post"]["responses"]


def test_blank_secrets_disable_auth_and_insecure_origin_is_rejected(settings):
    disabled = Settings(
        **{**settings.model_dump(), "telegram_bot_token": "", "csrf_signing_key": ""}
    )
    assert disabled.telegram_bot_token is None and disabled.csrf_signing_key is None
    with pytest.raises(ValidationError):
        Settings(**{**settings.model_dump(), "app_origin": "http://localhost"})


@pytest.mark.parametrize(
    "field,value", [("csrf_signing_key", "short"), ("telegram_bot_token", "invalid")]
)
def test_bad_secret_validation_does_not_print_input(settings, field, value):
    with pytest.raises(ValidationError) as error:
        Settings(**{**settings.model_dump(), field: value})
    assert value not in str(error.value)
