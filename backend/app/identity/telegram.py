import hashlib
import hmac
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from urllib.parse import parse_qsl, urlsplit

from pydantic import BaseModel, ConfigDict, Field, StrictInt, ValidationError, field_validator

from app.core.errors import ApplicationError


def invalid_proof() -> ApplicationError:
    return ApplicationError("INIT_DATA_INVALID", "Данные Telegram не прошли проверку.", 401)


class TelegramUser(BaseModel):
    model_config = ConfigDict(extra="ignore", hide_input_in_errors=True)
    id: StrictInt = Field(gt=0, le=2**63 - 1)
    first_name: str = Field(default="", max_length=256)
    last_name: str | None = Field(default=None, max_length=256)
    username: str | None = Field(default=None, max_length=64)
    language_code: str | None = Field(default=None, max_length=32)
    photo_url: str | None = Field(default=None, max_length=2048)

    @field_validator("photo_url")
    @classmethod
    def safe_photo(cls, value: str | None) -> str | None:
        if value:
            url = urlsplit(value)
            if url.scheme != "https" or not url.hostname or url.username or url.password:
                return None
        return value


@dataclass(frozen=True, repr=False)
class TelegramProof:
    user: TelegramUser
    digest: bytes
    bot_id: int
    valid_until: datetime


def unique_json_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("Duplicate JSON fields")
    return result


def verify_init_data(
    raw: str, bot_token: str, *, max_age: int = 300, now: datetime | None = None
) -> TelegramProof:
    try:
        if len(raw.encode()) > 16384 or re.search(r"%(?![0-9a-fA-F]{2})", raw):
            raise invalid_proof()
        pairs = parse_qsl(
            raw,
            keep_blank_values=True,
            strict_parsing=True,
            encoding="utf-8",
            errors="strict",
            max_num_fields=32,
        )
        fields = dict(pairs)
        if len(fields) != len(pairs) or not {"hash", "auth_date", "user"} <= fields.keys():
            raise ValueError
        if any(
            not re.fullmatch(r"[a-z][a-z0-9_]{0,63}", k) or "\n" in v or "\r" in v for k, v in pairs
        ):
            raise ValueError
        supplied = fields.pop("hash")
        if not re.fullmatch(r"[a-fA-F0-9]{64}", supplied):
            raise ValueError
        check_string = "\n".join(f"{k}={v}" for k, v in sorted(fields.items()))
        key = hmac.digest(b"WebAppData", bot_token.encode(), "sha256")
        expected = hmac.digest(key, check_string.encode(), "sha256")
        if not hmac.compare_digest(expected, bytes.fromhex(supplied)):
            raise ValueError
        if not re.fullmatch(r"[0-9]{1,11}", fields["auth_date"]):
            raise ValueError
        current = now or datetime.now(UTC)
        age = current.timestamp() - int(fields["auth_date"])
        if age > max_age:
            raise ApplicationError("INIT_DATA_EXPIRED", "Откройте Mini App заново.", 401)
        if age < -30:
            raise ValueError
        user = TelegramUser.model_validate(
            json.loads(fields["user"], object_pairs_hook=unique_json_object)
        )
        bot_id = int(bot_token.split(":", 1)[0])
        # Fingerprint the canonical authenticated signature, not raw query ordering/encoding.
        digest = hashlib.sha256(str(bot_id).encode() + b"\0" + expected).digest()
        return TelegramProof(
            user,
            digest,
            bot_id,
            datetime.fromtimestamp(int(fields["auth_date"]), UTC) + timedelta(seconds=max_age),
        )
    except (ValueError, UnicodeError, ValidationError, TypeError, OverflowError, RecursionError):
        raise invalid_proof() from None
