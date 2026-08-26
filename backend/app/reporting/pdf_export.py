"""
Builds a structured, professionally laid-out PDF for a CompetitorReport —
replaces the earlier CSV + browser-print combo now that a real PDF library
(reportlab) is in the stack. Pure presentation over report.content, which is
already fully computed (see reporting/service.py) — this module renders,
it never decides a number or an alert.

reportlab's platypus API (Paragraph/Table/Spacer flowables fed to
SimpleDocTemplate.build()) rather than a canvas-drawing approach — it
handles pagination/wrapping/repeating table headers for free, which matters
here since price_comparison and market_coverage are unbounded-length tables.
"""
from typing import Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.reporting.models import CompetitorReport
from app.workspace.models import Workspace

INK = colors.HexColor("#1b1f2a")
SLATE = colors.HexColor("#5b6472")
SLATE_SOFT = colors.HexColor("#8b93a1")
PAPER = colors.HexColor("#f5f6f8")
BORDER = colors.HexColor("#e2e4e9")
ACCENT = colors.HexColor("#c2410c")
GOOD = colors.HexColor("#15803d")
DANGER = colors.HexColor("#dc2626")

_OBJECTIVE_LABELS = {
    "market_research": "Market research",
    "price_alignment": "Price alignment",
    "map_compliance": "Reseller pricing compliance (MAP)",
}

_ALERT_LABELS = {
    "map_violation": "MAP violation",
    "price_anomaly": "Price anomaly",
    "new_competitor_product": "New competitor product",
    "own_price_change": "Own price change",
    "stock_status_change": "Stock status change",
}

_PAGE_MARGIN = 2 * cm


def _styles() -> dict[str, ParagraphStyle]:
    return {
        "title": ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=20, textColor=INK, leading=24),
        "subtitle": ParagraphStyle("subtitle", fontName="Helvetica", fontSize=9.5, textColor=SLATE, leading=14),
        "h2": ParagraphStyle("h2", fontName="Helvetica-Bold", fontSize=13, textColor=INK, spaceBefore=18, spaceAfter=8),
        "body": ParagraphStyle("body", fontName="Helvetica", fontSize=9.5, textColor=INK, leading=14.5),
        "small": ParagraphStyle("small", fontName="Helvetica", fontSize=8, textColor=SLATE, leading=11.5),
        "kpi_value": ParagraphStyle("kpi_value", fontName="Helvetica-Bold", fontSize=19, alignment=1, textColor=INK),
        "kpi_label": ParagraphStyle("kpi_label", fontName="Helvetica", fontSize=8, alignment=1, textColor=SLATE),
        "cell": ParagraphStyle("cell", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=12),
        "cell_bold": ParagraphStyle("cell_bold", fontName="Helvetica-Bold", fontSize=8.5, textColor=INK, leading=12),
        "cell_soft": ParagraphStyle("cell_soft", fontName="Helvetica", fontSize=8, textColor=SLATE_SOFT, leading=11),
        "thead": ParagraphStyle("thead", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10),
        "empty": ParagraphStyle("empty", fontName="Helvetica-Oblique", fontSize=9, textColor=SLATE_SOFT, leading=13),
    }


def _fmt_dt(iso_or_dt) -> str:
    return iso_or_dt.strftime("%B %d, %Y at %H:%M")


def _fmt_money(value: Optional[float], currency: Optional[str]) -> str:
    if value is None:
        return "—"
    return f"{currency or ''} {value:,.2f}".strip()


