from typing import Any
from uuid import UUID

from fastapi import APIRouter, Request, Response

from app.admin import drafts
from app.admin.schemas import (
    DefinitionBody,
    DisciplineBody,
    QuestionBody,
    QuestionCreate,
    SourceBody,
    TopicBody,
)
from app.content.api import Cursor, Limit, Search
from app.content.models import ContentSource, Discipline, Topic
from app.content.models import TestDefinition as Definition
from app.content.schemas import Listing
from app.identity.policy import access
from app.identity.schemas import Envelope

router = APIRouter(prefix="/api/v1/admin", tags=["medical drafts"])


@router.get("/disciplines", response_model=Listing[dict[str, Any]])
@access("content.admin.read")
async def list_discipline(
    request: Request,
    response: Response,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Any:
    return await drafts.catalog_list(request, response, Discipline, query, limit, cursor)


@router.get("/disciplines/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.admin.read")
async def get_discipline(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_get(request, response, Discipline, entity_id)


@router.post("/disciplines", response_model=Envelope[dict[str, Any]], status_code=201)
@access("content.draft.write")
async def create_discipline(body: DisciplineBody, request: Request, response: Response) -> Any:
    return await drafts.catalog_save(request, response, Discipline, body)


@router.patch("/disciplines/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def update_discipline(
    entity_id: UUID, body: DisciplineBody, request: Request, response: Response
) -> Any:
    return await drafts.catalog_save(request, response, Discipline, body, entity_id)


@router.delete("/disciplines/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def archive_discipline(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_archive(request, response, Discipline, entity_id)


@router.get("/topics", response_model=Listing[dict[str, Any]])
@access("content.admin.read")
async def list_topic(
    request: Request,
    response: Response,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Any:
    return await drafts.catalog_list(request, response, Topic, query, limit, cursor)


@router.get("/topics/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.admin.read")
async def get_topic(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_get(request, response, Topic, entity_id)


@router.post("/topics", response_model=Envelope[dict[str, Any]], status_code=201)
@access("content.draft.write")
async def create_topic(body: TopicBody, request: Request, response: Response) -> Any:
    return await drafts.catalog_save(request, response, Topic, body)


@router.patch("/topics/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def update_topic(
    entity_id: UUID, body: TopicBody, request: Request, response: Response
) -> Any:
    return await drafts.catalog_save(request, response, Topic, body, entity_id)


@router.delete("/topics/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def archive_topic(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_archive(request, response, Topic, entity_id)


@router.get("/test-definitions", response_model=Listing[dict[str, Any]])
@access("content.admin.read")
async def list_definition(
    request: Request,
    response: Response,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Any:
    return await drafts.catalog_list(request, response, Definition, query, limit, cursor)


@router.get("/test-definitions/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.admin.read")
async def get_definition(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_get(request, response, Definition, entity_id)


@router.post("/test-definitions", response_model=Envelope[dict[str, Any]], status_code=201)
@access("content.draft.write")
async def create_definition(body: DefinitionBody, request: Request, response: Response) -> Any:
    return await drafts.catalog_save(request, response, Definition, body)


@router.patch("/test-definitions/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def update_definition(
    entity_id: UUID, body: DefinitionBody, request: Request, response: Response
) -> Any:
    return await drafts.catalog_save(request, response, Definition, body, entity_id)


@router.delete("/test-definitions/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def archive_definition(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_archive(request, response, Definition, entity_id)


@router.get("/sources", response_model=Listing[dict[str, Any]])
@access("content.admin.read")
async def list_source(
    request: Request,
    response: Response,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Any:
    return await drafts.catalog_list(request, response, ContentSource, query, limit, cursor)


@router.get("/sources/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.admin.read")
async def get_source(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_get(request, response, ContentSource, entity_id)


@router.post("/sources", response_model=Envelope[dict[str, Any]], status_code=201)
@access("content.draft.write")
async def create_source(body: SourceBody, request: Request, response: Response) -> Any:
    return await drafts.catalog_save(request, response, ContentSource, body)


@router.patch("/sources/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def update_source(
    entity_id: UUID, body: SourceBody, request: Request, response: Response
) -> Any:
    return await drafts.catalog_save(request, response, ContentSource, body, entity_id)


@router.delete("/sources/{entity_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def archive_source(entity_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.catalog_archive(request, response, ContentSource, entity_id)


@router.get("/questions", response_model=Listing[dict[str, Any]])
@access("content.admin.read")
async def questions(
    request: Request,
    response: Response,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Any:
    return await drafts.revision_list(request, response, None, query, limit, cursor)


@router.post("/questions", response_model=Envelope[dict[str, Any]], status_code=201)
@access("content.draft.write")
async def create_question(body: QuestionCreate, request: Request, response: Response) -> Any:
    return await drafts.save_revision(request, response, body)


@router.get("/questions/{question_id}", response_model=Envelope[dict[str, Any]])
@access("content.admin.read")
async def question(question_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.question_get(request, response, question_id)


@router.get("/questions/{question_id}/revisions", response_model=Listing[dict[str, Any]])
@access("content.admin.read")
async def revisions(
    question_id: UUID,
    request: Request,
    response: Response,
    query: Search = "",
    limit: Limit = 20,
    cursor: Cursor = None,
) -> Any:
    return await drafts.revision_list(request, response, question_id, query, limit, cursor)


@router.post(
    "/questions/{question_id}/revisions", response_model=Envelope[dict[str, Any]], status_code=201
)
@access("content.draft.write")
async def create_revision(
    question_id: UUID, body: QuestionBody, request: Request, response: Response
) -> Any:
    return await drafts.save_revision(request, response, body, question_id=question_id)


@router.get("/question-revisions/{revision_id}", response_model=Envelope[dict[str, Any]])
@access("content.admin.read")
async def revision(revision_id: UUID, request: Request, response: Response) -> Any:
    return await drafts.revision_get(request, response, revision_id)


@router.patch("/question-revisions/{revision_id}", response_model=Envelope[dict[str, Any]])
@access("content.draft.write")
async def edit_revision(
    revision_id: UUID, body: QuestionBody, request: Request, response: Response
) -> Any:
    return await drafts.save_revision(request, response, body, revision_id=revision_id)
