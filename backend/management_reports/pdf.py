"""Searchable, Unicode management PDFs rendered from saved report data only."""

from functools import lru_cache
from datetime import date, datetime
from io import BytesIO
from pathlib import Path
import re
from zoneinfo import ZoneInfo
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Flowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle,
)


NAVY = colors.HexColor("#16324f")
BLUE = colors.HexColor("#2563eb")
MUTED = colors.HexColor("#526176")
PALE = colors.HexColor("#f1f5f9")
BORDER = colors.HexColor("#dce4ed")
CONTENT_WIDTH = A4[0] - 60


def _capture_time(value):
    return datetime.fromisoformat(value).astimezone(ZoneInfo("Europe/Istanbul")).strftime("%d.%m.%Y %H:%M")


def _calendar_date(value):
    return date.fromisoformat(value).strftime("%d.%m.%Y") if value else "Not set"


@lru_cache(maxsize=1)
def _styles():
    """Use packaged fonts so report layout is independent of the host OS."""
    directory = Path(__file__).with_name("fonts")
    pdfmetrics.registerFont(TTFont("ReportSans", str(directory / "NotoSans-Regular.ttf")))
    pdfmetrics.registerFont(TTFont("ReportSansBold", str(directory / "NotoSans-Bold.ttf")))
    pdfmetrics.registerFontFamily(
        "ReportSans", normal="ReportSans", bold="ReportSansBold",
        italic="ReportSans", boldItalic="ReportSansBold",
    )
    body = ParagraphStyle(
        "ReportBody", fontName="ReportSans", fontSize=8, leading=12,
        textColor=NAVY, splitLongWords=True,
    )
    return {
        "body": body,
        "title": ParagraphStyle("ReportTitle", parent=body, fontName="ReportSansBold",
                                fontSize=19, leading=25, spaceAfter=8),
        "heading": ParagraphStyle("ReportHeading", parent=body, fontName="ReportSansBold",
                                  fontSize=10, leading=15, spaceBefore=12, spaceAfter=6,
                                  keepWithNext=True),
        "muted": ParagraphStyle("ReportMuted", parent=body, fontSize=7, leading=10,
                                textColor=MUTED),
        "value": ParagraphStyle("ReportValue", parent=body, fontName="ReportSansBold",
                                fontSize=18, leading=25, alignment=TA_CENTER),
        "label": ParagraphStyle("ReportLabel", parent=body, fontSize=7, leading=10,
                                alignment=TA_CENTER, textColor=MUTED),
        "tablehead": ParagraphStyle("ReportTableHead", parent=body,
                                    fontName="ReportSansBold", fontSize=7,
                                    leading=10, textColor=colors.white),
    }


def _paragraph(value, style="body"):
    # ReportLab paragraphs interpret XML; notes, names and titles must stay literal.
    literal = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", str(value or ""))
    return Paragraph(escape(literal).replace("\n", "<br/>"), _styles()[style])


class _ApprovalBar(Flowable):
    """A vector bar with its numeric value, readable without color perception."""

    def __init__(self, percentage):
        super().__init__()
        self.width = 60
        self.height = 25
        self.percentage = max(0, min(100, float(percentage)))

    def draw(self):
        self.canv.setFont("ReportSansBold", 8)
        self.canv.setFillColor(NAVY)
        self.canv.drawString(0, 14, f"{self.percentage:.1f}%")
        self.canv.setFillColor(BORDER)
        self.canv.roundRect(0, 3, self.width, 5, 2, fill=1, stroke=0)
        if self.percentage:
            self.canv.setFillColor(BLUE)
            self.canv.roundRect(0, 3, self.width * self.percentage / 100, 5, 2,
                               fill=1, stroke=0)


def _cards(values):
    cells = [[_paragraph(label, "label"), _paragraph(value, "value"),
              _paragraph(caption, "label")] for label, value, caption in values]
    table = Table([cells], colWidths=[CONTENT_WIDTH / len(cells)] * len(cells))
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), PALE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 10),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
        ("LINEBEFORE", (1, 0), (-1, -1), 1, colors.white),
    ]))
    return table


def _summary(metrics):
    return _cards([
        ("Active documents", str(metrics["document_count"]), "Selected project scope"),
        ("Authority approved", f'{metrics["approval_percentage"]:.1f}%',
         f'{metrics["approved_count"]} of {metrics["document_count"]} documents'),
        ("High risk", str(metrics["high_risk_count"]), "Policy-based priorities"),
        ("Overdue actions", str(metrics["action_overdue_count"]), "Past next-action date"),
        ("Plan variance", f'{metrics["schedule_variance"]:+d}', "Issued minus scheduled"),
    ])


