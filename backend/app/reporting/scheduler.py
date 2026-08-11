"""
Single in-process background job that reads Workspace.report_interval_hours
(set in Settings, previously never read by anything) and generates a report
for every workspace that's due — the automation half of "so what should I
do," on top of generate_report() the manual endpoint also calls. Also the
trigger point for Workspace.refresh_before_report: when set, the full
automated pipeline (fresh competitor discovery, auto-saving ≥80% confidence;
product discovery + auto-match for every saved site, auto-confirming ≥80%
confidence matches) runs immediately before the report generates, so the
report reflects current data rather than whatever was last manually
discovered (see reporting_service.run_full_pipeline).

Runs correctly for this app's current deployment shape: one backend
replica, no --workers (see docker-compose.yml). If this ever scales
horizontally, every replica would independently see the same workspace as
"due" and fire a duplicate report/AI call (and, now, a duplicate pipeline
pass too) — noted in docs/DECISIONS.md as a known limitation to revisit
then (a DB-level claim, or moving the scheduler to one dedicated process),
not solved here.
"""
import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.database import AsyncSessionLocal
from app.reporting import service as reporting_service
from app.services import ai_client
from app.workspace.models import Workspace

logger = logging.getLogger(__name__)

# Cheapest reasonable granularity given the smallest real interval a
# workspace can set is 24h (daily) — at most 1h staleness past due time.
CHECK_INTERVAL_HOURS = 1

scheduler = AsyncIOScheduler()


async def _maybe_generate_for_workspace(db, workspace: Workspace) -> None:
    last_report = await reporting_service.get_previous_report(db, workspace.id)
    if last_report is not None:
        due_at = last_report.generated_at + timedelta(hours=workspace.report_interval_hours)
        if datetime.now(timezone.utc) < due_at:
            return

    try:
        if workspace.refresh_before_report:
            await reporting_service.run_full_pipeline(db, workspace, trigger_source="scheduled")
        else:
            await reporting_service.generate_report(db, workspace, trigger_source="scheduled")
    except reporting_service.NoTrackedMatchesError:
        logger.info("Skipping scheduled report for workspace %s: no trackable confirmed matches yet", workspace.id)
    except ai_client.NoActiveProviderError:
        logger.info("Skipping scheduled report for workspace %s: no active AI provider configured", workspace.id)


async def check_and_generate_reports() -> None:
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Workspace).where(Workspace.report_interval_hours.is_not(None)))
        for workspace in result.scalars().all():
            try:
                await _maybe_generate_for_workspace(db, workspace)
            except Exception:
                logger.exception("Scheduled report generation failed for workspace %s", workspace.id)


def start_scheduler() -> None:
    scheduler.add_job(
        check_and_generate_reports,
        "interval",
        hours=CHECK_INTERVAL_HOURS,
        id="report_generation_check",
        replace_existing=True,
        max_instances=1,
    )
    scheduler.start()


def stop_scheduler() -> None:
    scheduler.shutdown(wait=False)