def _header(report: CompetitorReport, workspace: Workspace, s: dict) -> list:
    title = report.name or f"Competitor Report — {report.generated_at:%b %d, %Y}"
    meta = (
        f"{workspace.name} &middot; Generated {_fmt_dt(report.generated_at)} "
        f"&middot; {report.status.title()} &middot; {report.trigger_source.title()} trigger"
    )
    story = [
        Paragraph(title, s["title"]),
        Spacer(1, 4),
        Paragraph(meta, s["subtitle"]),
        Spacer(1, 10),
        HRFlowable(width="100%", thickness=2, color=ACCENT, spaceAfter=14),
    ]
    if report.status == "failed":
        story.append(
            Paragraph(
                f"The AI summary couldn't be generated ({report.error_message}). The price comparison below is still accurate.",
                ParagraphStyle("warn", parent=s["body"], textColor=DANGER),
            )
        )
        story.append(Spacer(1, 8))
    return story


def _kpi_row(stats: dict, s: dict, content_width: float) -> Table:
    increases_color = INK
    decreases_color = GOOD if stats["price_decreases"] > 0 else INK
    alerts_color = DANGER if stats["alerts_count"] > 0 else INK

    def cell(value, color):
        return [
            Paragraph(str(value), ParagraphStyle("v", parent=s["kpi_value"], textColor=color)),
        ]

    data = [
        [
            cell(stats["matches_tracked"], INK),
            cell(stats["alerts_count"], alerts_color),
            cell(stats["price_increases"], increases_color),
            cell(stats["price_decreases"], decreases_color),
        ],
        [
            [Paragraph("Matches tracked", s["kpi_label"])],
            [Paragraph("Alerts", s["kpi_label"])],
            [Paragraph("Price increases", s["kpi_label"])],
            [Paragraph("Price decreases", s["kpi_label"])],
        ],
    ]
    col = content_width / 4
    tbl = Table(data, colWidths=[col] * 4, rowHeights=[30, 18])
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                ("BOX", (0, 0), (-1, -1), 0.75, BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.75, BORDER),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, 0), 6),
                ("BOTTOMPADDING", (0, 1), (-1, 1), 8),
            ]
        )
    )
    return tbl


def _alerts_breakdown(alerts: list[dict], s: dict) -> str:
    counts = {
        "map_violation": 0,
        "price_anomaly_up": 0,
        "price_anomaly_down": 0,
        "new_competitor_product": 0,
        "own_price_change": 0,
        "stock_status_change": 0,
    }
    new_product_total = 0
    for a in alerts:
        if a["type"] == "map_violation":
            counts["map_violation"] += 1
        elif a["type"] == "price_anomaly":
            direction = (a.get("trend") or {}).get("direction")
            if direction == "up":
                counts["price_anomaly_up"] += 1
            elif direction == "down":
                counts["price_anomaly_down"] += 1
        elif a["type"] == "new_competitor_product":
            counts["new_competitor_product"] += 1
            new_product_total += a.get("new_product_count") or 0
        elif a["type"] == "own_price_change":
            counts["own_price_change"] += 1
        elif a["type"] == "stock_status_change":
            counts["stock_status_change"] += 1
    return (
        f"{counts['map_violation']} MAP violations &middot; {counts['price_anomaly_up']} price jumps &middot; "
        f"{counts['price_anomaly_down']} price drops &middot; {new_product_total} new competitor products &middot; "
        f"{counts['own_price_change']} own price changes &middot; {counts['stock_status_change']} stock status changes"
    )


def _alerts_section(alerts: list[dict], s: dict, content_width: float) -> list:
    story = [Paragraph("Alerts", s["h2"])]
    if not alerts:
        story.append(
            Paragraph(
                "No alerts this period — nothing crossed the MAP-violation, price-anomaly, new-product, "
                "or own-price-change thresholds since the previous report.",
                s["empty"],
            )
        )
        return story

    story.append(Paragraph(_alerts_breakdown(alerts, s), s["small"]))
    story.append(Spacer(1, 8))

    severity_color = {"high": DANGER, "medium": ACCENT}
    rows = []
    for a in alerts:
        label = _ALERT_LABELS.get(a["type"], a["type"])
        color = severity_color.get(a["severity"], SLATE)
        badge = Paragraph(f'<font color="{color.hexval()}"><b>{label}</b></font>', s["cell"])
        message = Paragraph(a["message"], s["cell"])
        rows.append([badge, message])

    tbl = Table(rows, colWidths=[content_width * 0.22, content_width * 0.78])
    tbl.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -2), 0.5, BORDER),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )
    story.append(tbl)
    return story


