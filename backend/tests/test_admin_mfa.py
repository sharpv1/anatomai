import asyncio
from datetime import timedelta

import pytest
from admin_helpers import TOTP_SECRET
from sqlalchemy import select

from app.admin.mfa import match_counter, provision
from app.admin.models import MFACredential, RecoveryCode, StepUp
from app.core.errors import ApplicationError
from app.identity.models import AuditEvent, UserRole, UserSession

pytestmark = pytest.mark.integration


@pytest.mark.parametrize("role", ["student", "support"])
async def test_non_admin_roles_cannot_even_step_up(admin_clients, role):
    async with admin_clients(role, confirmed=False) as actor:
        response = await actor.client.post(
            "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=actor.headers
        )
        assert response.status_code == 403 and response.json()["error"]["code"] == "ACCESS_DENIED"
        assert (await actor.client.get("/api/v1/admin/disciplines")).status_code == 403


async def test_missing_enrollment_and_disabled_config_fail_closed(admin_clients):
    async with admin_clients(confirmed=False, enrolled=False) as actor:
        response = await actor.client.post(
            "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=actor.headers
        )
        assert response.json()["error"]["code"] == "MFA_NOT_ENROLLED"
        actor.app.state.settings = actor.settings.model_copy(update={"mfa_encryption_key": None})
        response = await actor.client.post(
            "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=actor.headers
        )
        assert (
            response.status_code == 503 and response.json()["error"]["code"] == "MFA_NOT_CONFIGURED"
        )
        assert (await actor.client.get("/api/v1/admin/disciplines")).status_code == 403


@pytest.mark.parametrize("bad", ["", "12345", "1234567", "abcdef", "１２３４５６", 123456])
async def test_bad_proof_format_is_not_echoed(admin_clients, bad):
    async with admin_clients(confirmed=False) as actor:
        response = await actor.client.post(
            "/api/v1/admin/auth/step-up", json={"code": bad}, headers=actor.headers
        )
        assert response.status_code == 422
        assert "input" not in response.text and "encrypted_secret" not in response.text


async def test_csrf_and_origin_cannot_be_bypassed(admin_clients):
    async with admin_clients(confirmed=False) as actor:
        for headers in (
            {},
            {"Origin": "https://evil.test", "X-CSRF-Token": actor.headers["X-CSRF-Token"]},
        ):
            response = await actor.client.post(
                "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=headers
            )
            assert response.status_code == 403
        # Missing CSRF must not consume the valid TOTP counter.
        response = await actor.client.post(
            "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=actor.headers
        )
        assert response.status_code == 200


async def test_failure_counter_commits_and_survives_reopen(admin_clients, database):
    async with admin_clients(confirmed=False) as actor:
        invalid = next(
            f"{i:06d}"
            for i in range(100)
            if match_counter(TOTP_SECRET, f"{i:06d}", actor.clock[0], -1) is None
        )
        for _ in range(5):
            response = await actor.client.post(
                "/api/v1/admin/auth/step-up", json={"code": invalid}, headers=actor.headers
            )
            assert response.status_code == 403
        response = await actor.client.post(
            "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=actor.headers
        )
        assert response.status_code == 429 and response.headers["retry-after"] == "300"
        async with database.sessions() as db:
            credential = await db.get(MFACredential, actor.user_id)
            assert credential.failed_attempts == 5 and credential.locked_until is not None
            audits = (
                await db.scalars(
                    select(AuditEvent).where(
                        AuditEvent.actor_id == actor.user_id, AuditEvent.action == "mfa.rejected"
                    )
                )
            ).all()
            assert len(audits) == 5 and all(event.safe_diff == {} for event in audits)
        actor.clock[0] += timedelta(seconds=301)
        response = await actor.client.post(
            "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=actor.headers
        )
        assert response.status_code == 200


async def test_parallel_replay_only_one_confirmation(admin_clients):
    async with admin_clients(confirmed=False) as actor:
        responses = await asyncio.gather(
            *[
                actor.client.post(
                    "/api/v1/admin/auth/step-up", json={"code": actor.code()}, headers=actor.headers
                )
                for _ in range(2)
            ]
        )
        assert sorted(response.status_code for response in responses) == [200, 403]
        rejected = next(r for r in responses if r.status_code == 403)
        assert rejected.json()["error"]["code"] == "MFA_INVALID"


@pytest.mark.parametrize("failure", ["expired", "future", "version", "roles", "revoked"])
async def test_server_grant_binding_and_freshness(admin_clients, database, failure):
    async with admin_clients() as actor:
        assert (await actor.client.get("/api/v1/admin/disciplines")).status_code == 200
        async with database.sessions.begin() as db:
            grant = await db.scalar(select(StepUp).where(StepUp.user_id == actor.user_id))
            if failure == "expired":
                grant.verified_at = actor.clock[0] - timedelta(minutes=16)
                grant.expires_at = actor.clock[0] - timedelta(minutes=1)
            if failure == "future":
                grant.verified_at = actor.clock[0] + timedelta(minutes=1)
                grant.expires_at = actor.clock[0] + timedelta(minutes=15)
            if failure == "version":
                credential = await db.get(MFACredential, actor.user_id)
                credential.version += 1
            if failure == "roles":
                db.add(UserRole(user_id=actor.user_id, role_code="content_reviewer"))
            if failure == "revoked":
                grant.revoked_at = actor.clock[0]
        response = await actor.client.get(
            "/api/v1/admin/disciplines", headers={"X-MFA-Verified": "true"}
        )
        assert response.status_code == 403 and response.json()["error"]["code"] == "MFA_REQUIRED"


