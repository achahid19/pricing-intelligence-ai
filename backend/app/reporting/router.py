from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status as http_status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace
from app.reporting import service as reporting_service
from app.reporting.models import CompetitorReport
from app.reporting.pdf_export import build_report_pdf
from app.reporting.schemas import CompetitorReportOut, PipelineStartedOut, ReportRename
from app.services.cooldown import check_cooldown
from app.workspace.models import Workspace
from app.db.database import get_db

router = APIRouter()

# Same reasoning as discovery's own cooldown — cheapest guard against a
# double-click burning a real AI call. This does NOT enforce
# report_interval_hours (that governs only the scheduled path) — a user
# can manually regenerate anytime beyond this double-click guard.
REPORT_COOLDOWN_SECONDS = 30


@router.post("/reports", response_model=PipelineStartedOut, status_code=http_status.HTTP_202_ACCEPTED)
async def create_report(
    background_tasks: BackgroundTasks,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Generate a report now — as of 2026-08-10, this means the *full*
    pipeline (fresh product discovery + auto-match ≥80% for every saved
    competitor, then the report), not just generate_report() directly,
    same as the onboarding/scheduled trigger points. That can genuinely
    take minutes (observed live this session), well past the frontend
    proxy's timeout, so this can no longer run synchronously inside the
    request the way it used to — it's backgrounded and returns
    immediately. Workspace.pipeline_status/pipeline_substeps (already
    polled by the frontend, see lib/pipelineStatus.tsx) is what actually
    carries this forward, including the eventual report id once done."""
    last_report = await reporting_service.get_previous_report(db, workspace.id)
    check_cooldown(last_report.generated_at if last_report else None, REPORT_COOLDOWN_SECONDS)

    # A single pipeline_status field now gets written from three trigger
    # points (onboarding, scheduled, and this one) — without this guard a
    # manual click while one's already running would race the same
    # Workspace row with a second, fully overlapping run.
    if workspace.pipeline_status == "running":
        raise HTTPException(
            status_code=http_status.HTTP_400_BAD_REQUEST,
            detail="A report is already being generated for this workspace — check Activity for progress.",
        )

    background_tasks.add_task(reporting_service.run_full_pipeline_background, workspace.id, "manual")
    return PipelineStartedOut()


@router.get("/reports", response_model=list[CompetitorReportOut])
async def list_reports(
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CompetitorReport)
        .where(CompetitorReport.workspace_id == workspace.id)
        .order_by(CompetitorReport.generated_at.desc())
    )
    return result.scalars().all()


async def _get_owned_report(db: AsyncSession, report_id: int, workspace_id: int) -> CompetitorReport:
    result = await db.execute(select(CompetitorReport).where(CompetitorReport.id == report_id))
    report = result.scalars().first()
    if report is None or report.workspace_id != workspace_id:
        raise HTTPException(status_code=http_status.HTTP_404_NOT_FOUND, detail="Report not found")
    return report


@router.get("/reports/{report_id}", response_model=CompetitorReportOut)
async def get_report(
    report_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    return await _get_owned_report(db, report_id, workspace.id)


@router.patch("/reports/{report_id}", response_model=CompetitorReportOut)
async def rename_report(
    report_id: int,
    payload: ReportRename,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    report = await _get_owned_report(db, report_id, workspace.id)
    report.name = payload.name.strip() or None
    await db.commit()
    await db.refresh(report)
    return report


@router.delete("/reports/{report_id}", status_code=http_status.HTTP_204_NO_CONTENT)
async def delete_report(
    report_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """fed_forward_from_report_id is ON DELETE SET NULL (models.py), so a
    later report chained off this one just loses its "since last time"
    reference rather than blocking the delete."""
    report = await _get_owned_report(db, report_id, workspace.id)
    await db.delete(report)
    await db.commit()


@router.get("/reports/{report_id}/export.pdf")
async def export_report_pdf(
    report_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """The spec's "exportable report" ask — a proper structured PDF (see
    reporting/pdf_export.py), replacing the earlier CSV + browser-print
    combo now that a real PDF library is in the stack."""
    report = await _get_owned_report(db, report_id, workspace.id)
    pdf_bytes = build_report_pdf(report, workspace)
    date_str = report.generated_at.strftime("%Y-%m-%d")
    filename = f"report_{date_str}_{report_id}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
