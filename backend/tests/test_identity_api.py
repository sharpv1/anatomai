import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from identity_helpers import ORIGIN, TEST_BOT_TOKEN, TEST_CSRF_KEY, signed_data
from pydantic import SecretStr
from sqlalchemy import func, select, text, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from app.core.errors import ApplicationError
from app.identity.bootstrap import bootstrap_admin
from app.identity.maintenance import cleanup_expired
from app.identity.models import AuditEvent, AuthReplay, User, UserSession
from app.identity.policy import access
from app.identity.security import COOKIE_NAME, token_hash
from app.main import create_app

pytestmark = pytest.mark.integration


@pytest.fixture
async def clients(database, db_settings, monkeypatch):
    monkeypatch.setattr("app.main.configure_logging", lambda level: None)
    settings = db_settings.model_copy(
        update={
            "telegram_bot_token": SecretStr(TEST_BOT_TOKEN),
            "csrf_signing_key": SecretStr(TEST_CSRF_KEY),
            "app_origin": ORIGIN,
            "login_rate_limit": 100,
        }
    )
    app = create_app(settings)

    @app.get("/api/v1/unclassified")
    async def unclassified():
        return {"must_not": "be_public"}

    @app.post("/api/v1/test-admin")
    @access("roles.manage")
    async def admin_route():
        return {"must_not": "execute_without_mfa"}

    @asynccontextmanager
    async def make():
        async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as client:
            yield client

    async with app.router.lifespan_context(app):
        yield make, app, settings


async def login_client(client, user_id=None, **kwargs):
    user_id = user_id or uuid4().int % (2**62) + 1
    raw = kwargs.pop("raw", None) or signed_data(user_id, **kwargs)
    response = await client.post(
        "/api/v1/auth/telegram", json={"init_data": raw}, headers={"Origin": ORIGIN}
    )
    assert response.status_code == 200, response.text
    return response, raw


def mutation_headers(response):
    return {"Origin": ORIGIN, "X-CSRF-Token": response.json()["data"]["csrf_token"]}


async def test_login_restore_cookie_hashes_and_me_alias(clients, database):
    make, app, _ = clients
    async with make() as client:
        response, raw = await login_client(client)
        cookie = response.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
        assert "Path=/" in cookie and "Domain=" not in cookie
        original = response.json()["data"]
        token = client.cookies.get(COOKIE_NAME)
        assert token not in response.text and raw not in response.text
        restore = await client.get("/api/v1/auth/session")
        assert restore.status_code == 200
        assert restore.json()["data"]["csrf_token"] == original["csrf_token"]
        a = await client.get("/api/v1/me")
        b = await client.get("/api/v1/users/me")
        assert a.json()["data"] == b.json()["data"] == original["user"]
        assert a.json()["data"]["roles"] == ["student"]
        assert a.headers["etag"] == '"1"'
        async with database.sessions() as db:
            session = await db.get(UserSession, UUID(original["id"]))
            assert session.token_hash == token_hash(token)
            assert session.csrf_hash == token_hash(original["csrf_token"])
            replay = (
                await db.scalars(select(AuthReplay).where(AuthReplay.session_id == session.id))
            ).one()
            assert len(replay.init_data_digest) == 32


async def test_replay_with_and_without_cookie_including_reordered_encoding(clients):
    from urllib.parse import parse_qsl, urlencode

    make, _, _ = clients
    async with make() as first, make() as other:
        response, raw = await login_client(first)
        repeated = await first.post(
            "/api/v1/auth/telegram", json={"init_data": raw}, headers={"Origin": ORIGIN}
        )
        assert repeated.status_code == 200 and "set-cookie" not in repeated.headers
        assert repeated.json()["data"]["id"] == response.json()["data"]["id"]
        for variant in (raw, urlencode(list(reversed(parse_qsl(raw)))), raw.replace("+", "%20")):
            denied = await other.post(
                "/api/v1/auth/telegram", json={"init_data": variant}, headers={"Origin": ORIGIN}
            )
            assert denied.status_code == 409
            assert denied.json()["error"]["code"] == "AUTH_RELAUNCH_REQUIRED"


