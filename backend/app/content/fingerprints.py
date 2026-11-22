import hashlib
import json

from app.admin.schemas import QuestionBody


def fingerprint(body: QuestionBody) -> str:
    return hashlib.sha256(
        json.dumps(
            body.model_dump(mode="json", exclude={"external_id"}),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def content_hash(body: QuestionBody, *, include_key: bool = True) -> str:
    value = {
        "kind": body.kind,
        "text": body.text,
        "options": [
            {
                "code": option.code,
                "text": option.text,
                **({"correct": option.is_correct} if include_key else {}),
            }
            for option in body.options
        ],
    }
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()
