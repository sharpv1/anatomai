from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.api.health import Meta


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Page(DTO):
    next_cursor: str | None
    has_more: bool
    total: int


class Listing[T](DTO):
    data: list[T]
    page: Page
    meta: Meta
    catalog_version: int


class DisciplineDTO(DTO):
    id: UUID
    slug: str
    title: str
    icon_key: str
    color_token: str
    question_count: int
    topic_count: int
    note_count: int


class CategoryDTO(DTO):
    id: UUID
    discipline_id: UUID
    slug: str
    title: str
    topic_count: int


class TopicDTO(DTO):
    id: UUID
    discipline_id: UUID
    category_id: UUID | None
    slug: str
    title: str
    question_count: int
    test_definition_id: UUID | None
    available_modes: list[Literal["learning", "exam"]]


class TestDTO(DTO):
    id: UUID
    topic_id: UUID
    slug: str
    title: str
    exam_duration_seconds: int
    question_count: int
    available_modes: list[Literal["learning", "exam"]]


class SafeOptionDTO(DTO):
    id: UUID
    position: int
    code: str
    text: str


class ExamQuestionDTO(DTO):
    question_id: UUID
    revision_id: UUID
    number: int
    kind: Literal["single_choice"]
    text: str
    options: list[SafeOptionDTO]


class LearningQuestionDTO(DTO):
    """Safe before submission. Feedback is a separate future attempt-service response."""

    question_id: UUID
    revision_id: UUID
    number: int
    kind: Literal["single_choice"]
    text: str
    options: list[SafeOptionDTO]


class ReferenceQuestionDTO(DTO):
    question_id: UUID
    revision_id: UUID
    number: int
    kind: Literal["single_choice"]
    text: str
    options: list[SafeOptionDTO]
    correct_option_ids: list[UUID]


class NoteSummaryDTO(DTO):
    id: UUID
    discipline_id: UUID
    topic_id: UUID | None
    title: str


class NoteDTO(NoteSummaryDTO):
    revision_id: UUID
    body: str | None
    body_format: Literal["plain_text"] = "plain_text"
    asset_id: UUID | None
    download_available: bool = False
