from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from io import BytesIO
import html
import os

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    Image,
    KeepTogether,
)

from app.database import SessionLocal
from app.auth_utils import get_current_user
from app.routes.summary import (
    build_underwriting_intelligence,
    get_claims_for_account,
    data_quality,
)
from app.routes.renewal import (
    build_underwriter_decision_engine,
    build_carrier_appetite_engine,
    build_carrier_match_engine,
    build_premium_forecast_engine,
    money,
    is_open,
    is_litigated,
)

router = APIRouter(prefix="/reports", tags=["Reports"])

NAVY = colors.HexColor("#0f172a")
SLATE = colors.HexColor("#334155")
MUTED = colors.HexColor("#64748b")
BLUE = colors.HexColor("#2563eb")
LIGHT_BLUE = colors.HexColor("#eff6ff")
BORDER = colors.HexColor("#cbd5e1")
SOFT = colors.HexColor("#f8fafc")
GREEN = colors.HexColor("#16a34a")
AMBER = colors.HexColor("#d97706")
ORANGE = colors.HexColor("#ea580c")
RED = colors.HexColor("#dc2626")
PURPLE = colors.HexColor("#7c3aed")
WHITE = colors.white


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def clean(value):
    return str(value or "").strip()


def dollars(value):
    return f"${money(value):,.0f}"


def pct(value):
    if value is None:
        return "-"
    return f"{value}%"


def safe_text(value):
    return html.escape(clean(value) or "-").replace("\n", "<br/>")


def claim_attr(claim, *names, default=""):
    for name in names:
        value = getattr(claim, name, None)
        if value not in [None, ""]:
            return value
    return default


def get_creator(current_user: dict | None):
    user = current_user or {}
    creator = (
        user.get("full_name")
        or user.get("name")
        or user.get("display_name")
        or user.get("username")
        or user.get("email")
        or user.get("sub")
        or "LossQ User"
    )
    email = user.get("email") or ""
    if email and email not in creator:
        return f"{creator} ({email})"
    return creator


def get_logo_path():
    candidates = [
        os.path.join(os.getcwd(), "frontend", "public", "lossq-logo-style2.png"),
        os.path.join(os.getcwd(), "public", "lossq-logo-style2.png"),
        os.path.join(os.getcwd(), "app", "static", "lossq-logo-style2.png"),
        os.path.join(os.getcwd(), "lossq-logo-style2.png"),
        "/app/frontend/public/lossq-logo-style2.png",
        "/app/public/lossq-logo-style2.png",
    ]
    for path in candidates:
        if os.path.exists(path):
            return path
    return None


def risk_color(risk_level: str, renewal_score=None):
    risk = clean(risk_level).lower()
    if "critical" in risk or "distressed" in risk:
        return RED
    if "high" in risk:
        return ORANGE
    if "moderate" in risk or "medium" in risk:
        return AMBER
    if "low" in risk:
        return GREEN
    try:
        score = float(renewal_score)
        if score < 35:
            return RED
        if score < 55:
            return ORANGE
        if score < 75:
            return AMBER
        return GREEN
    except Exception:
        return SLATE


def get_metrics(claims):
    total_claims = len(claims)
    open_claims = len([c for c in claims if is_open(c)])
    closed_claims = max(total_claims - open_claims, 0)
    litigation_claims = len([c for c in claims if is_litigated(c)])
    flagged_claims = len([c for c in claims if clean(getattr(c, "flag", ""))])
    total_paid = sum(money(getattr(c, "paid_amount", 0)) for c in claims)
    total_reserve = sum(money(getattr(c, "reserve_amount", 0)) for c in claims)
    total_incurred = sum(money(getattr(c, "total_incurred", 0)) for c in claims)
    largest_loss = max([money(getattr(c, "total_incurred", 0)) for c in claims], default=0)
    return {
        "total_claims": total_claims,
        "open_claims": open_claims,
        "closed_claims": closed_claims,
        "litigation_claims": litigation_claims,
        "flagged_claims": flagged_claims,
        "total_paid": total_paid,
        "total_reserve": total_reserve,
        "total_incurred": total_incurred,
        "largest_loss": largest_loss,
    }


