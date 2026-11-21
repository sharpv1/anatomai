"""Synthetic signing fixtures only; never imported by app/ or production code."""

import hashlib
import hmac
import json
import time
from urllib.parse import urlencode
from uuid import uuid4

TEST_BOT_TOKEN = "42424242:synthetic_test_token_abcdefghijklmnopqrstuvwxyz"
TEST_CSRF_KEY = "synthetic-test-csrf-key-" + "x" * 40
ORIGIN = "https://miniapp.test"


def signed_data(user_id=12345, *, age=0, user=None, extra=None, token=TEST_BOT_TOKEN):
    fields = {
        "auth_date": str(int(time.time()) - age),
        "query_id": str(uuid4()),
        "user": json.dumps(
            user
            if user is not None
            else {
                "id": user_id,
                "first_name": "Test + Юзер",
                "username": "synthetic",
                "photo_url": "https://example.test/avatar.png",
            },
            ensure_ascii=False,
            separators=(",", ":"),
        ),
    }
    if extra:
        fields.update(extra)
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    fields["hash"] = hmac.new(
        secret, "\n".join(f"{key}={fields[key]}" for key in sorted(fields)).encode(), hashlib.sha256
    ).hexdigest()
    return urlencode(fields)
