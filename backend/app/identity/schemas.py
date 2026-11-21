import re
from datetime import datetime
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, SecretStr, model_validator

from app.api.health import Meta


def validate_timezone(value: str) -> str:
    try:
        ZoneInfo(value)
    except (ZoneInfoNotFoundError, ValueError):
        raise ValueError("Unknown IANA timezone") from None
    return value


def validate_language(value: str) -> str:
    if not re.fullmatch(r"[a-zA-Z]{2,3}(?:-[a-zA-Z0-9]{2,8})*", value):
        raise ValueError("Invalid language code")
    return value


class LoginBody(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    init_data: SecretStr
    timezone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def validate_preferences(self) -> "LoginBody":
        if self.timezone is not None:
            validate_timezone(self.timezone)
        if self.language is not None:
            validate_language(self.language)
        return self


class Preferences(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    timezone: str | None = Field(default=None, max_length=64)
    language: str | None = Field(default=None, max_length=32)

    @model_validator(mode="after")
    def nonempty(self) -> "Preferences":
        if not self.model_fields_set or any(
            getattr(self, name) is None for name in self.model_fields_set
        ):
            raise ValueError("Provide at least one non-null preference")
        if self.timezone is not None:
            validate_timezone(self.timezone)
        if self.language is not None:
            validate_language(self.language)
        return self


class UserView(BaseModel):
    id: UUID
    telegram_user_id: str
    first_name: str
    last_name: str | None
    username: str | None
    photo_url: str | None
    language: str
    timezone: str
    version: int
    roles: list[str]


class SessionView(BaseModel):
    id: UUID
    user: UserView
    expires_at: datetime
    idle_expires_at: datetime
    csrf_token: str


class SessionSummary(BaseModel):
    id: UUID
    created_at: datetime
    last_seen_at: datetime
    expires_at: datetime
    idle_expires_at: datetime
    current: bool


class Envelope[T](BaseModel):
    data: T
    meta: Meta