def build_context(db: Session, current_user: dict, policy_number: str | None):
    claims, policy_numbers_used, profile = get_claims_for_account(db, current_user, policy_number)
    quality = data_quality(claims, policy_numbers_used, profile)
    summary = build_underwriting_intelligence(claims)
    decision = build_underwriter_decision_engine(claims, policy_number)
    appetite = build_carrier_appetite_engine(claims, policy_number)
    carrier_match = build_carrier_match_engine(claims, policy_number)
    forecast = build_premium_forecast_engine(claims, policy_number)
    metrics = get_metrics(claims)

    summary_metrics = summary.get("renewal_metrics") or summary.get("metrics") or {}
    decision_metrics = decision.get("decision_metrics") or {}
    forecast_metrics = forecast.get("forecast_metrics") or {}

    # Prefer the guarded account-aware engine metrics when available.
    for source in [summary_metrics, decision_metrics, forecast_metrics]:
        for key in [
            "total_claims",
            "open_claims",
            "closed_claims",
            "litigation_claims",
            "flagged_claims",
            "total_paid",
            "total_reserve",
            "total_incurred",
            "largest_loss",
        ]:
            if key in source and source.get(key) is not None:
                metrics[key] = source[key]

    return {
        "claims": claims,
        "policy_numbers_used": policy_numbers_used,
        "profile": profile or {},
        "quality": quality,
        "summary": summary,
        "decision": decision,
        "appetite": appetite,
        "carrier_match": carrier_match,
        "forecast": forecast,
        "metrics": metrics,
        "creator": get_creator(current_user),
    }


def make_doc(title: str):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.48 * inch,
        leftMargin=0.48 * inch,
        topMargin=0.72 * inch,
        bottomMargin=0.58 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="LossQTitle",
            parent=styles["Title"],
            fontSize=24,
            leading=28,
            textColor=NAVY,
            alignment=1,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LossQSubtitle",
            parent=styles["BodyText"],
            fontSize=10.5,
            leading=14,
            textColor=MUTED,
            alignment=1,
            spaceAfter=16,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LossQHeading",
            parent=styles["Heading2"],
            fontSize=13.5,
            leading=17,
            textColor=BLUE,
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LossQBody",
            parent=styles["BodyText"],
            fontSize=8.7,
            leading=12,
            textColor=colors.HexColor("#1f2937"),
            spaceAfter=6,
        )
    )
    styles.add(
        ParagraphStyle(
            name="SmallMuted",
            parent=styles["BodyText"],
            fontSize=7.5,
            leading=9.5,
            textColor=MUTED,
            spaceAfter=4,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CardLabel",
            parent=styles["BodyText"],
            fontSize=7.5,
            leading=9,
            textColor=MUTED,
            alignment=1,
        )
    )
    styles.add(
        ParagraphStyle(
            name="CardValue",
            parent=styles["BodyText"],
            fontSize=13,
            leading=16,
            textColor=NAVY,
            alignment=1,
        )
    )
    return buffer, doc, styles


def p(text, styles):
    return Paragraph(safe_text(text), styles["LossQBody"])


def subtitle(text, styles):
    return Paragraph(safe_text(text), styles["LossQSubtitle"])


def heading(text, styles):
    return Paragraph(safe_text(text), styles["LossQHeading"])


def title(text, styles):
    return Paragraph(safe_text(text), styles["LossQTitle"])


def logo_flowable(width=2.2 * inch):
    logo_path = get_logo_path()
    if not logo_path:
        return Paragraph("<b>LOSSQ</b>", getSampleStyleSheet()["Title"])
    img = Image(logo_path)
    ratio = (img.imageHeight or 1) / (img.imageWidth or 1)
    img.drawWidth = width
    img.drawHeight = width * ratio
    return img


