import csv
import io

from fastapi import APIRouter, Depends, HTTPException, status as http_status
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_workspace
from app.reporting import service as reporting_service
from app.reporting.models import CompetitorReport
from app.reporting.schemas import CompetitorReportOut
from app.services import ai_client
from app.services.cooldown import check_cooldown
from app.workspace.models import Workspace
from app.db.database import get_db

router = APIRouter()

# Same reasoning as discovery's own cooldown — cheapest guard against a
# double-click burning a real AI call. This does NOT enforce
# report_interval_hours (that governs only the scheduled path) — a user
# can manually regenerate anytime beyond this double-click guard.
REPORT_COOLDOWN_SECONDS = 30


@router.post("/reports", response_model=CompetitorReportOut)
async def create_report(
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """Generate a report now. Returns 200 even when the AI narrative fails
    (status="failed" in the body) rather than a 502 that would discard the
    already-correct, already-computed price comparison and alerts — see
    reporting/service.py's persistence rule."""
    last_report = await reporting_service.get_previous_report(db, workspace.id)
    check_cooldown(last_report.generated_at if last_report else None, REPORT_COOLDOWN_SECONDS)

    try:
        report = await reporting_service.generate_report(db, workspace, trigger_source="manual")
    except reporting_service.NoTrackedMatchesError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except ai_client.NoActiveProviderError as exc:
        raise HTTPException(status_code=http_status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return report


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


@router.get("/reports/{report_id}/export.csv")
async def export_report_csv(
    report_id: int,
    workspace: Workspace = Depends(get_current_workspace),
    db: AsyncSession = Depends(get_db),
):
    """The spec's "exportable report" ask — a plain CSV of the price
    comparison (+ any alert flag), same download pattern as catalog's
    import template. No PDF library exists in this stack; CSV plus the
    report page's own print stylesheet are the pragmatic v1 scope."""
    report = await _get_owned_report(db, report_id, workspace.id)
    alert_by_match_id = {a["match_id"]: a["type"] for a in report.content.get("alerts", [])}

    buffer = io.StringIO()
    writer = csv.writer(buffer)
    writer.writerow(
        [
            "product_name", "product_price", "product_currency", "product_min_price",
            "competitor_site_domain", "competitor_product_title",
            "competitor_product_price", "competitor_product_currency",
            "price_delta_pct", "alert",
        ]
    )
    for row in report.content.get("price_comparison", []):
        writer.writerow(
            [
                row["product_name"], row["product_price"], row["product_currency"], row["product_min_price"],
                row["competitor_site_domain"], row["competitor_product_title"],
                row["competitor_product_price"], row["competitor_product_currency"],
                row["price_delta_pct"], alert_by_match_id.get(row["match_id"], ""),
            ]
        )

    return Response(
        content=buffer.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="report_{report_id}.csv"'},
    )
