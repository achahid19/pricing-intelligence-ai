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
    # The business's own site — doubles as future context for AI (and later
    # a seed for the "AI reads your own site to build your catalog" import
    # path), not just a display field.
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    report_interval_hours: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Opt-in: before each scheduled report, re-discover + re-match every
    # saved competitor site first. NULL/false both mean "off" forever, same
    # as report_interval_hours itself — a pure user preference, not a
    # system-computed field, so no backfill-then-lock migration needed.
    refresh_before_report: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Set once, the moment the automated onboarding pipeline (reporting/
    # service.py's run_full_pipeline) is enqueued for this workspace's
    # first-ever product — never unset, never re-checked against product
    # count again, so the pipeline only ever runs unprompted this one time.
    # NULL means it hasn't happened yet; no backfill needed since no
    # existing row could ever have had this happen before this column did.
    onboarding_pipeline_triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Live status of the most recent run_full_pipeline call (reporting/
    # service.py) — the pipeline runs entirely server-side (BackgroundTasks
    # or the scheduler), with no frontend promise for the existing
    # ActivityProvider to wrap, so this is what a polling frontend reads to
    # surface it in that same UI instead of it being silently invisible.
    # Only ever tracks the single most-recent run, not a history — full
    # detail already lives in DiscoveryRun/CompetitorReport for anyone who
    # digs further.
    pipeline_status: Mapped[str | None] = mapped_column(Text, nullable=True)  # "running"|"completed"|"failed"|"cancelled"
    pipeline_trigger_source: Mapped[str | None] = mapped_column(Text, nullable=True)  # "onboarding"|"scheduled"
    pipeline_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    pipeline_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    pipeline_report_id: Mapped[int | None] = mapped_column(
        ForeignKey("competitor_reports.id", ondelete="SET NULL"), nullable=True
    )
    # Per-step plan/progress for the current pipeline_status="running" run
    # (or the last completed one) — a list of {"id", "label", "status"}
    # dicts, "status" one of "pending"|"done"|"error"|"cancelled". Rebuilt
    # from scratch at the start of every run_full_pipeline() call, not
    # accumulated across runs. Not wrapped in SQLAlchemy's MutableList —
    # every writer reassigns the whole list rather than mutating in place,
    # same reasoning as objectives_selected above never needing that wrapper.
    pipeline_substeps: Mapped[list[dict] | None] = mapped_column(JSONB, nullable=True)
    # Set by POST /reporting/pipeline/cancel while pipeline_status=="running";
    # checked cooperatively at natural checkpoints in run_full_pipeline and
    # discovery/service.py's refresh_saved_sites (after the current step,
    # never mid-AI-call — there's no way to interrupt an in-flight request
    # to the AI provider, only to skip starting the next one). Reset to
    # False at the start of every new run, so a stale request from a
    # previous run can't immediately cancel this one.
    pipeline_cancel_requested: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Set the first time the interactive first-run product tour ends, by
    # finishing OR explicitly skipping — both count as "seen," so it never
    # nags on a later Home visit. NULL means it hasn't run yet; no backfill
    # needed, same reasoning as every other one-shot flag on this model.
    product_tour_completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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