def draw_header_footer(canvas, doc, report_title: str, prepared_by: str):
    canvas.saveState()
    width, height = letter

    # Header bar
    canvas.setFillColor(NAVY)
    canvas.rect(0, height - 0.34 * inch, width, 0.34 * inch, fill=True, stroke=False)
    canvas.setFillColor(WHITE)
    canvas.setFont("Helvetica-Bold", 8)
    canvas.drawString(0.5 * inch, height - 0.22 * inch, "LossQ Underwriting Intelligence")
    canvas.setFont("Helvetica", 7)
    canvas.drawRightString(width - 0.5 * inch, height - 0.22 * inch, f"{report_title} | Page {doc.page}")

    # Footer
    canvas.setStrokeColor(BORDER)
    canvas.line(0.5 * inch, 0.42 * inch, width - 0.5 * inch, 0.42 * inch)
    canvas.setFillColor(MUTED)
    canvas.setFont("Helvetica", 6.8)
    canvas.drawString(0.5 * inch, 0.25 * inch, f"Prepared by: {prepared_by}")
    canvas.drawCentredString(width / 2, 0.25 * inch, f"Date Created: {datetime.utcnow().date().isoformat()}")
    canvas.drawRightString(width - 0.5 * inch, 0.25 * inch, "Confidential | Generated by LossQ")
    canvas.restoreState()


def table(data, widths=None, header=True, font_size=8, header_color=NAVY):
    tbl = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), header_color if header else WHITE),
        ("TEXTCOLOR", (0, 0), (-1, 0), WHITE if header else NAVY),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), font_size),
        ("LEADING", (0, 0), (-1, -1), font_size + 2),
        ("GRID", (0, 0), (-1, -1), 0.25, BORDER),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [WHITE, SOFT]),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
    ]
    if not header:
        style.extend(
            [
                ("BACKGROUND", (0, 0), (-1, -1), WHITE),
                ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
                ("TEXTCOLOR", (0, 0), (0, -1), SLATE),
                ("ROWBACKGROUNDS", (0, 0), (-1, -1), [WHITE, SOFT]),
            ]
        )
    tbl.setStyle(TableStyle(style))
    return tbl


def kpi_cards(cards, styles, columns=4):
    row = []
    for label, value in cards:
        cell = Table(
            [
                [Paragraph(safe_text(label), styles["CardLabel"])],
                [Paragraph(f"<b>{safe_text(value)}</b>", styles["CardValue"])],
            ],
            colWidths=[1.65 * inch],
        )
        cell.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f8fafc")),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER),
                    ("TOPPADDING", (0, 0), (-1, -1), 7),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ]
            )
        )
        row.append(cell)
    tbl = Table([row], colWidths=[1.72 * inch] * len(row))
    tbl.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
    return tbl


def risk_banner(renewal_score, risk_level, styles):
    color = risk_color(risk_level, renewal_score)
    score_text = f"{renewal_score}/100" if renewal_score is not None else "-"
    risk_text = clean(risk_level) or "Not Rated"
    tbl = Table(
        [
            [
                Paragraph("<font color='white'><b>RENEWAL SCORE</b></font>", styles["CardLabel"]),
                Paragraph("<font color='white'><b>RISK LEVEL</b></font>", styles["CardLabel"]),
                Paragraph("<font color='white'><b>UNDERWRITING POSTURE</b></font>", styles["CardLabel"]),
            ],
            [
                Paragraph(f"<font color='white'><b>{safe_text(score_text)}</b></font>", styles["CardValue"]),
                Paragraph(f"<font color='white'><b>{safe_text(risk_text.upper())}</b></font>", styles["CardValue"]),
                Paragraph("<font color='white'><b>MARKET STRATEGY REQUIRED</b></font>", styles["CardValue"]),
            ],
        ],
        colWidths=[2.2 * inch, 2.2 * inch, 2.4 * inch],
    )
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), color),
                ("BOX", (0, 0), (-1, -1), 0.5, color),
                ("INNERGRID", (0, 0), (-1, -1), 0.25, WHITE),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 9),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 9),
            ]
        )
    )
    return tbl