async def test_fresh_reauthentication_rotates_and_revokes_old_session(clients):
    make, _, _ = clients
    uid = uuid4().int % (2**62) + 1
    async with make() as client, make() as old:
        first, _ = await login_client(client, uid)
        old.cookies.set(
            COOKIE_NAME, client.cookies.get(COOKIE_NAME), domain="miniapp.test", path="/"
        )
        second, _ = await login_client(client, uid)
        assert second.json()["data"]["id"] != first.json()["data"]["id"]
        assert second.json()["data"]["csrf_token"] != first.json()["data"]["csrf_token"]
        assert (await old.get("/api/v1/me")).status_code == 401
        assert (await client.get("/api/v1/me")).status_code == 200


async def test_concurrent_replay_creates_one_session(clients, database):
    make, _, _ = clients
    uid = uuid4().int % (2**62) + 1
    raw = signed_data(uid)
    async with make() as a, make() as b:
        results = await asyncio.gather(
            *[
                c.post("/api/v1/auth/telegram", json={"init_data": raw}, headers={"Origin": ORIGIN})
                for c in (a, b)
            ]
        )
    assert sorted(r.status_code for r in results) == [200, 409]
    async with database.sessions() as db:
        user = (await db.scalars(select(User).where(User.telegram_user_id == uid))).one()
        assert (
            await db.scalar(
                select(func.count()).select_from(UserSession).where(UserSession.user_id == user.id)
            )
            == 1
        )


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Origin": "https://evil.test"},
        {"Origin": ORIGIN, "X-CSRF-Token": "bad"},
        {"Origin": ORIGIN, "X-CSRF-Token": b"\xe9" * 64},
        {"Origin": ORIGIN, "Sec-Fetch-Site": "cross-site"},
    ],
)
async def test_csrf_and_origin_deny_mutations(clients, headers):
    make, _, _ = clients
    async with make() as client:
        response, _ = await login_client(client)
        result = await client.patch(
            "/api/v1/me/preferences",
            json={"timezone": "Asia/Bishkek"},
            headers={**headers, "If-Match": '"1"'},
        )
        assert result.status_code == 403
        assert (await client.get("/api/v1/me")).json()["data"]["timezone"] == "UTC"


async def test_preferences_etag_validation_and_ownership(clients):
    make, _, _ = clients
    async with make() as client:
        response, _ = await login_client(client)
        headers = mutation_headers(response)
        assert (
            await client.patch(
                "/api/v1/me/preferences", json={"timezone": "Asia/Bishkek"}, headers=headers
            )
        ).status_code == 412
        changed = await client.patch(
            "/api/v1/me/preferences",
            json={"timezone": "Asia/Bishkek", "language": "en"},
            headers={**headers, "If-Match": '"1"'},
        )
        assert changed.status_code == 200 and changed.headers["etag"] == '"2"'
        stale = await client.patch(
            "/api/v1/me/preferences",
            json={"language": "ru"},
            headers={**headers, "If-Match": '"1"'},
        )
        assert stale.status_code == 409
        for body in (
            {},
            {"timezone": "../../etc/passwd"},
            {"language": None},
            {"roles": ["admin"]},
            {"user_id": str(uuid4())},
        ):
            assert (
                await client.patch(
                    "/api/v1/me/preferences", json=body, headers={**headers, "If-Match": '"2"'}
                )
            ).status_code == 422


async def test_own_session_listing_and_foreign_revoke_idor(clients):
    make, _, _ = clients
    async with make() as a, make() as b:
        first, _ = await login_client(a)
        second, _ = await login_client(b)
        items = (await a.get("/api/v1/me/sessions")).json()["data"]
        assert len(items) == 1 and items[0]["current"]
        for target in (second.json()["data"]["id"], str(uuid4())):
            result = await a.delete(
                "/api/v1/me/sessions/" + target, headers=mutation_headers(first)
            )
            assert result.status_code == 404 and result.json()["error"]["code"] == "NOT_FOUND"
        assert (await b.get("/api/v1/me")).status_code == 200
        result = await a.delete(
            "/api/v1/me/sessions/" + first.json()["data"]["id"], headers=mutation_headers(first)
        )
        assert result.status_code == 204 and "Max-Age=0" in result.headers["set-cookie"]
        assert (await a.get("/api/v1/me")).status_code == 401


