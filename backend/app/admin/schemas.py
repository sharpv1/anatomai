from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictBool,
    StringConstraints,
    field_validator,
    model_validator,
)

Title = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=512)]
Slug = Annotated[str, StringConstraints(pattern=r"^[a-z0-9][a-z0-9-]{0,127}$")]
Token = Annotated[str, StringConstraints(pattern=r"^[a-z0-9_-]{1,64}$")]
Text = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
Position = Annotated[int, Field(ge=0, le=1000000)]


class Body(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)


class DisciplineBody(Body):
    slug: Slug
    title: Title
    icon_key: Token
    color_token: Literal["blue", "mint", "violet", "orange"]
    position: Position = 0


class TopicBody(Body):
    discipline_id: UUID
    category_id: UUID | None = None
    slug: Slug
    title: Title
    position: Position = 0


class DefinitionBody(Body):
    topic_id: UUID
    slug: Slug
    title: Title
    exam_duration_seconds: Annotated[int, Field(ge=1, le=86400)]
    question_limit: Annotated[int, Field(ge=1, le=5000)] | None = None
    internal_difficulty: Annotated[str, StringConstraints(max_length=32)] | None = None


class SourceBody(Body):
    slug: Slug
    title: Title
    attribution: Text
    license_reference: Text | None = None

    @field_validator("license_reference", mode="before")
    @classmethod
    def blank_license(cls, value: object) -> object:
        return None if isinstance(value, str) and not value.strip() else value


class OptionBody(Body):
    code: Annotated[str, StringConstraints(pattern=r"^[A-H]$")]
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=2000)]
    is_correct: StrictBool

    @field_validator("text")
    @classmethod
    def utf8_limit(cls, value: str) -> str:
        if len(value.encode()) > 2000:
            raise ValueError("Option exceeds UTF-8 byte limit")
        return value


class QuestionBody(Body):
    kind: Literal["single_choice", "multiple_choice"] = "single_choice"
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=8000)]
    explanation: Annotated[str, StringConstraints(max_length=16000)] | None = None
    license_reference: Text | None = None
    source_id: UUID | None = None
    source_reference: Text | None = None
    source_page: Annotated[str, StringConstraints(max_length=128)] | None = None
    options: Annotated[list[OptionBody], Field(min_length=2, max_length=8)]

    @field_validator(
        "source_id", "source_reference", "source_page", "license_reference", mode="before"
    )
    @classmethod
    def optional_metadata(cls, value: object) -> object:
        if isinstance(value, str):
            value = value.strip()
            return value or None
        return value

    @model_validator(mode="after")
    def validate_question(self) -> Self:
        if len(self.text.encode()) > 8000:
            raise ValueError("Question exceeds UTF-8 byte limit")
        if len(set(option.code for option in self.options)) != len(self.options):
            raise ValueError("Duplicate option code")
        correct = sum(option.is_correct for option in self.options)
        if correct < 1 or (self.kind == "single_choice" and correct != 1):
            raise ValueError("Explicit valid answer key required")
        return self


class QuestionCreate(QuestionBody):
    external_id: Annotated[str, StringConstraints(min_length=1, max_length=128)] | None = None