def pdf_response(buffer: BytesIO, filename: str):
    buffer.seek(0)
    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def profile_rows(profile, policy_number, creator):
    return [
        ["Insured", clean(profile.get("business_name")) or "Selected Account"],
        ["Writing Carrier", clean(profile.get("writing_carrier")) or clean(profile.get("carrier_name")) or "-"],
        ["Carrier", clean(profile.get("carrier_name")) or "-"],
        ["Producing Agency", clean(profile.get("agency_name")) or "-"],
        ["Account / Policy", clean(policy_number) or clean(profile.get("policy_number")) or "-"],
        ["Account Number", clean(profile.get("account_number")) or clean(profile.get("customer_number")) or "-"],
        ["Effective Date", clean(profile.get("effective_date")) or "-"],
        ["Expiration Date", clean(profile.get("expiration_date")) or "-"],
        ["Evaluation Date", clean(profile.get("evaluation_date")) or datetime.utcnow().date().isoformat()],
        ["Report Created By", creator],
    ]


def policy_schedule_table(profile, policy_numbers_used):
    policies = profile.get("policies") or []
    rows = [["Policy Type", "Policy Number", "Carrier", "Effective", "Expiration"]]
    if policies:
        for item in policies:
            rows.append(
                [
                    clean(item.get("policy_type") or item.get("line_coverage") or item.get("line_of_business") or "Needs Review"),
                    clean(item.get("policy_number")) or "-",
                    clean(item.get("writing_carrier") or item.get("carrier") or profile.get("carrier_name")) or "-",
                    clean(item.get("effective_date")) or "-",
                    clean(item.get("expiration_date")) or "-",
                ]
            )
    elif policy_numbers_used:
        for pn in policy_numbers_used:
            rows.append(["Account Policy", pn, clean(profile.get("carrier_name")) or "-", "-", "-"])
    else:
        rows.append(["No policy schedule available", "-", "-", "-", "-"])
    return rows


def top_claim_rows(claims, max_rows=15):
    rows = [["Claim #", "Line", "Status", "Paid", "Reserve", "Total", "Policy", "Flag"]]
    sorted_claims = sorted(claims, key=lambda c: money(getattr(c, "total_incurred", 0)), reverse=True)[:max_rows]
    if not sorted_claims:
        rows.append(["No claims", "-", "-", "$0", "$0", "$0", "-", "-"])
        return rows
    for c in sorted_claims:
        rows.append(
            [
                clean(claim_attr(c, "claim_number", default="-")),
                clean(claim_attr(c, "line_of_business", "claim_type", default="-")),
                clean(claim_attr(c, "status", default="-")),
                dollars(getattr(c, "paid_amount", 0)),
                dollars(getattr(c, "reserve_amount", 0)),
                dollars(getattr(c, "total_incurred", 0)),
                clean(claim_attr(c, "policy_number", default="-")),
                clean(claim_attr(c, "flag", default="-")) or "-",
            ]
        )
    return rows


def cover(story, styles, report_title, profile, policy_number, creator):
    story.append(Spacer(1, 0.18 * inch))
    logo = logo_flowable(2.25 * inch)
    logo_table = Table([[logo]], colWidths=[7.0 * inch])
    logo_table.setStyle(TableStyle([("ALIGN", (0, 0), (-1, -1), "CENTER")]))
    story.append(logo_table)
    story.append(Spacer(1, 0.18 * inch))
    story.append(title(report_title, styles))
    story.append(subtitle("Renewal, claims, and underwriting intelligence summary.", styles))
    story.append(table(profile_rows(profile, policy_number or profile.get("policy_number"), creator), widths=[1.7 * inch, 5.0 * inch], header=False, font_size=8.2))


