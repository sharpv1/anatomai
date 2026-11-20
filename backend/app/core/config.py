from typing import Literal

from pydantic import Field, SecretStr, field_validator
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
