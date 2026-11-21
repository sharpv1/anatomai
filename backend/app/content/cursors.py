import base64
import hashlib
import hmac
import json
import time

from app.core.errors import ApplicationError


def normalize(value: str) -> str:
    import unicodedata

    return unicodedata.normalize("NFC", value).lower().replace("ё", "е").strip()


def filter_hash(filters: dict[str, str | int | None]) -> str:
    return hashlib.sha256(
        json.dumps(filters, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def encode_cursor(
    key: str, *, version: int, scope: str, position: int, entity_id: str, now: int | None = None
) -> str:
    body = json.dumps(
        {
            "v": version,
            "f": scope,
            "p": position,
            "id": entity_id,
            "exp": (int(time.time()) if now is None else now) + 3600,
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    signature = hmac.digest(key.encode(), b"medexa-content-cursor-v1\0" + body, "sha256")
    return base64.urlsafe_b64encode(body + signature).rstrip(b"=").decode()


def decode_cursor(raw: str, key: str, *, version: int, scope: str) -> tuple[int, str]:
    try:
        if len(raw) > 2048 or not raw.isascii():
            raise ValueError
        decoded = base64.b64decode(raw + "=" * (-len(raw) % 4), altchars=b"-_", validate=True)
        body, signature = decoded[:-32], decoded[-32:]
        expected = hmac.digest(key.encode(), b"medexa-content-cursor-v1\0" + body, "sha256")
        if not hmac.compare_digest(signature, expected):
            raise ValueError
        data = json.loads(body)
        if (
            not isinstance(data, dict)
            or set(data) != {"v", "f", "p", "id", "exp"}
            or data["f"] != scope
            or type(data["exp"]) is not int
            or data["exp"] < time.time()
            or type(data["v"]) is not int
            or type(data["p"]) is not int
            or data["p"] < 0
            or not isinstance(data["id"], str)
        ):
            raise ValueError
        if data["v"] != version:
            raise ApplicationError(
                "CATALOG_CHANGED", "Каталог обновился. Загрузите список заново.", 409
            )
        from uuid import UUID

        return data["p"], str(UUID(data["id"]))
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ApplicationError("INVALID_CURSOR", "Некорректный или истёкший cursor.", 400) from None
