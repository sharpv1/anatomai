from datetime import UTC, datetime
from urllib.parse import parse_qsl, urlencode

import pytest
from identity_helpers import TEST_BOT_TOKEN, signed_data

from app.core.errors import ApplicationError
from app.identity.policy import authorize
from app.identity.security import LoginLimiter
from app.identity.telegram import verify_init_data


def test_fixed_hmac_vector_independently_generated_with_openssl():
    # Frozen offline test vector; no real bot or user credentials.
    raw = urlencode(
        {
            "auth_date": "1700000000",
            "user": '{"id":12345,"first_name":"A+B/Ю"}',
            "signature": "signed-field",
            "hash": "a644c0003eea1d8e8c737f2ee21bc8a765c27dfe4506a8eef277924b9df71743",
        }
    )
    proof = verify_init_data(raw, TEST_BOT_TOKEN, now=datetime.fromtimestamp(1700000000, UTC))
    assert proof.user.first_name == "A+B/Ю"


def test_valid_hmac_unicode_plus_signature_and_canonical_digest():
    raw = signed_data(extra={"signature": "plus+slash/equals="})
    proof = verify_init_data(raw, TEST_BOT_TOKEN)
    assert proof.user.id == 12345
    assert proof.user.first_name == "Test + Юзер"
    reordered = urlencode(list(reversed(parse_qsl(raw))))
    assert verify_init_data(reordered, TEST_BOT_TOKEN).digest == proof.digest
    with pytest.raises(ApplicationError):
        verify_init_data(raw.replace("signature=plus", "signature=other"), TEST_BOT_TOKEN)


@pytest.mark.parametrize("age,code", [(301, "INIT_DATA_EXPIRED"), (-31, "INIT_DATA_INVALID")])
def test_rejects_expired_and_future_signed_data(age, code):
    raw = signed_data(age=age)
    with pytest.raises(ApplicationError) as error:
        verify_init_data(
            raw, TEST_BOT_TOKEN, now=datetime.fromtimestamp(int(datetime.now(UTC).timestamp()), UTC)
        )
    assert error.value.code == code


@pytest.mark.parametrize("age", [0, 299, -29])
def test_valid_time_window(age):
    assert verify_init_data(signed_data(age=age), TEST_BOT_TOKEN).user.id == 12345


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "hash=123",
        "hash=" + "z" * 64 + "&auth_date=1&user=x",
        "a=%ZZ",
        "a=%FF",
        "a=b&broken",
        "x=" + "x" * 16385,
    ],
)
def test_rejects_malformed_query(raw):
    with pytest.raises(ApplicationError) as error:
        verify_init_data(raw, TEST_BOT_TOKEN)
    assert error.value.status_code == 401


@pytest.mark.parametrize(
    "user", [{"id": True}, {"id": 0}, {"id": -1}, {"id": "12345"}, {"id": 2**63}, []]
)
def test_strict_user_id(user):
    with pytest.raises(ApplicationError):
        verify_init_data(signed_data(user=user), TEST_BOT_TOKEN)


def test_wrong_bot_duplicate_keys_and_tampering():
    raw = signed_data()
    for candidate, token in (
        (raw, "99999999:another_synthetic_bot_token_abcdefghijk"),
        (raw + "&auth_date=1", TEST_BOT_TOKEN),
        (raw + "&hash=" + "0" * 64, TEST_BOT_TOKEN),
        (raw.replace("12345", "12346"), TEST_BOT_TOKEN),
        ("\ud800", TEST_BOT_TOKEN),
    ):
        with pytest.raises(ApplicationError):
            verify_init_data(candidate, token)


def test_duplicate_json_id_and_single_url_decode():
    with pytest.raises(ApplicationError):
        verify_init_data(signed_data(extra={"user": '{"id":12345,"id":67890}'}), TEST_BOT_TOKEN)
    raw = signed_data(user={"id": 12345, "first_name": "literal%2B / +"})
    assert verify_init_data(raw, TEST_BOT_TOKEN).user.first_name == "literal%2B / +"


@pytest.mark.parametrize(
    "roles,permission,code",
    [
        ({"student"}, "roles.manage", "ACCESS_DENIED"),
        ({"made_up_role"}, "identity.self.read", "ACCESS_DENIED"),
        ({"admin"}, "roles.manage", "MFA_REQUIRED"),
        ({"content_reviewer"}, "content.publish", "MFA_REQUIRED"),
    ],
)
def test_permissions_are_default_deny_and_admin_requires_mfa(roles, permission, code):
    with pytest.raises(ApplicationError) as error:
        authorize(roles, permission)
    assert error.value.code == code


def test_rate_limit_has_bounded_storage_and_expires():
    limiter = LoginLimiter(2)
    limiter.take("client", now=0)
    limiter.take("client", now=1)
    with pytest.raises(ApplicationError):
        limiter.take("client", now=2)
    limiter.take("client", now=61)
    for i in range(3000):
        limiter.take(str(i), now=62)
    assert len(limiter.windows) == 2048