@router.get("/executive-report-pdf")
def executive_report_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ctx = build_context(db, current_user, policy_number)
    profile = ctx["profile"]
    metrics = ctx["metrics"]
    summary = ctx["summary"]
    forecast = ctx["forecast"]
    appetite = ctx["appetite"]
    carrier_match = ctx["carrier_match"]
    claims = ctx["claims"]
    creator = ctx["creator"]

    buffer, doc, styles = make_doc("LossQ Executive Underwriting Report")
    story = []
    insured = clean(profile.get("business_name")) or "Selected Account"
    risk_level = clean(summary.get("renewal_risk_level") or summary.get("risk_level") or "Not Rated")
    renewal_score = summary.get("renewal_score")

    cover(story, styles, "Executive Underwriting Report", profile, policy_number, creator)
    story.append(Spacer(1, 0.18 * inch))
    story.append(risk_banner(renewal_score, risk_level, styles))

    story.append(heading("Executive Summary", styles))
    story.append(p(summary.get("renewal_summary") or summary.get("summary") or f"{insured} has {metrics['total_claims']} claim(s) and total incurred losses of {dollars(metrics['total_incurred'])}.", styles))

    story.append(kpi_cards([
        ("Total Claims", metrics["total_claims"]),
        ("Open Claims", metrics["open_claims"]),
        ("Total Incurred", dollars(metrics["total_incurred"])),
        ("Litigation Claims", metrics["litigation_claims"]),
    ], styles))
    story.append(Spacer(1, 0.12 * inch))
    story.append(kpi_cards([
        ("Total Paid", dollars(metrics["total_paid"])),
        ("Total Reserve", dollars(metrics["total_reserve"])),
        ("Largest Loss", dollars(metrics.get("largest_loss", 0))),
        ("Flagged Claims", metrics.get("flagged_claims", 0)),
    ], styles))

    story.append(heading("Premium Forecast", styles))
    story.append(table([
        ["Current Premium", "Estimated Renewal", "Increase %", "Confidence"],
        [
            dollars(forecast.get("current_premium")),
            dollars(forecast.get("expected_renewal_premium")),
            pct(forecast.get("expected_increase_percent")),
            pct(forecast.get("confidence_score")),
        ],
    ], widths=[1.7 * inch] * 4, header_color=BLUE))
    story.append(p(forecast.get("forecast_summary") or "No premium forecast summary available.", styles))

    story.append(heading("Carrier Appetite and Market Match", styles))
    story.append(table([
        ["Appetite Score", "Appetite Level", "Recommended Carrier", "Match Score"],
        [
            f"{appetite.get('carrier_appetite_score')}/100" if appetite.get("carrier_appetite_score") is not None else "-",
            appetite.get("carrier_appetite_level") or "-",
            carrier_match.get("recommended_carrier") or "-",
            f"{carrier_match.get('recommended_score')}/100" if carrier_match.get("recommended_score") is not None else "-",
        ],
    ], widths=[1.7 * inch] * 4, header_color=PURPLE))
    story.append(p(carrier_match.get("carrier_match_summary") or appetite.get("placement_summary") or "No carrier match summary available.", styles))

    story.append(heading("Policy Schedule", styles))
    story.append(table(policy_schedule_table(profile, ctx["policy_numbers_used"]), widths=[1.45 * inch, 1.75 * inch, 1.45 * inch, 1.0 * inch, 1.0 * inch], header_color=NAVY))

    story.append(PageBreak())
    story.append(heading("Top Claims by Total Incurred", styles))
    story.append(table(top_claim_rows(claims), widths=[0.9 * inch, 1.0 * inch, 0.72 * inch, 0.78 * inch, 0.78 * inch, 0.78 * inch, 1.25 * inch, 0.85 * inch], font_size=7.2, header_color=NAVY))

    story.append(heading("Broker Action Plan", styles))
    actions = summary.get("recommended_actions") or summary.get("renewal_drivers") or []
    if not actions:
        actions = ["Prepare current loss runs, open claim updates, reserve commentary, litigation status, and corrective action details before market submission."]
    for index, action in enumerate(actions, start=1):
        story.append(p(f"{index}. {action}", styles))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Disclaimer: This report is generated from available claim and account data inside LossQ. All figures should be reviewed against current carrier loss runs and confirmed before formal submission.", styles["SmallMuted"]))

    doc.build(
        story,
        onFirstPage=lambda canvas, doc: draw_header_footer(canvas, doc, "Executive Report", creator),
        onLaterPages=lambda canvas, doc: draw_header_footer(canvas, doc, "Executive Report", creator),
    )
    return pdf_response(buffer, "lossq_executive_underwriting_report.pdf")


