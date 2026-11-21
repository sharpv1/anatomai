from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.api.health import Meta
from app.attempts.schemas import AttemptDTO, LearningResult, ReviewItem


class DTO(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Summary(DTO):
    completed_tests: int
    answered_count: int
    correct_count: int
    wrong_count: int
    skipped_count: int
    average_percent: int | None
    practice_seconds: int | None
    activity_streak_days: int
    period: Literal["all", "week", "month"]
    timezone: str
    data_scope: Literal["server_history"] = "server_history"
    calculated_at: datetime


class HistoryItem(DTO):
    id: UUID
    mode: Literal["learning", "exam"]
    discipline_id: UUID
    topic_id: UUID | None
    test_definition_id: UUID | None
    result: LearningResult
    activity_date: date
    activity_timezone: str


class Page(DTO):
    next_cursor: str | None
    has_more: bool


class Listing[T](DTO):
    data: list[T]
    page: Page
    meta: Meta


class ActivityDay(DTO):
    date: date
    completed_tests: int
    answered_count: int
    correct_count: int
    practice_seconds: int
    average_percent: int | None


class Activity(DTO):
    timezone: str
    date_policy: Literal["frozen_attempt_timezone"] = "frozen_attempt_timezone"
    start: date
    end: date
    days: list[ActivityDay]


class GroupProgress(DTO):
    id: UUID
    title: str
    completed_tests: int
    answered_count: int
    correct_count: int
    wrong_count: int
    skipped_count: int
    observed_questions: int
    average_percent: int | None
    best_percent: int | None
    ever_wrong_question_count: int
    unresolved_wrong_question_count: int


class TopicSummary(DTO):
    topic_id: UUID
    completed_count: int
    best_percent: int | None
    ever_wrong_question_count: int | None
    unresolved_wrong_question_count: int | None
    favorites_count: int | None = None
    favorites_status: Literal["not_configured"] = "not_configured"


class Progress(DTO):
    statistics: Summary
    unattributed_topic_responses: int
    source: Literal["immutable_attempts"] = "immutable_attempts"


class Recommendation(DTO):
    topic_id: UUID
    discipline_id: UUID
    title: str
    question_count: int
    reason: Literal["weak_topic"]
    observed_average_percent: int
    observed_attempts: int


class DailyTopic(DTO):
    local_date: date
    timezone: str
    topic_id: UUID | None
    title: str | None
    discipline_id: UUID | None
    question_count: int | None
    availability: Literal["available", "withdrawn", "empty"]
    catalog_version: int
    selector_version: Literal[1] = 1


class Achievement(DTO):
    code: str
    title: str
    state: Literal["unlocked", "locked", "not_configured"]
    condition: str
    progress: int | None
    target: int | None
    granted_at: None = None


class Home(DTO):
    statistics: Summary
    active_attempt: AttemptDTO | None
    recent_results: list[HistoryItem]


class ResultPage(DTO):
    items: list[ReviewItem]
    next_cursor: str | None
    has_more: bool