def _comparison_section(comparison):
    result = [_paragraph("Weekly comparison", "heading")]
    if not comparison["available"]:
        result.append(_paragraph(
            "No previous-week report. Net comparison is unavailable; save reports each week.",
            "muted",
        ))
        return result
    baseline = comparison["baseline"]
    result.append(_paragraph(
        f'Baseline: {baseline["title"]} | Captured: {_capture_time(baseline["captured_at"])} | '
        f'Elapsed: {comparison["elapsed_days"]} days', "muted",
    ))
    result.append(Spacer(1, 6))
    delta = comparison["deltas"]
    result.append(_cards([
        ("Approved documents", f'{delta["approved_count"]:+d}', "Net change"),
        ("Approval rate", f'{delta["approval_percentage"]:+.1f} pp', "Percentage points"),
        ("Overdue actions", f'{delta["action_overdue_count"]:+d}', "Net change"),
        ("Scope", f'{delta["document_count"]:+d}', "Net active-document change"),
    ]))
    result.append(Spacer(1, 4))
    result.append(_paragraph(
        "Net change compares two captured stocks. It does not count approvals or other events "
        "that occurred between those captures.", "muted",
    ))
    return result


def _project_table(projects):
    headers = ["Project", "Active", "Approved", "Approval rate", "Issued / plan",
               "Overdue actions", "High risk"]
    rows = [[_paragraph(value, "tablehead") for value in headers]]
    for project in projects:
        rows.append([
            _paragraph(project["display_name"]),
            _paragraph(str(project["document_count"])),
            _paragraph(str(project["approved_count"])),
            _ApprovalBar(project["approval_percentage"]),
            _paragraph(f'{project["issued_count"]} / {project["scheduled_count"]}'),
            _paragraph(str(project["action_overdue_count"])),
            _paragraph(str(project["high_risk_count"])),
        ])
    table = Table(rows, colWidths=[CONTENT_WIDTH - 420, 45, 60, 80, 75, 85, 75],
                  repeatRows=1, hAlign="LEFT")
    table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, PALE]),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        ("TOPPADDING", (0, 0), (-1, -1), 7),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
        ("LINEBELOW", (0, -1), (-1, -1), 0.5, BORDER),
    ]))
    return table


def _priorities(priorities):
    result = [_paragraph("Risk priorities", "heading")]
    if not priorities:
        result.append(_paragraph("No risk priorities in this report.", "muted"))
    for item in priorities:
        details = [
            _paragraph(f'{item["project_name"]} / {item["name"]}'),
            _paragraph(
                f'{item["level"].upper()} ({item["score"]}/100) | '
                f'{item["stage_age_days"]} days in stage | '
                f'Owner: {item.get("owner") or "Unassigned"} | '
                f'Action due: {_calendar_date(item.get("next_action_due_date"))}', "muted",
            ),
            _paragraph(item["reason"], "muted"),
            Spacer(1, 6),
        ]
        result.append(KeepTogether(details))
    return result


def _footer(canvas, document):
    canvas.saveState()
    canvas.setStrokeColor(BORDER)
    canvas.line(30, 32, A4[0] - 30, 32)
    canvas.setFillColor(MUTED)
    canvas.setFont("ReportSans", 7)
    canvas.drawString(30, 20, "AW Center | Private saved management report")
    canvas.drawRightString(A4[0] - 30, 20, f"Page {document.page}")
    canvas.restoreState()


def build_report_pdf(report, comparison):
    """Return a private PDF; callers must enforce report ownership/project access.

    Inputs are the server-generated saved report and validated comparison. No
    live metrics are fetched here, so later CompDoc changes cannot alter a PDF.
    """
    _styles()
    output = BytesIO()
    document = SimpleDocTemplate(
        output, pagesize=A4, rightMargin=30, leftMargin=30, topMargin=30,
        bottomMargin=45, title=report["title"], author="AW Center",
    )
    story = [
        _paragraph("AW CENTER / MANAGEMENT REPORTS", "muted"),
        Spacer(1, 8),
        _paragraph(report["title"], "title"),
        _paragraph(f'Captured: {_capture_time(report["captured_at"])} | Week starting: {_calendar_date(report["week_start"])}', "muted"),
        _paragraph("Scope: " + ", ".join(item["display_name"] for item in report["projects"]), "muted"),
        Spacer(1, 12),
        _summary(report["totals"]),
    ]
    if not report["totals"]["document_count"]:
        story.extend([Spacer(1, 6), _paragraph("No active documents in the selected scope.", "muted")])
    story.extend(_comparison_section(comparison))
    story.extend([_paragraph("Project overview", "heading"), _project_table(report["projects"])])
    story.extend(_priorities(report["priorities"]))
    if report["management_note"]:
        story.extend([_paragraph("Management note / decision requests", "heading"),
                      _paragraph(report["management_note"])])
    story.extend([
        _paragraph("Definitions and data context", "heading"),
        _paragraph(
            "Authority approved and issued documents are separate measures. Plan variance is "
            "issued minus scheduled documents at capture time. Approval rate is approved / "
            "active documents across the selected projects. Risk scores are policy-based "
            "priorities, not delay probabilities. Data-quality counts represent issues, "
            "not unique documents. Capture time does not assert external-source freshness.", "muted",
        ),
        _paragraph(
            f'Data-quality issues: {report["totals"]["data_quality_issue_count"]} | '
            f'Unassigned: {report["totals"]["unassigned_count"]} | '
            f'Actions due within 7 days: {report["totals"]["action_due_soon_count"]} | '
            f'Pending internal review / approval tasks: '
            f'{report["totals"]["pending_review_count"]} / '
            f'{report["totals"]["pending_approval_count"]}', "muted",
        ),
    ])
    document.build(story, onFirstPage=_footer, onLaterPages=_footer)
    return output.getvalue()
