import base64
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from admin_helpers import MFA_KEY, TOTP_SECRET
from pydantic import SecretStr, ValidationError

from app.admin.mfa import decrypt_secret, encrypt_secret, match_counter, recovery_hash, totp
from app.core.config import Settings
from app.core.errors import ApplicationError


def test_rfc4226_vectors_and_rfc6238_window():
    assert [totp(TOTP_SECRET, i) for i in range(3)] == ["755224", "287082", "359152"]
    now = datetime.fromtimestamp(59, UTC)
    assert match_counter(TOTP_SECRET, "287082", now, -1) == 1
    assert match_counter(TOTP_SECRET, "287082", now, 1) is None
    assert match_counter(TOTP_SECRET, "287082", datetime.fromtimestamp(121, UTC), -1) is None
    assert match_counter(TOTP_SECRET, "12345", now, -1) is None


@pytest.mark.parametrize("failure", ["user", "ciphertext", "key"])
def test_encrypted_secret_cannot_be_swapped_or_tampered(settings, failure):
    configured = settings.model_copy(update={"mfa_encryption_key": SecretStr(MFA_KEY)})
    user = uuid4()
    encrypted = encrypt_secret(configured, user, TOTP_SECRET)
    assert TOTP_SECRET.encode() not in encrypted
    assert decrypt_secret(configured, user, encrypted) == TOTP_SECRET
    if failure == "user":
        user = uuid4()
    if failure == "ciphertext":
        encrypted = encrypted[:-4] + b"AAAA"
    if failure == "key":
        configured = configured.model_copy(
            update={"mfa_encryption_key": SecretStr(base64.urlsafe_b64encode(b"n" * 32).decode())}
        )
    with pytest.raises(ApplicationError) as exc:
        decrypt_secret(configured, user, encrypted)
    assert exc.value.code == "MFA_UNAVAILABLE"


def test_recovery_hash_is_bound_to_user_and_not_a_raw_code():
    user, code = uuid4(), "synthetic-recovery-code-only"
    assert recovery_hash(user, code) != recovery_hash(uuid4(), code)
    assert len(recovery_hash(user, code)) == 32 and recovery_hash(user, code) != code.encode()


def test_mfa_key_validation_and_secret_redaction(settings):
    with pytest.raises(ValidationError) as exc:
        Settings(**{**settings.model_dump(), "mfa_encryption_key": "synthetic-invalid-key"})
    assert "synthetic-invalid-key" not in str(exc.value)
    assert (
        Settings(**{**settings.model_dump(), "mfa_encryption_key": ""}).mfa_encryption_key is None
    )


def test_key_reuse_and_non_interactive_provisioning_are_rejected(settings, monkeypatch):
    with pytest.raises(ValidationError):
        Settings(
            **{**settings.model_dump(), "csrf_signing_key": MFA_KEY, "mfa_encryption_key": MFA_KEY}
        )
    import sys

    from app.admin.provision import main

    monkeypatch.setattr(sys, "argv", ["provision", "--telegram-user-id", "123", "--confirm"])
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 2
