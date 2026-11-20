import json
import logging

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.core.idempotency import StoredResponse, request_fingerprint
from app.core.logging import JsonFormatter, request_id_context


def test_password_is_secret_and_url_encodes_special_characters(settings):
    settings = Settings(**{**settings.model_dump(), "db_password": "secret:@/% value"})
    assert "secret:@/% value" not in repr(settings)
    assert "secret" not in str(settings.database_url)
    assert settings.database_url.password == "secret:@/% value"


@pytest.mark.parametrize(
    "name", ["production", "old_medexa", "medexa_foundation_x;DROP", "медекса"]
)
def test_refuses_unrelated_database_names(settings, name):
    with pytest.raises(ValidationError):
        Settings(**{**settings.model_dump(), "db_name": name})


@pytest.mark.parametrize("password", ["", "REPLACE_ME"])
def test_password_has_no_usable_default(settings, password):
    with pytest.raises(ValidationError):
        Settings(**{**settings.model_dump(), "db_password": password})


def test_no_production_environment(settings):
    with pytest.raises(ValidationError):
        Settings(**{**settings.model_dump(), "environment": "production"})


def test_fingerprint_is_order_independent_and_sensitive_to_content():
    assert request_fingerprint({"a": 1, "b": ["Тест"]}) == request_fingerprint(
        {"b": ["Тест"], "a": 1}
    )
    assert request_fingerprint({"a": 1}) != request_fingerprint({"a": 2})
    with pytest.raises(ValueError):
        request_fingerprint({"a": float("nan")})


def test_cannot_cache_unsuccessful_or_oversize_response():
    with pytest.raises(ValueError):
        StoredResponse(500, {})
    with pytest.raises(ValueError):
        StoredResponse(200, {"large": "x" * 1_000_001})


def test_json_logs_drop_inputs_secrets_exception_and_arbitrary_messages():
    formatter = JsonFormatter()
    token = request_id_context.set("trace-test")
    try:
        try:
            raise RuntimeError("postgres://user:secret@host/db")
        except RuntimeError:
            import sys

            record = logging.LogRecord(
                "test", logging.ERROR, "", 1, "request_failed", (), sys.exc_info()
            )
        record.error_type = "RuntimeError"
        record.init_data = "secret-init-data"
        result = formatter.format(record)
        data = json.loads(result)
        assert data["request_id"] == "trace-test"
        assert data["error_type"] == "RuntimeError"
        assert "secret" not in result and "Traceback" not in result
        record.msg = "request https://host/?token=secret"
        assert json.loads(formatter.format(record))["event"] == "library_log"
    finally:
        request_id_context.reset(token)
