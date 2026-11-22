from pathlib import Path
from typing import Literal, Self
from urllib.parse import urlsplit

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MEDEXA_", extra="ignore", frozen=True, hide_input_in_errors=True
    )

    environment: Literal["development", "test"] = "development"
    db_host: str = Field(default="127.0.0.1", min_length=1, max_length=255)
    db_port: int = Field(default=5432, ge=1, le=65535)
    db_name: str = Field(min_length=19, max_length=63)
    db_user: str = Field(min_length=1, max_length=63)
    db_password: SecretStr
    db_pool_size: int = Field(default=3, ge=1, le=5)
    readiness_timeout_seconds: float = Field(default=3, ge=0.1, le=10)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    telegram_bot_token: SecretStr | None = None
    csrf_signing_key: SecretStr | None = None
    content_cursor_signing_key: SecretStr | None = None
    content_asset_delivery_enabled: bool = False
    import_storage_dir: Path | None = None
    mfa_encryption_key: SecretStr | None = None
    app_origin: str = "https://localhost"
    init_data_max_age_seconds: int = Field(default=300, ge=1, le=300)
    session_absolute_seconds: int = Field(default=604800, ge=60, le=604800)
    session_idle_seconds: int = Field(default=86400, ge=60, le=86400)
    login_rate_limit: int = Field(default=10, ge=1, le=100)

    @field_validator(
        "telegram_bot_token",
        "csrf_signing_key",
        "content_cursor_signing_key",
        "mfa_encryption_key",
        mode="before",
    )
    @classmethod
    def blank_secret_is_disabled(cls, value: object) -> object:
        return None if value == "" else value

    @field_validator("csrf_signing_key", "content_cursor_signing_key")
    @classmethod
    def strong_signing_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None and len(value.get_secret_value().encode()) < 32:
            raise ValueError("Signing key must contain at least 32 bytes")
        return value

    @field_validator("import_storage_dir", mode="before")
    @classmethod
    def import_directory(cls, value: object) -> object:
        if value in (None, ""):
            return None
        path = Path(str(value))
        if not path.is_absolute() or path in (
            Path("/"),
            Path("/tmp"),
            Path("/app"),
            Path("/workspace"),
        ):
            raise ValueError("Use a dedicated absolute private import directory")
        return path

    @model_validator(mode="after")
    def independent_mfa_key(self) -> Self:
        if self.mfa_encryption_key is not None:
            key = self.mfa_encryption_key.get_secret_value()
            if any(
                other is not None and key == other.get_secret_value()
                for other in (
                    self.telegram_bot_token,
                    self.csrf_signing_key,
                    self.content_cursor_signing_key,
                )
            ):
                raise ValueError("MFA requires its own encryption key")
        return self

    @field_validator("mfa_encryption_key")
    @classmethod
    def fernet_key(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            from cryptography.fernet import Fernet

            try:
                Fernet(value.get_secret_value().encode("ascii"))
            except (ValueError, UnicodeError):
                raise ValueError("Use a separate Fernet MFA encryption key") from None
        return value

    @field_validator("telegram_bot_token")
    @classmethod
    def bot_token_format(cls, value: SecretStr | None) -> SecretStr | None:
        if value is not None:
            import re

            if not re.fullmatch(
                r"[1-9][0-9]{0,18}:[A-Za-z0-9_-]{20,128}", value.get_secret_value()
            ):
                raise ValueError("Invalid bot token format")
            if int(value.get_secret_value().split(":")[0]) > 2**63 - 1:
                raise ValueError("Invalid bot ID")
        return value

    @field_validator("app_origin")
    @classmethod
    def https_origin(cls, value: str) -> str:
        parsed = urlsplit(value)
        if (
            parsed.scheme != "https"
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.path not in ("", "/")
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("Use an exact HTTPS origin without credentials or path")
        return value.rstrip("/")

    @field_validator("db_name")
    @classmethod
    def isolated_database(cls, value: str) -> str:
        if not value.startswith("medexa_foundation_") or not value.isascii():
            raise ValueError("Use a dedicated medexa_foundation_ database")
        if not all(character.isalnum() or character == "_" for character in value):
            raise ValueError("Database names must contain only letters, digits and underscores")
        return value

    @field_validator("db_password")
    @classmethod
    def nonempty_password(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value() or value.get_secret_value() == "REPLACE_ME":
            raise ValueError("Set a nonempty local database password")
        return value

    @property
    def database_url(self) -> URL:
        return URL.create(
            "postgresql+asyncpg",
            username=self.db_user,
            password=self.db_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
