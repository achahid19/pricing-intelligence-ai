from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, ForeignKey, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


class Workspace(Base):
    """
    The tenant. One Workspace : one User for now (see DECISIONS.md) —
    multi-user teams are a clean later extension, not built yet.

    Business-context fields (objectives, country, market, report_interval)
    are added in a later migration once the onboarding capture UI (Step 3)
    actually needs them — no point carrying empty columns before that.
    """
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc)
    )

    ai_provider_configs: Mapped[list["AiProviderConfig"]] = relationship(
        back_populates="workspace", cascade="all, delete-orphan"
    )


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
