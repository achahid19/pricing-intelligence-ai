from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Workspace(Base):
    """
    The tenant. One Workspace : one User for now (see DECISIONS.md) —
    multi-user teams are a clean later extension, not built yet.

    Business-context fields below are deliberately all nullable — a
    freshly-signed-up workspace has none of them set, and the onboarding
    flow (Step 3) is exactly what fills them in. `objectives_selected` is a
    JSON list rather than an enum column on purpose (see DECISIONS.md):
    stays open-ended as new objectives emerge, no migration needed to add
    one.
    """
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)

    objectives_selected: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    objectives_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    country: Mapped[str | None] = mapped_column(Text, nullable=True)
    market: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    ai_provider_configs: Mapped[list["AiProviderConfig"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )

    @property
    def onboarding_completed(self) -> bool:
        """Onboarding is done once there's at least one objective and a
        country — the two fields discovery/reports actually key off of.
        market/notes stay optional even after onboarding."""
        return bool(self.objectives_selected) and bool(self.country)


class AiProviderConfig(Base):
    """
    A workspace's own AI provider credential — user-supplied, billed to
    them, never a shared app-level key. `encrypted_api_key` is Fernet
    ciphertext (see app/workspace/encryption.py); the raw key is never
    stored, logged, or echoed back to the frontend.

    A workspace may have configs for more than one provider on file, but
    only one is `is_active` at a time — that's the one ai_client.py uses.
    """
    __tablename__ = "ai_provider_configs"

    id: Mapped[int] = mapped_column(primary_key=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider: Mapped[str] = mapped_column(Text, nullable=False)  # "openai" | "google" | "anthropic"
    encrypted_api_key: Mapped[str] = mapped_column(Text, nullable=False)
    model_override: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    workspace: Mapped["Workspace"] = relationship(back_populates="ai_provider_configs")
