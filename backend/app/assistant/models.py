from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class AssistantToolCall(Base):
    """
    A write-tool call the agentic chat assistant has proposed — the
    security boundary for its "AI proposes, human approves" flow, the same
    pattern CompetitorSite.status/ProductMatch.status already established
    elsewhere in this app. `arguments` is exactly what the AI provider
    returned at propose time and is never accepted again from the client —
    PATCH /assistant/tool-calls/{id} takes only an action, so a tampered
    request has no channel to substitute different arguments than what was
    actually proposed and shown to the user; approval always executes
    against the arguments already stored here. `display` is a
    server-resolved, human-readable summary (e.g. a resolved site name
    instead of a bare id) built once at propose time so the frontend never
    has to render raw JSON. `tier` mirrors model_catalog.py's cost tier —
    this app has no real per-call cost tracking, so this is deliberately
    just the same lightweight signal Settings' model picker already shows,
    not a new metering system.
    """
    __tablename__ = "assistant_tool_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )

    tool_name: Mapped[str] = mapped_column(Text, nullable=False)
    arguments: Mapped[dict] = mapped_column(JSONB, nullable=False)
    display: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # proposed|executed|dismissed|failed
    status: Mapped[str] = mapped_column(Text, nullable=False, default="proposed")

    ai_provider: Mapped[str] = mapped_column(Text, nullable=False)
    model: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[str] = mapped_column(Text, nullable=False)  # low|medium|high

    result_summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