def _narrative_section(title: str, text: Optional[str], s: dict) -> list:
    if not text:
        return []
    return [Paragraph(title, s["h2"]), Paragraph(text, s["body"])]


def _price_comparison_section(groups: list[dict], s: dict, content_width: float) -> list:
    story = [Paragraph("Price comparison", s["h2"])]
    if not groups:
        story.append(Paragraph("No confirmed, priced matches to compare yet.", s["empty"]))
        return story

    header = [
        Paragraph("Product", s["thead"]),
        Paragraph("Price standing", s["thead"]),
        Paragraph("Cheapest competitor", s["thead"]),
        Paragraph("Tracked competitors", s["thead"]),
    ]
    rows = [header]
    for group in groups:
        m = group["metrics"]
        name_cell = [Paragraph(group["product_name"], s["cell_bold"])]
        price_line = _fmt_money(group["product_price"], group["product_currency"])
        own_trend = group.get("own_trend")
        if own_trend and own_trend["direction"] != "same":
            arrow = "&#9650;" if own_trend["direction"] == "up" else "&#9660;"
            price_line += f' <font color="{(ACCENT if own_trend["is_anomaly"] else SLATE_SOFT).hexval()}">{arrow}</font>'
        name_cell.append(Paragraph(price_line, s["cell_soft"]))
        if group.get("product_min_price") is not None:
            name_cell.append(Paragraph(f'MAP {_fmt_money(group["product_min_price"], group["product_currency"])}', s["cell_soft"]))

        # Plain-language sentence only — no raw rank/index numbers printed
        # here. This is the artifact meant to be printed/forwarded to
        # management, so it stays the cleanest version; the raw numbers
        # are still in the data (ProductMetrics.price_rank/price_index),
        # just not surfaced as a labeled statistic anywhere in the PDF.
        if m["price_position_summary"] is not None:
            rank_cell = [Paragraph(m["price_position_summary"], s["cell"])]
        else:
            rank_cell = [Paragraph("No same-currency data", s["cell_soft"])]

        if m["cheapest_competitor_name"]:
            cheapest_cell = [
                Paragraph(m["cheapest_competitor_name"], s["cell"]),
                Paragraph(_fmt_money(m["cheapest_competitor_price"], group["product_currency"]), s["cell_soft"]),
            ]
        else:
            cheapest_cell = [Paragraph("—", s["cell_soft"])]

        match_lines = []
        for row in group["matches"][:6]:
            site = row["competitor_site_name"] or row["competitor_site_domain"]
            price = _fmt_money(row["competitor_product_price"], row["competitor_product_currency"])
            flag = " (below MAP)" if row.get("below_map") else ""
            match_lines.append(Paragraph(f"{site} &middot; {price}{flag}", s["cell"]))
        remaining = len(group["matches"]) - 6
        if remaining > 0:
            match_lines.append(Paragraph(f"+{remaining} more", s["cell_soft"]))
        if not match_lines:
            match_lines = [Paragraph("—", s["cell_soft"])]

        rows.append([name_cell, rank_cell, cheapest_cell, match_lines])

    widths = [content_width * 0.28, content_width * 0.18, content_width * 0.24, content_width * 0.30]
    tbl = Table(rows, colWidths=widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
            ]
        )
    )
    story.append(tbl)
    return story


