from collections.abc import Mapping
from typing import Any
from uuid import UUID

from fastapi import Request
from sqlalchemy import Select, and_, func, or_, select
from sqlalchemy.engine import RowMapping
from sqlalchemy.ext.asyncio import AsyncSession

from app.content.cursors import decode_cursor, encode_cursor, filter_hash, normalize
from app.content.models import CatalogState
from app.content.schemas import Listing, Page
from app.core.errors import ApplicationError
from app.identity.api import meta
from app.identity.dependencies import current_db


def not_found() -> ApplicationError:
    return ApplicationError("NOT_FOUND", "Материал не найден.", 404)


def search(statement: Select[Any], column: Any, query: str) -> Select[Any]:
    for word in normalize(query).split():
        statement = statement.where(column.contains(word, autoescape=True))
    return statement


class ContentReader:
    def __init__(self, request: Request) -> None:
        self.request = request
        self.db: AsyncSession = getattr(request.state, "content_db", None) or current_db(request)
        key = request.app.state.settings.content_cursor_signing_key
        if key is None:
            raise ApplicationError("CONTENT_NOT_CONFIGURED", "Контент ещё не настроен.", 503)
        self.key: str = key.get_secret_value()
        self.version = 0

    async def begin(self) -> None:
        self.version = await self._version()

    async def _version(self) -> int:
        version = await self.db.scalar(select(CatalogState.version).where(CatalogState.id == 1))
        if version is None:
            raise ApplicationError("SERVICE_NOT_READY", "Каталог ещё не готов.", 503)
        return version

    async def finish(self) -> None:
        if await self._version() != self.version:
            raise ApplicationError(
                "CATALOG_CHANGED", "Каталог обновился. Загрузите список заново.", 409
            )

    async def rows(
        self,
        statement: Select[Any],
        *,
        scope: str,
        filters: Mapping[str, str | int | None],
        limit: int,
        cursor: str | None,
    ) -> tuple[list[RowMapping], Page]:
        owner: str | None = None
        if hasattr(self.request.state, "identity"):
            owner = str(self.request.state.identity.user.id)
        fingerprint = filter_hash({"route": scope, "owner": owner, **filters})
        total = await self.db.scalar(
            select(func.count()).select_from(statement.order_by(None).subquery())
        )
        position = statement.selected_columns.sort_position
        entity = statement.selected_columns.sort_id
        if cursor is not None:
            last_pos, last_id = decode_cursor(
                cursor, self.key, version=self.version, scope=fingerprint
            )
            statement = statement.where(
                or_(position > last_pos, and_(position == last_pos, entity > UUID(last_id)))
            )
        fetched = (
            (await self.db.execute(statement.order_by(position, entity).limit(limit + 1)))
            .mappings()
            .all()
        )
        more = len(fetched) > limit
        rows = list(fetched[:limit])
        next_cursor = None
        if more:
            last = rows[-1]
            next_cursor = encode_cursor(
                self.key,
                version=self.version,
                scope=fingerprint,
                position=last["sort_position"],
                entity_id=str(last["sort_id"]),
            )
        return rows, Page(next_cursor=next_cursor, has_more=more, total=total or 0)

    async def listing[T](self, data: list[T], page: Page) -> Listing[T]:
        await self.finish()
        return Listing[T](
            data=data, page=page, meta=meta(self.request), catalog_version=self.version
        )


async def reader(request: Request) -> ContentReader:
    result = ContentReader(request)
    await result.begin()
    return result
