"""Synthetic secrets and authenticated actors, never shipped in the runtime image."""

import base64
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from httpx import AsyncClient

from app.admin.mfa import totp

MFA_KEY = base64.urlsafe_b64encode(b"m" * 32).decode()
TOTP_SECRET = base64.b32encode(b"12345678901234567890").decode()


@dataclass
class AdminActor:
    client: AsyncClient
    user_id: UUID
    telegram_id: int
    headers: dict[str, str]
    app: Any
    settings: Any
    clock: list[datetime]
    codes: list[str]
    grant: Any = None

    def code(self) -> str:
        return totp(TOTP_SECRET, int(self.clock[0].timestamp()) // 30)

    async def write_headers(self) -> dict[str, str]:
        response = await self.client.get("/api/v1/admin/disciplines")
        assert response.status_code == 200, response.text
        return {**self.headers, "If-Match": response.headers["etag"]}


async def source(actor: AdminActor) -> dict[str, Any]:
    body = {
        "slug": uuid4().hex,
        "title": "SYNTHETIC SOURCE " + uuid4().hex,
        "attribution": "TEST ONLY",
        "license_reference": None,
    }
    response = await actor.client.post(
        "/api/v1/admin/sources", json=body, headers=await actor.write_headers()
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


def question(source_id: str) -> dict[str, Any]:
    return {
        "text": "SYNTHETIC QUESTION",
        "source_id": source_id,
        "source_reference": "TEST ONLY",
        "explanation": None,
        "kind": "single_choice",
        "options": [
            {"code": "A", "text": "SYNTHETIC A", "is_correct": True},
            {"code": "B", "text": "SYNTHETIC B", "is_correct": False},
        ],
    }