async def test_mfa_revoke_is_safe_repeat_and_session_remains_user_session(admin_clients):
    async with admin_clients() as actor:
        for _ in range(2):
            assert (
                await actor.client.delete("/api/v1/admin/auth/step-up", headers=actor.headers)
            ).status_code == 204
        assert (await actor.client.get("/api/v1/admin/disciplines")).status_code == 403
        assert (await actor.client.get("/api/v1/me")).status_code == 200


async def test_new_telegram_session_does_not_inherit_step_up(admin_clients):
    from identity_helpers import ORIGIN, signed_data

    async with admin_clients() as actor:
        response = await actor.client.post(
            "/api/v1/auth/telegram",
            json={"init_data": signed_data(actor.telegram_id)},
            headers={"Origin": ORIGIN},
        )
        assert response.status_code == 200
        assert (await actor.client.get("/api/v1/admin/disciplines")).status_code == 403


async def test_recovery_is_operator_only_single_use_and_revokes_sessions(admin_clients, database):
    async with admin_clients() as actor:
        actor.clock[0] += timedelta(seconds=30)
        async with database.sessions.begin() as db:
            codes = await provision(
                db,
                actor.settings,
                actor.telegram_id,
                TOTP_SECRET,
                actor.code(),
                recovery=actor.codes[0],
            )
        assert len(codes) == 10 and set(codes).isdisjoint(actor.codes)
        assert (await actor.client.get("/api/v1/me")).status_code == 401
        async with database.sessions() as db:
            credential = await db.get(MFACredential, actor.user_id)
            assert credential.version == 2
            old_codes = (
                await db.scalars(
                    select(RecoveryCode).where(
                        RecoveryCode.user_id == actor.user_id, RecoveryCode.credential_version == 1
                    )
                )
            ).all()
            assert all(code.used_at is not None for code in old_codes)
            assert all(code.code_hash.hex() not in codes for code in old_codes)
        with pytest.raises(ApplicationError) as exc:
            async with database.sessions.begin() as db:
                await provision(
                    db,
                    actor.settings,
                    actor.telegram_id,
                    TOTP_SECRET,
                    actor.code(),
                    recovery=actor.codes[0],
                )
        assert exc.value.code == "RECOVERY_INVALID"
        assert (await actor.client.post("/api/v1/admin/auth/recovery", json={})).status_code == 404
        assert (await actor.client.post("/api/v1/admin/auth/enroll", json={})).status_code == 404


async def test_enrollment_cannot_replace_existing_mfa_without_recovery(admin_clients, database):
    async with admin_clients() as actor:
        with pytest.raises(ApplicationError) as exc:
            async with database.sessions.begin() as db:
                await provision(db, actor.settings, actor.telegram_id, TOTP_SECRET, actor.code())
        assert exc.value.code == "MFA_ALREADY_ENROLLED"
        async with database.sessions.begin() as db:
            # Revoked ordinary sessions are rejected even if a fresh grant row remains.
            session = await db.scalar(
                select(UserSession).where(UserSession.user_id == actor.user_id)
            )
            session.revoked_at = actor.clock[0]
        assert (await actor.client.get("/api/v1/admin/disciplines")).status_code == 401


async def test_step_up_bootstrap_permission_cannot_be_used_for_other_admin_routes(admin_clients):
    from app.identity.policy import access

    async with admin_clients("admin") as actor:

        @actor.app.get("/api/v1/admin/invalid-bootstrap")
        @access("admin.step_up")
        async def invalid_bootstrap():
            return {"must_not_execute": True}

        @actor.app.post("/api/v1/admin/unimplemented-roles")
        @access("roles.manage")
        async def unpublished_handler():
            return {"must_not_execute": True}

        assert (await actor.client.get("/api/v1/admin/invalid-bootstrap")).status_code == 403
        assert (
            await actor.client.post("/api/v1/admin/unimplemented-roles", headers=actor.headers)
        ).status_code == 403


async def test_identity_maintenance_can_remove_expired_session_without_losing_mfa_history(
    admin_clients, database
):
    from datetime import UTC, datetime

    from sqlalchemy import func

    from app.identity.maintenance import cleanup_expired
    from app.identity.models import AuthReplay

    async with admin_clients() as actor:
        async with database.sessions.begin() as db:
            now = datetime.now(UTC)
            session = await db.scalar(
                select(UserSession).where(UserSession.user_id == actor.user_id)
            )
            session_id = session.id
            session.created_at = now - timedelta(days=40)
            session.last_seen_at = now - timedelta(days=37)
            session.idle_expires_at = now - timedelta(days=36)
            session.expires_at = now - timedelta(days=35)
            grant = await db.get(StepUp, session.id)
            grant.verified_at = now - timedelta(days=38)
            grant.expires_at = grant.verified_at + timedelta(minutes=15)
            replays = (
                await db.scalars(select(AuthReplay).where(AuthReplay.session_id == session.id))
            ).all()
            for replay in replays:
                replay.valid_until = now - timedelta(days=2)
        async with database.sessions.begin() as db:
            replays_removed, sessions_removed = await cleanup_expired(db)
            assert replays_removed >= 1 and sessions_removed >= 1
        async with database.sessions() as db:
            assert await db.get(UserSession, session_id) is None
            assert await db.get(StepUp, session_id) is None
            assert await db.get(MFACredential, actor.user_id) is not None
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(RecoveryCode)
                    .where(RecoveryCode.user_id == actor.user_id)
                )
                == 10
            )
            assert (
                await db.scalar(
                    select(func.count())
                    .select_from(AuditEvent)
                    .where(
                        AuditEvent.actor_id == actor.user_id, AuditEvent.action == "mfa.confirmed"
                    )
                )
                == 1
            )