async def test_logout_idempotent_and_replay_does_not_restore_revoked_session(clients):
    make, _, _ = clients
    async with make() as client:
        response, raw = await login_client(client)
        original_token = client.cookies.get(COOKIE_NAME)
        assert (
            await client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
        ).status_code == 403
        assert (
            await client.post("/api/v1/auth/logout", headers=mutation_headers(response))
        ).status_code == 204
        client.cookies.set(COOKIE_NAME, original_token, domain="miniapp.test", path="/")
        assert (
            await client.post("/api/v1/auth/logout", headers=mutation_headers(response))
        ).status_code == 204
        assert (
            await client.post("/api/v1/auth/logout", headers={"Origin": ORIGIN})
        ).status_code == 204
        assert (await client.get("/api/v1/auth/session")).status_code == 401
        assert (
            await client.post(
                "/api/v1/auth/telegram", json={"init_data": raw}, headers={"Origin": ORIGIN}
            )
        ).status_code == 409


@pytest.mark.parametrize("field", ["expires_at", "idle_expires_at", "revoked_at", "status"])
async def test_expiry_revocation_and_blocked_user(clients, database, field):
    make, _, _ = clients
    async with make() as client:
        response, _ = await login_client(client)
        data = response.json()["data"]
        async with database.sessions.begin() as db:
            if field == "status":
                await db.execute(
                    update(User).where(User.id == UUID(data["user"]["id"])).values(status="blocked")
                )
            else:
                session = await db.get(UserSession, UUID(data["id"]))
                session.created_at = datetime.now(UTC) - timedelta(days=10)
                if field == "expires_at":
                    session.idle_expires_at = datetime.now(UTC) - timedelta(days=2)
                    session.expires_at = datetime.now(UTC) - timedelta(days=1)
                else:
                    setattr(session, field, datetime.now(UTC) - timedelta(seconds=1))
        assert (await client.get("/api/v1/me")).status_code == (403 if field == "status" else 401)


async def test_default_deny_and_no_trust_in_client_roles_or_telegram_flags(clients):
    make, _, _ = clients
    async with make() as client:
        raw = signed_data(
            user={
                "id": uuid4().int % (2**62) + 1,
                "first_name": "Admin",
                "is_premium": True,
                "is_admin": True,
            }
        )
        response, _ = await login_client(client, raw=raw)
        assert response.json()["data"]["user"]["roles"] == ["student"]
        assert (await client.get("/api/v1/unclassified")).status_code == 403
        assert (
            await client.post("/api/v1/test-admin", headers=mutation_headers(response))
        ).status_code == 403
        for extra in ({"telegram_id": 1}, {"role": "admin"}):
            assert (
                await client.post(
                    "/api/v1/auth/telegram",
                    json={"init_data": signed_data(), **extra},
                    headers={"Origin": ORIGIN},
                )
            ).status_code == 422


async def test_bootstrap_existing_user_only_once_revokes_sessions_and_audits(clients, database):
    make, _, _ = clients
    uid = uuid4().int % (2**62) + 1
    async with make() as client:
        response, _ = await login_client(client, uid)
        async with database.sessions.begin() as db:
            assert await bootstrap_admin(db, uid)
        assert (await client.get("/api/v1/me")).status_code == 401
        async with database.sessions.begin() as db:
            assert not await bootstrap_admin(db, uid)
        new, _ = await login_client(client, uid)
        assert "admin" in new.json()["data"]["user"]["roles"]
        async with make() as other:
            other_response, _ = await login_client(other)
            async with database.sessions.begin() as db:
                with pytest.raises(ApplicationError) as error:
                    await bootstrap_admin(
                        db, int(other_response.json()["data"]["user"]["telegram_user_id"])
                    )
                assert error.value.code == "BOOTSTRAP_CLOSED"
        denied = await client.post("/api/v1/test-admin", headers=mutation_headers(new))
        assert denied.json()["error"]["code"] == "MFA_REQUIRED"
        for sql in (
            "DELETE FROM audit_events",
            "UPDATE audit_events SET action='changed'",
            "TRUNCATE audit_events",
        ):
            with pytest.raises(DBAPIError):
                async with database.sessions.begin() as db:
                    await db.execute(text(sql))


