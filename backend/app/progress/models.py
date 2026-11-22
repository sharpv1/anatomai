from datetime import date, datetime
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DailyRecommendation(Base):
    __tablename__ = "daily_recommendations"
    __table_args__ = (CheckConstraint("selector_version=1 AND catalog_version>=1", name="version"),)
    user_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), primary_key=True
    )
    local_date: Mapped[date] = mapped_column(primary_key=True)
    topic_id: Mapped[UUID | None] = mapped_column(ForeignKey("topics.id", ondelete="RESTRICT"))
    timezone: Mapped[str] = mapped_column(String(64))
    catalog_version: Mapped[int]
    selector_version: Mapped[int] = mapped_column(Integer, server_default="1", default=1)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.clock_timestamp()
    )