def _market_coverage_section(coverage: dict, competitive_gaps: Optional[str], s: dict, content_width: float) -> list:
    if not competitive_gaps and not coverage.get("sites"):
        return []
    story = [Paragraph("Market coverage", s["h2"])]
    if competitive_gaps:
        story.append(Paragraph(competitive_gaps, s["body"]))
        story.append(Spacer(1, 10))

    sites = coverage.get("sites") or []
    if not sites:
        return story

    header = [
        Paragraph("Site", s["thead"]),
        Paragraph("Relationship", s["thead"]),
        Paragraph("Discovered", s["thead"]),
        Paragraph("Matched", s["thead"]),
        Paragraph("Unmatched sample", s["thead"]),
    ]
    rows = [header]
    for site in sites:
        sample = ", ".join(p["title"] for p in site["unmatched_sample"][:4])
        rows.append(
            [
                Paragraph(site["competitor_site_name"] or site["competitor_site_domain"], s["cell"]),
                Paragraph(site["relationship_type"].title(), s["cell_soft"]),
                Paragraph(str(site["total_products_discovered"]), s["cell"]),
                Paragraph(str(site["matched_products_count"]), s["cell"]),
                Paragraph(sample or "—", s["cell_soft"]),
            ]
        )
    widths = [content_width * 0.20, content_width * 0.14, content_width * 0.12, content_width * 0.12, content_width * 0.42]
    tbl = Table(rows, colWidths=widths, repeatRows=1)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), INK),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LINEBELOW", (0, 0), (-1, -1), 0.5, BORDER),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PAPER]),
            ]
        )
    )
    story.append(tbl)
    return story


def _recommendations_section(recommendations: list[dict], s: dict) -> list:
    if not recommendations:
        return []
    story = [Paragraph("Recommendations", s["h2"])]
    for i, rec in enumerate(recommendations, start=1):
        label = _OBJECTIVE_LABELS.get(rec["objective"], rec["objective"].replace("_", " ").title())
        block = [
            Paragraph(f'<font color="{ACCENT.hexval()}"><b>{i}. {label}</b></font>', s["cell"]),
            Spacer(1, 2),
            Paragraph(rec["text"], s["body"]),
            Spacer(1, 10),
        ]
        story.append(KeepTogether(block))
    return story


def _footer(canvas, doc):
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(SLATE_SOFT)
    canvas.drawString(_PAGE_MARGIN, 1.2 * cm, "Pricing Intelligence AI — Confidential, generated for internal use")
    canvas.drawRightString(A4[0] - _PAGE_MARGIN, 1.2 * cm, f"Page {doc.page}")
    canvas.restoreState()


def build_report_pdf(report: CompetitorReport, workspace: Workspace) -> bytes:
    from io import BytesIO

    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=_PAGE_MARGIN,
        rightMargin=_PAGE_MARGIN,
        topMargin=_PAGE_MARGIN,
        bottomMargin=_PAGE_MARGIN,
        title=report.name or f"Competitor Report {report.generated_at:%Y-%m-%d}",
    )
    content_width = A4[0] - 2 * _PAGE_MARGIN
    s = _styles()
    content = report.content

    story: list = []
    story += _header(report, workspace, s)
    story.append(_kpi_row(content["summary_stats"], s, content_width))
    story.append(
        Paragraph(
            "Price increases/decreases measure competitor price moves since your previous report, "
            "not how your price compares to theirs today.",
            s["small"],
        )
    )
    story.append(Spacer(1, 18))
    # Executive summary, market position, and recommendations first — the
    # "so what do I do" sections, read straight through a printed/forwarded
    # PDF with no clicking around — before the supporting detail (alerts,
    # the full price-comparison table, the full market-coverage catalog).
    story += _narrative_section("Executive summary", content.get("executive_summary"), s)
    story += _narrative_section("Market position", content.get("market_position"), s)
    story += _recommendations_section(content.get("recommendations", []), s)
    story.append(Spacer(1, 6))
    story += _alerts_section(content.get("alerts", []), s, content_width)
    story.append(Spacer(1, 6))
    story += _price_comparison_section(content.get("price_comparison", []), s, content_width)
    story += _market_coverage_section(
        content.get("market_coverage", {}), content.get("competitive_gaps"), s, content_width
    )

    doc.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()