async def test_login_origin_https_and_body_limits(clients):
    make, app, _ = clients
    async with make() as client:
        raw = signed_data()
        assert (
            await client.post("/api/v1/auth/telegram", json={"init_data": raw})
        ).status_code == 403
        assert (
            await client.post(
                "/api/v1/auth/telegram",
                json={"init_data": raw},
                headers={"Origin": "https://evil.test"},
            )
        ).status_code == 403
        assert (
            await client.post(
                "/api/v1/auth/telegram", content=b"x" * 32769, headers={"Origin": ORIGIN}
            )
        ).status_code == 413

        async def chunks():
            yield b"x" * 16000
            yield b"x" * 18000

        assert (
            await client.post("/api/v1/auth/telegram", content=chunks(), headers={"Origin": ORIGIN})
        ).status_code == 413
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://miniapp.test"
    ) as insecure:
        assert (
            await insecure.post(
                "/api/v1/auth/telegram",
                json={"init_data": raw},
                headers={"Origin": ORIGIN, "X-Forwarded-Proto": "https"},
            )
        ).status_code == 403


async def test_session_and_init_data_not_logged(clients, caplog):
    make, _, _ = clients
    async with make() as client:
        response, raw = await login_client(client)
        token = client.cookies.get(COOKIE_NAME)
        await client.get("/api/v1/auth/session")
        assert raw not in caplog.text and token not in caplog.text
        assert response.json()["data"]["csrf_token"] not in caplog.text


async def test_session_survives_new_app_instance_and_wrong_signing_key_fails_closed(clients):
    make, _, settings = clients
    async with make() as client:
        original, _ = await login_client(client)
        token = client.cookies.get(COOKIE_NAME)
    for key, expected in ((TEST_CSRF_KEY, 200), (TEST_CSRF_KEY + "rotated", 401)):
        app = create_app(settings.model_copy(update={"csrf_signing_key": SecretStr(key)}))
        async with app.router.lifespan_context(app):
            async with AsyncClient(transport=ASGITransport(app=app), base_url=ORIGIN) as restored:
                restored.cookies.set(COOKIE_NAME, token, domain="miniapp.test", path="/")
                response = await restored.get("/api/v1/auth/session")
                assert response.status_code == expected
                if expected == 200:
                    assert response.json()["data"]["id"] == original.json()["data"]["id"]
                    assert (
                        response.json()["data"]["csrf_token"]
                        == original.json()["data"]["csrf_token"]
                    )
                else:
                    fresh, _ = await login_client(
                        restored, int(original.json()["data"]["user"]["telegram_user_id"])
                    )
                    assert fresh.json()["data"]["id"] != original.json()["data"]["id"]


async def test_no_bootstrap_for_nonexistent_user_and_no_public_role_grant(clients, database):
    make, _, _ = clients
    async with database.sessions.begin() as db:
        with pytest.raises(ApplicationError) as error:
            await bootstrap_admin(db, uuid4().int % (2**62) + 1)
        assert error.value.code == "BOOTSTRAP_USER_REQUIRED"
    async with make() as client:
        response, _ = await login_client(client)
        assert (
            await client.post(
                "/api/v1/admin/bootstrap",
                json={"role": "admin"},
                headers=mutation_headers(response),
            )
        ).status_code == 404
        assert (await client.get("/api/v1/me")).json()["data"]["roles"] == ["student"]


