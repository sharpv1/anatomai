from datetime import datetime
from typing import Annotated, Any, Literal, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    SerializerFunctionWrapHandler,
    model_serializer,
    model_validator,
)

from app.admin.schemas import Body


class Start(Body):
    mode: Literal["learning"] = "learning"
    kind: Literal["regular"] = "regular"
    discipline_id: UUID | None = None
    topic_id: UUID | None = None
    test_definition_id: UUID | None = None

    @model_validator(mode="after")
    def one_scope(self) -> Self:
        if (
            sum(v is not None for v in (self.discipline_id, self.topic_id, self.test_definition_id))
            != 1
        ):
            raise ValueError("Select exactly one discipline, topic or test")
        return self


class Submit(Body):
    selected_option_ids: Annotated[list[UUID], Field(min_length=1, max_length=1)]


class ItemAction(Body):
    item_id: UUID


class Abandon(Body):
    reason: Literal["user_exit"] = "user_exit"


class Finish(Body):
    pass


# Output states are separate allowlists: an unanswered item cannot carry feedback.


class Output(BaseModel):
    model_config = ConfigDict(extra="forbid")


class OptionView(Output):
    id: UUID
    position: Annotated[int, Field(ge=0, le=7)]
    code: str
    text: str


class Feedback(Output):
    is_correct: bool
    correct_option_ids: Annotated[list[UUID], Field(min_length=1, max_length=1)]
    explanation: str | None = None

    @model_serializer(mode="wrap")
    def optional_explanation(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.explanation is None:
            data.pop("explanation", None)
        return data


class ItemView(Output):
    id: UUID
    question_id: UUID
    revision_id: UUID
    position: int
    text: str
    options: Annotated[list[OptionView], Field(min_length=2, max_length=8)]


class Unanswered(ItemView):
    state: Literal["awaiting_answer"]
    selected_option_ids: Annotated[list[UUID], Field(max_length=0)]


class Checked(ItemView):
    state: Literal["checked"]
    selected_option_ids: Annotated[list[UUID], Field(min_length=1, max_length=1)]
    feedback: Feedback


class LearningResult(Output):
    attempt_id: UUID
    title: str
    total: Annotated[int, Field(ge=1, le=5000)]
    correct: Annotated[int, Field(ge=0)]
    wrong: Annotated[int, Field(ge=0)]
    skipped: Annotated[int, Field(ge=0)]
    answered: Annotated[int, Field(ge=0)]
    percent: Annotated[int, Field(ge=0, le=100)]
    duration_seconds: Annotated[int, Field(ge=0)]
    started_at: datetime
    finalized_at: datetime
    finish_reason: Literal["last_question", "user_finish"]


class AttemptView(Output):
    id: UUID
    mode: Literal["learning"]
    status: Literal["in_progress", "completed", "abandoned"]
    version: Annotated[int, Field(ge=1)]
    title: str
    scope: Literal["discipline", "topic", "test"]
    discipline_id: UUID
    topic_id: UUID | None
    test_definition_id: UUID | None
    total: Annotated[int, Field(ge=1, le=5000)]
    current_position: int
    started_at: datetime
    current_item: Annotated[Unanswered | Checked, Field(discriminator="state")] | None
    result: LearningResult | None = None

    @model_validator(mode="after")
    def valid_state(self) -> Self:
        if (self.status == "completed") != (self.result is not None) or (
            self.status == "in_progress"
        ) != (self.current_item is not None):
            raise ValueError("Invalid learning response projection")
        if self.current_item is not None and self.current_item.position != self.current_position:
            raise ValueError("Item does not match the cursor")
        return self

    @model_serializer(mode="wrap")
    def optional_result(self, handler: SerializerFunctionWrapHandler) -> dict[str, Any]:
        data: dict[str, Any] = handler(self)
        if self.result is None:
            data.pop("result", None)
        return data
