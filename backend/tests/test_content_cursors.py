from uuid import uuid4

import pytest

from app.content.cursors import decode_cursor, encode_cursor, filter_hash, normalize
from app.core.errors import ApplicationError

KEY = "synthetic-content-test-key-" + "x" * 40


def test_cursor_signed_bound_and_expiring():
    scope = filter_hash({"endpoint": "reference", "query": "еж"})
    cursor = encode_cursor(KEY, version=3, scope=scope, position=2, entity_id=str(uuid4()))
    assert decode_cursor(cursor, KEY, version=3, scope=scope)[0] == 2
    with pytest.raises(ApplicationError) as error:
        decode_cursor(cursor, KEY, version=4, scope=scope)
    assert error.value.code == "CATALOG_CHANGED"
    for raw, key, request_scope in [
        (cursor, KEY + "other", scope),
        (cursor, KEY, "other"),
        (cursor[:-8] + "00000000", KEY, scope),
        ("bad", KEY, scope),
        ("é", KEY, scope),
        (
            encode_cursor(KEY, version=3, scope=scope, position=2, entity_id=str(uuid4()), now=0),
            KEY,
            scope,
        ),
    ]:
        with pytest.raises(ApplicationError):
            decode_cursor(raw, key, version=3, scope=request_scope)


def test_search_is_nfc_case_and_yo_normalized():
    assert normalize(" ЁЖ ") == "еж"
    assert normalize("Е\u0308Ж") == "еж"


async def test_content_is_disabled_without_key_but_metadata_is_honest(settings, monkeypatch):
    from httpx import ASGITransport, AsyncClient

    from app.main import create_app

    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    app = create_app(settings)
    async with app.router.lifespan_context(app):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="https://localhost"
        ) as client:
            response = await client.get("/api/v1/meta")
            assert response.status_code == 200
            assert response.json()["data"]["capabilities"] == {
                "content_configured": False,
                "attempts": True,
                "asset_delivery": False,
                "billing": False,
            }