async def test_unrelated_identity_cannot_replace_valid_session(clients):
    make, _, _ = clients
    async with make() as client:
        first, _ = await login_client(client)
        result = await client.post(
            "/api/v1/auth/telegram",
            json={"init_data": signed_data(uuid4().int % (2**62) + 1)},
            headers={"Origin": ORIGIN},
        )
        assert (
            result.status_code == 409
            and result.json()["error"]["code"] == "SESSION_IDENTITY_MISMATCH"
        )
        assert (await client.get("/api/v1/me")).json()["data"]["id"] == first.json()["data"][
            "user"
        ]["id"]


async def test_idle_heartbeat_is_persisted_without_extending_absolute_expiry(clients, database):
    make, _, _ = clients
    async with make() as client:
        response, _ = await login_client(client)
        sid = UUID(response.json()["data"]["id"])
        async with database.sessions.begin() as db:
            session = await db.get(UserSession, sid)
            absolute = session.expires_at
            session.created_at = datetime.now(UTC) - timedelta(hours=2)
            session.last_seen_at = datetime.now(UTC) - timedelta(hours=1)
            session.idle_expires_at = datetime.now(UTC) + timedelta(hours=1)
        assert (await client.get("/api/v1/auth/session")).status_code == 200
        async with database.sessions() as db:
            session = await db.get(UserSession, sid)
            assert session.expires_at == absolute
            assert session.last_seen_at > datetime.now(UTC) - timedelta(minutes=1)
            assert session.idle_expires_at > datetime.now(UTC) + timedelta(hours=23)


async def test_active_device_sessions_are_bounded_and_oldest_is_revoked(clients):
    make, _, _ = clients
    uid = uuid4().int % (2**62) + 1
    tokens = []
    for _ in range(11):
        async with make() as client:
            await login_client(client, uid)
            tokens.append(client.cookies.get(COOKIE_NAME))
    async with make() as oldest, make() as latest:
        oldest.cookies.set(COOKIE_NAME, tokens[0], domain="miniapp.test", path="/")
        latest.cookies.set(COOKIE_NAME, tokens[-1], domain="miniapp.test", path="/")
        assert (await oldest.get("/api/v1/me")).status_code == 401
        assert len((await latest.get("/api/v1/me/sessions")).json()["data"]) == 10


async def test_replay_record_must_belong_to_session_owner(clients, database):
    make, _, _ = clients
    async with make() as a, make() as b:
        first, _ = await login_client(a)
        second, _ = await login_client(b)
        with pytest.raises(IntegrityError):
            async with database.sessions.begin() as db:
                db.add(
                    AuthReplay(
                        init_data_digest=token_hash(str(uuid4())),
                        bot_id=42424242,
                        user_id=UUID(first.json()["data"]["user"]["id"]),
                        session_id=UUID(second.json()["data"]["id"]),
                        valid_until=datetime.now(UTC) + timedelta(minutes=5),
                    )
                )


async def test_cleanup_preserves_users_active_sessions_and_immutable_audit(clients, database):
    make, _, _ = clients
    async with make() as old, make() as active:
        old_response, _ = await login_client(old)
        active_response, _ = await login_client(active)
        sid = UUID(old_response.json()["data"]["id"])
        uid = UUID(old_response.json()["data"]["user"]["id"])
        now = datetime.now(UTC)
        async with database.sessions.begin() as db:
            session = await db.get(UserSession, sid)
            session.created_at = now - timedelta(days=40)
            session.last_seen_at = now - timedelta(days=35)
            session.idle_expires_at = now - timedelta(days=32)
            session.expires_at = now - timedelta(days=31)
            await db.execute(
                update(AuthReplay)
                .where(AuthReplay.session_id == sid)
                .values(valid_until=now - timedelta(days=2))
            )
        async with database.sessions.begin() as db:
            assert await cleanup_expired(db) == (1, 1)
        async with database.sessions.begin() as db:
            assert await cleanup_expired(db) == (0, 0)
            assert await db.get(User, uid) is not None
            assert await db.get(UserSession, sid) is None
            assert (
                await db.scalar(
                    select(func.count()).select_from(AuditEvent).where(AuditEvent.actor_id == uid)
                )
                >= 1
            )
        assert (await active.get("/api/v1/me")).status_code == 200