@router.get("/carrier-packet-pdf")
def carrier_packet_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ctx = build_context(db, current_user, policy_number)
    profile = ctx["profile"]
    metrics = ctx["metrics"]
    summary = ctx["summary"]
    forecast = ctx["forecast"]
    carrier_match = ctx["carrier_match"]
    claims = ctx["claims"]
    creator = ctx["creator"]

    buffer, doc, styles = make_doc("LossQ Carrier Submission Packet")
    story = []
    insured = clean(profile.get("business_name")) or "Selected Account"
    risk_level = clean(summary.get("renewal_risk_level") or "Not Rated")
    renewal_score = summary.get("renewal_score")

    cover(story, styles, "Carrier Submission Packet", profile, policy_number, creator)
    story.append(Spacer(1, 0.18 * inch))
    story.append(risk_banner(renewal_score, risk_level, styles))

    story.append(heading("Submission Snapshot", styles))
    story.append(kpi_cards([
        ("Claim Count", metrics["total_claims"]),
        ("Open Claims", metrics["open_claims"]),
        ("Paid Losses", dollars(metrics["total_paid"])),
        ("Open Reserves", dollars(metrics["total_reserve"])),
    ], styles))
    story.append(Spacer(1, 0.12 * inch))
    story.append(kpi_cards([
        ("Total Incurred", dollars(metrics["total_incurred"])),
        ("Litigation Claims", metrics["litigation_claims"]),
        ("Flagged Claims", metrics.get("flagged_claims", 0)),
        ("Recommended Market", carrier_match.get("recommended_carrier") or "-"),
    ], styles))

    story.append(heading("Broker Marketing Narrative", styles))
    story.append(p(summary.get("broker_recommendation") or summary.get("renewal_summary") or f"This submission presents {insured} for carrier underwriting review based on {metrics['total_claims']} account-specific claim(s).", styles))

    story.append(heading("Policy Schedule", styles))
    story.append(table(policy_schedule_table(profile, ctx["policy_numbers_used"]), widths=[1.45 * inch, 1.75 * inch, 1.45 * inch, 1.0 * inch, 1.0 * inch], header_color=NAVY))

    story.append(heading("Loss Summary", styles))
    story.append(table([
        ["Metric", "Value"],
        ["Total Claims", metrics["total_claims"]],
        ["Open Claims", metrics["open_claims"]],
        ["Closed Claims", metrics["closed_claims"]],
        ["Litigation / Attorney Claims", metrics["litigation_claims"]],
        ["Flagged Claims", metrics["flagged_claims"]],
        ["Total Paid", dollars(metrics["total_paid"])],
        ["Total Reserve", dollars(metrics["total_reserve"])],
        ["Total Incurred", dollars(metrics["total_incurred"])],
    ], widths=[2.4 * inch, 4.3 * inch], header_color=BLUE))

    story.append(PageBreak())
    story.append(heading("Claim Narratives and Underwriting Notes", styles))
    story.append(table(top_claim_rows(claims, max_rows=25), widths=[0.9 * inch, 1.0 * inch, 0.72 * inch, 0.78 * inch, 0.78 * inch, 0.78 * inch, 1.25 * inch, 0.85 * inch], font_size=7.2, header_color=NAVY))

    story.append(heading("Renewal Strategy", styles))
    strategy = summary.get("broker_recommendation") or "Provide updated loss runs, open-claim status, reserve explanations, litigation updates, and corrective-action documentation before approaching markets."
    story.append(p(strategy, styles))
    story.append(p(f"Recommended market: {carrier_match.get('recommended_carrier') or 'To be determined'} with match score {carrier_match.get('recommended_score', '-')}/100.", styles))
    story.append(p(f"Premium forecast: {dollars(forecast.get('expected_renewal_premium'))}, modeled change {forecast.get('expected_increase_percent', '-')}%.", styles))

    story.append(heading("Carrier Submission Email Draft", styles))
    email_text = (
        f"Subject: Renewal Submission - {insured}\n\n"
        f"Please find attached the renewal submission package for {insured}. "
        f"LossQ reviewed {metrics['total_claims']} account-specific claim(s), "
        f"{metrics['open_claims']} open claim(s), total incurred losses of {dollars(metrics['total_incurred'])}, "
        f"reserves of {dollars(metrics['total_reserve'])}, and {metrics['litigation_claims']} litigation-related claim(s). "
        f"The modeled renewal score is {renewal_score}/100 and the account is rated {risk_level}. "
        f"Please advise if additional loss-control, vehicle, payroll, operations, reserve, or litigation information is needed for quoting consideration.\n\n"
        f"Prepared by: {creator}"
    )
    story.append(p(email_text, styles))

    story.append(Spacer(1, 10))
    story.append(Paragraph("Disclaimer: This carrier packet is generated from available claim and account data inside LossQ. All figures should be reviewed against current carrier loss runs and confirmed before formal submission.", styles["SmallMuted"]))

    doc.build(
        story,
        onFirstPage=lambda canvas, doc: draw_header_footer(canvas, doc, "Carrier Packet", creator),
        onLaterPages=lambda canvas, doc: draw_header_footer(canvas, doc, "Carrier Packet", creator),
    )
    return pdf_response(buffer, "lossq_carrier_submission_packet.pdf")


@router.get("/loss-run-template-pdf")
def loss_run_template_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    ctx = build_context(db, current_user, policy_number)
    profile = ctx["profile"]
    claims = ctx["claims"]
    metrics = ctx["metrics"]
    creator = ctx["creator"]

    buffer, doc, styles = make_doc("LossQ Carrier Loss Run")
    story = []
    cover(story, styles, "Carrier Loss Run", profile, policy_number, creator)
    story.append(heading("Loss Totals", styles))
    story.append(table([
        ["Total Claims", "Open Claims", "Total Paid", "Total Reserve", "Total Incurred"],
        [metrics["total_claims"], metrics["open_claims"], dollars(metrics["total_paid"]), dollars(metrics["total_reserve"]), dollars(metrics["total_incurred"])],
    ], widths=[1.35 * inch] * 5, header_color=BLUE))
    story.append(heading("Claims", styles))
    story.append(table(top_claim_rows(claims, max_rows=50), widths=[0.9 * inch, 1.0 * inch, 0.72 * inch, 0.78 * inch, 0.78 * inch, 0.78 * inch, 1.25 * inch, 0.85 * inch], font_size=7.2, header_color=NAVY))
    doc.build(
        story,
        onFirstPage=lambda canvas, doc: draw_header_footer(canvas, doc, "Loss Run", creator),
        onLaterPages=lambda canvas, doc: draw_header_footer(canvas, doc, "Loss Run", creator),
    )
    return pdf_response(buffer, "lossq_carrier_loss_run.pdf")
