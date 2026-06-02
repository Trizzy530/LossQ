from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate,
    Table,
    TableStyle,
    Paragraph,
    Spacer,
    PageBreak,
    Image,
)

from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from datetime import datetime
import os

from app.database import SessionLocal
from app.models.claim import Claim
from app.models.account_profile import AccountProfile
from app.auth_utils import get_current_user
from app.routes.claims import build_claim_ai_analysis

router = APIRouter(prefix="/reports", tags=["Reports"])

REPORT_DIR = "reports"
os.makedirs(REPORT_DIR, exist_ok=True)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def money(value):
    return f"${float(value or 0):,.0f}"


def pct(value):
    try:
        return f"{float(value or 0):.1f}%"
    except Exception:
        return "0.0%"


def safe_text(value):
    return str(value or "").strip() or "-"


def safe_file(value):
    return (
        str(value or "selected_policy")
        .replace("/", "_")
        .replace("\\", "_")
        .replace(" ", "_")
    )


def get_profile(db, org_id, policy_number=None):
    query = db.query(AccountProfile).filter(AccountProfile.organization_id == org_id)

    if policy_number:
        profile = query.filter(AccountProfile.policy_number == policy_number).first()
    else:
        profile = query.order_by(AccountProfile.id.desc()).first()

    if not profile:
        return {
            "business_name": "",
            "carrier_name": "",
            "agency_name": "",
            "policy_number": policy_number or "",
            "effective_date": "",
            "expiration_date": "",
            "evaluation_date": datetime.now().strftime("%m/%d/%Y"),
        }

    return {
        "business_name": profile.business_name or "",
        "carrier_name": profile.carrier_name or "",
        "agency_name": profile.agency_name or "",
        "policy_number": profile.policy_number or "",
        "effective_date": profile.effective_date or "",
        "expiration_date": profile.expiration_date or "",
        "evaluation_date": profile.evaluation_date or datetime.now().strftime("%m/%d/%Y"),
    }


def get_claims(db, org_id, policy_number=None):
    query = db.query(Claim).filter(Claim.organization_id == org_id)

    if policy_number:
        query = query.filter(Claim.policy_number == policy_number)

    return query.order_by(Claim.id.asc()).all()


def claim_totals(claims):
    total_paid = sum(float(c.paid_amount or 0) for c in claims)
    total_reserve = sum(float(c.reserve_amount or 0) for c in claims)
    total_incurred = sum(float(c.total_incurred or 0) for c in claims)
    open_claims = len([c for c in claims if str(c.status or "").lower() == "open"])
    litigation_claims = len([c for c in claims if c.litigation or c.attorney_assigned])

    return {
        "claim_count": len(claims),
        "open_claims": open_claims,
        "closed_claims": max(len(claims) - open_claims, 0),
        "litigation_claims": litigation_claims,
        "total_paid": total_paid,
        "total_reserve": total_reserve,
        "total_incurred": total_incurred,
    }


def renewal_score_from_claims(claims):
    totals = claim_totals(claims)
    score = 100

    if totals["claim_count"] >= 10:
        score -= 20
    elif totals["claim_count"] >= 5:
        score -= 12
    elif totals["claim_count"] >= 2:
        score -= 6

    if totals["open_claims"] >= 3:
        score -= 18
    elif totals["open_claims"] >= 1:
        score -= 8

    if totals["litigation_claims"] >= 2:
        score -= 20
    elif totals["litigation_claims"] >= 1:
        score -= 12

    if totals["total_incurred"] >= 250000:
        score -= 25
    elif totals["total_incurred"] >= 100000:
        score -= 16
    elif totals["total_incurred"] >= 50000:
        score -= 8

    score = max(0, min(100, score))

    if score >= 80:
        level = "Low"
    elif score >= 60:
        level = "Moderate"
    elif score >= 40:
        level = "High"
    else:
        level = "Critical"

    return score, level


def build_report_styles():
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="LossQTitle",
            parent=styles["Title"],
            fontSize=26,
            leading=31,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=14,
        )
    )

    styles.add(
        ParagraphStyle(
            name="LossQSubtitle",
            parent=styles["Normal"],
            fontSize=11,
            leading=16,
            textColor=colors.HexColor("#475569"),
            spaceAfter=12,
        )
    )

    styles.add(
        ParagraphStyle(
            name="LossQSection",
            parent=styles["Heading2"],
            fontSize=16,
            leading=20,
            textColor=colors.HexColor("#1d4ed8"),
            spaceBefore=10,
            spaceAfter=8,
        )
    )

    styles.add(
        ParagraphStyle(
            name="LossQBody",
            parent=styles["Normal"],
            fontSize=9,
            leading=13,
            textColor=colors.HexColor("#1e293b"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="LossQSmall",
            parent=styles["Normal"],
            fontSize=7.5,
            leading=10,
            textColor=colors.HexColor("#334155"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="LossQWhite",
            parent=styles["Normal"],
            fontSize=10,
            leading=13,
            textColor=colors.white,
        )
    )

    return styles


def apply_clean_table_style(table, header_color="#1d4ed8"):
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor(header_color)),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#cbd5e1")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.HexColor("#f8fafc")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )
    return table

def add_cover(story, styles, title, subtitle, profile):
    story.append(Spacer(1, 0.35 * inch))

    logo_path = os.path.join(REPORT_DIR, "lossq-logo-style2.png")

    if os.path.exists(logo_path):
        story.append(
            Image(
                logo_path,
                width=2.8 * inch,
                height=0.85 * inch,
            )
        )
        story.append(Spacer(1, 14))
    else:
        story.append(Paragraph("LossQ", styles["LossQTitle"]))

    story.append(Paragraph(title, styles["LossQTitle"]))
    story.append(Paragraph(subtitle, styles["LossQSubtitle"]))

    cover_table = Table(
        [
            ["Insured", safe_text(profile["business_name"])],
            ["Carrier", safe_text(profile["carrier_name"])],
            ["Agency", safe_text(profile["agency_name"])],
            ["Policy Number", safe_text(profile["policy_number"])],
            ["Policy Period", f'{safe_text(profile["effective_date"])} - {safe_text(profile["expiration_date"])}'],
            ["Evaluation Date", safe_text(profile["evaluation_date"])],
        ],
        colWidths=[1.7 * inch, 4.7 * inch],
    )

    apply_clean_table_style(cover_table)

    story.append(Spacer(1, 18))
    story.append(cover_table)
    story.append(Spacer(1, 24))

    story.append(
        Paragraph(
            "Prepared by LossQ AI Underwriting Suite for broker, carrier, and renewal strategy review.",
            styles["LossQSubtitle"],
        )
    )

    story.append(PageBreak())





@router.get("/underwriting-pdf")
def underwriting_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return executive_report_pdf(policy_number, db, current_user)


@router.get("/executive-report-pdf")
def executive_report_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    org_id = current_user["organization_id"]
    claims = get_claims(db, org_id, policy_number)
    profile = get_profile(db, org_id, policy_number)
    totals = claim_totals(claims)
    renewal_score, risk_level = renewal_score_from_claims(claims)

    safe_policy = safe_file(profile["policy_number"])
    file_path = os.path.join(REPORT_DIR, f"lossq_executive_report_{safe_policy}.pdf")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
    )

    styles = build_report_styles()
    story = []

    add_cover(
        story,
        styles,
        "Executive Underwriting Report",
        "Boardroom-style renewal, claims, and underwriting intelligence summary.",
        profile,
    )

    story.append(Paragraph("Executive Summary", styles["LossQSection"]))

    summary_text = (
        f"{safe_text(profile['business_name'])} currently has {totals['claim_count']} claim(s) "
        f"associated with this policy period. Total incurred loss is {money(totals['total_incurred'])}, "
        f"with paid losses of {money(totals['total_paid'])} and active reserves of "
        f"{money(totals['total_reserve'])}. LossQ assigns this account a renewal score of "
        f"{renewal_score}/100 with a {risk_level} renewal risk level."
    )

    story.append(Paragraph(summary_text, styles["LossQBody"]))
    story.append(Spacer(1, 12))

    if renewal_score >= 80:
        badge_color = "#16a34a"
    elif renewal_score >= 60:
        badge_color = "#eab308"
    else:
        badge_color = "#dc2626"

    score_badge = Table(
        [[f"Renewal Score: {renewal_score}/100"]],
        colWidths=[2.5 * inch],
    )

    score_badge.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor(badge_color)),
                ("TEXTCOLOR", (0, 0), (-1, -1), colors.white),
                ("FONTNAME", (0, 0), (-1, -1), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 18),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 10),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 10),
                ("BOX", (0, 0), (-1, -1), 1, colors.white),
            ]
        )
    )

    story.append(score_badge)
    story.append(Spacer(1, 12))

    metrics = Table(

        [
            ["Renewal Score", "Risk Level", "Total Claims", "Open Claims"],
            [f"{renewal_score}/100", risk_level, str(totals["claim_count"]), str(totals["open_claims"])],
            ["Total Paid", "Total Reserve", "Total Incurred", "Litigation Claims"],
            [
                money(totals["total_paid"]),
                money(totals["total_reserve"]),
                money(totals["total_incurred"]),
                str(totals["litigation_claims"]),
            ],
        ],
        colWidths=[1.6 * inch, 1.6 * inch, 1.6 * inch, 1.6 * inch],
    )
    apply_clean_table_style(metrics, "#0f172a")
    story.append(metrics)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Renewal Intelligence", styles["LossQSection"]))

    drivers = []
    if totals["open_claims"] > 0:
        drivers.append(f"{totals['open_claims']} open claim(s) requiring carrier explanation.")
    if totals["litigation_claims"] > 0:
        drivers.append(f"{totals['litigation_claims']} claim(s) involve litigation or attorney assignment.")
    if totals["total_reserve"] > 0:
        drivers.append(f"Outstanding reserves total {money(totals['total_reserve'])}.")
    if totals["total_incurred"] >= 100000:
        drivers.append("Large-loss severity may create underwriting pressure.")
    if not drivers:
        drivers.append("No major renewal pressure indicators detected from current claim data.")

    for item in drivers:
        story.append(Paragraph(f"• {item}", styles["LossQBody"]))

    story.append(Spacer(1, 12))

    story.append(Paragraph("Broker Recommendation", styles["LossQSection"]))

    recommendation = (
        "Prepare a complete renewal submission with clear explanations for open claims, reserve strategy, "
        "large losses, and litigation activity. Include corrective action details, updated claim statuses, "
        "and a concise broker narrative positioning the account for the best available carrier appetite."
    )
    story.append(Paragraph(recommendation, styles["LossQBody"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Top Claims by Total Incurred", styles["LossQSection"]))

    top_claims = sorted(claims, key=lambda c: float(c.total_incurred or 0), reverse=True)[:8]

    claim_rows = [["Claim #", "Line", "Status", "Paid", "Reserve", "Total", "Flag"]]
    for c in top_claims:
        claim_rows.append(
            [
                safe_text(c.claim_number),
                safe_text(c.line_of_business),
                safe_text(c.status),
                money(c.paid_amount),
                money(c.reserve_amount),
                money(c.total_incurred),
                Paragraph(safe_text(c.flag), styles["LossQSmall"]),
            ]
        )

    if len(claim_rows) == 1:
        claim_rows.append(["No claims", "-", "-", "$0", "$0", "$0", "-"])

    claim_table = Table(
        claim_rows,
         colWidths=[
             1.0 * inch,
             1.15 * inch,
             0.85 * inch,
             0.85 * inch,
             0.85 * inch,
             0.95 * inch,
             1.75 * inch,
],
    )
    apply_clean_table_style(claim_table, "#1d4ed8")
    story.append(claim_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Executive Closing Summary", styles["LossQSection"]))
    story.append(
        Paragraph(
            "This report is designed for executive review and renewal strategy planning. "
            "It should be used alongside current carrier loss runs, updated claim notes, "
            "client operations information, and broker market knowledge.",
            styles["LossQBody"],
        )
    )

    doc.build(story)

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"lossq_executive_report_{safe_policy}.pdf",
    )
@router.get("/carrier-packet-pdf")
def carrier_packet_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    org_id = current_user["organization_id"]
    claims = get_claims(db, org_id, policy_number)
    profile = get_profile(db, org_id, policy_number)
    totals = claim_totals(claims)
    renewal_score, risk_level = renewal_score_from_claims(claims)

    safe_policy = safe_file(profile["policy_number"])
    file_path = os.path.join(REPORT_DIR, f"lossq_carrier_packet_{safe_policy}.pdf")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=letter,
        rightMargin=42,
        leftMargin=42,
        topMargin=42,
        bottomMargin=42,
    )

    styles = build_report_styles()
    story = []

    add_cover(
        story,
        styles,
        "Carrier Submission Packet",
        "Underwriter-ready account narrative, loss analysis, claim explanations, and broker positioning.",
        profile,
    )

    story.append(Paragraph("Insured Overview", styles["LossQSection"]))

    overview_table = Table(
        [
            ["Insured", safe_text(profile["business_name"])],
            ["Writing Carrier", safe_text(profile["carrier_name"])],
            ["Producing Agency", safe_text(profile["agency_name"])],
            ["Policy Number", safe_text(profile["policy_number"])],
            ["Policy Period", f'{safe_text(profile["effective_date"])} - {safe_text(profile["expiration_date"])}'],
            ["Evaluation Date", safe_text(profile["evaluation_date"])],
        ],
        colWidths=[1.7 * inch, 4.7 * inch],
    )
    apply_clean_table_style(overview_table, "#0f172a")
    story.append(overview_table)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Submission Snapshot", styles["LossQSection"]))

    snapshot = Table(
        [
            ["Renewal Score", "Risk Level", "Claim Count", "Open Claims"],
            [f"{renewal_score}/100", risk_level, str(totals["claim_count"]), str(totals["open_claims"])],
            ["Paid Losses", "Open Reserves", "Total Incurred", "Litigation Claims"],
            [
                money(totals["total_paid"]),
                money(totals["total_reserve"]),
                money(totals["total_incurred"]),
                str(totals["litigation_claims"]),
            ],
        ],
        colWidths=[1.6 * inch, 1.6 * inch, 1.6 * inch, 1.6 * inch],
    )
    apply_clean_table_style(snapshot, "#1d4ed8")
    story.append(snapshot)
    story.append(Spacer(1, 14))

    story.append(Paragraph("Broker Marketing Narrative", styles["LossQSection"]))

    broker_narrative = (
        f"This submission package presents {safe_text(profile['business_name'])} for carrier underwriting review. "
        f"The account has {totals['claim_count']} claim(s), {totals['open_claims']} open claim(s), "
        f"and total incurred losses of {money(totals['total_incurred'])}. "
        f"LossQ classifies the account as {risk_level} renewal risk with a score of {renewal_score}/100. "
        f"The broker should position this submission with clear claim explanations, current reserve updates, "
        f"litigation status, and any corrective actions taken by the insured."
    )
    story.append(Paragraph(broker_narrative, styles["LossQBody"]))
    story.append(Spacer(1, 14))

    story.append(Paragraph("Loss Summary", styles["LossQSection"]))

    loss_summary = Table(
        [
            ["Metric", "Value"],
            ["Total Claims", str(totals["claim_count"])],
            ["Open Claims", str(totals["open_claims"])],
            ["Closed Claims", str(totals["closed_claims"])],
            ["Litigation / Attorney Claims", str(totals["litigation_claims"])],
            ["Total Paid", money(totals["total_paid"])],
            ["Total Reserve", money(totals["total_reserve"])],
            ["Total Incurred", money(totals["total_incurred"])],
        ],
        colWidths=[2.5 * inch, 3.5 * inch],
    )
    apply_clean_table_style(loss_summary, "#0f766e")
    story.append(loss_summary)
    story.append(PageBreak())

    story.append(Paragraph("Claim Narratives & Underwriting Notes", styles["LossQSection"]))

    top_claims = sorted(claims, key=lambda c: float(c.total_incurred or 0), reverse=True)

    if not top_claims:
        story.append(Paragraph("No claims are available for this submission package.", styles["LossQBody"]))

    for claim in top_claims:
        analysis = build_claim_ai_analysis(claim)

        claim_title = (
            f"Claim {safe_text(claim.claim_number)} | "
            f"{safe_text(claim.line_of_business)} | "
            f"{money(claim.total_incurred)}"
        )

        story.append(Paragraph(claim_title, styles["LossQSection"]))

        claim_table = Table(
            [
                ["Status", "Date of Loss", "Paid", "Reserve", "Total Incurred"],
                [
                    safe_text(claim.status),
                    safe_text(claim.date_of_loss),
                    money(claim.paid_amount),
                    money(claim.reserve_amount),
                    money(claim.total_incurred),
                ],
            ],
            colWidths=[1.2 * inch, 1.3 * inch, 1.2 * inch, 1.2 * inch, 1.4 * inch],
        )
        apply_clean_table_style(claim_table, "#334155")
        story.append(claim_table)
        story.append(Spacer(1, 8))

        story.append(Paragraph("<b>Underwriter Narrative</b>", styles["LossQSmall"]))
        story.append(
            Paragraph(
                analysis.get("underwriter_narrative")
                or analysis.get("ai_summary")
                or "No underwriter narrative available.",
                styles["LossQBody"],
            )
        )
        story.append(Spacer(1, 6))

        story.append(Paragraph("<b>Risk Summary</b>", styles["LossQSmall"]))
        story.append(
            Paragraph(
                analysis.get("risk_summary")
                or "No risk summary available.",
                styles["LossQBody"],
            )
        )
        story.append(Spacer(1, 6))

        story.append(Paragraph("<b>Litigation Analysis</b>", styles["LossQSmall"]))
        story.append(
            Paragraph(
                analysis.get("litigation_analysis")
                or analysis.get("litigation_exposure")
                or "No litigation analysis available.",
                styles["LossQBody"],
            )
        )
        story.append(Spacer(1, 6))

        talking_points = analysis.get("broker_talking_points") or analysis.get("broker_actions") or []
        if talking_points:
            story.append(Paragraph("<b>Broker Talking Points</b>", styles["LossQSmall"]))
            for point in talking_points:
                story.append(Paragraph(f"• {point}", styles["LossQBody"]))

        story.append(Spacer(1, 14))

    story.append(PageBreak())
    story.append(Paragraph("Renewal Strategy", styles["LossQSection"]))

    strategy_items = []

    if totals["open_claims"] > 0:
        strategy_items.append("Provide updated open-claim status and expected closure timeline.")
    if totals["total_reserve"] > 0:
        strategy_items.append("Explain current reserve strategy and expected reserve movement.")
    if totals["litigation_claims"] > 0:
        strategy_items.append("Include defense counsel update and litigation posture.")
    if totals["total_incurred"] >= 100000:
        strategy_items.append("Prepare large-loss explanation and corrective action summary.")
    if not strategy_items:
        strategy_items.append("Position the account as clean, controlled, and ready for standard market review.")

    for item in strategy_items:
        story.append(Paragraph(f"• {item}", styles["LossQBody"]))

    story.append(Spacer(1, 14))

    story.append(Paragraph("Carrier Submission Email Draft", styles["LossQSection"]))

    email_text = (
        f"Please find attached the renewal submission package for {safe_text(profile['business_name'])}. "
        f"The account reflects {totals['claim_count']} claim(s), total incurred losses of "
        f"{money(totals['total_incurred'])}, and a LossQ renewal score of {renewal_score}/100. "
        f"We have included claim narratives, reserve commentary, litigation review, and broker positioning "
        f"to support underwriting review. Please advise if additional loss control, payroll, vehicle, or operations "
        f"information is needed for quoting consideration."
    )
    story.append(Paragraph(email_text, styles["LossQBody"]))

    story.append(Spacer(1, 18))
    story.append(
        Paragraph(
            "Disclaimer: This carrier packet is generated from available claim and account data inside LossQ. "
            "All figures should be reviewed against current carrier loss runs and confirmed before formal submission.",
            styles["LossQSmall"],
        )
    )

    doc.build(story)

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"lossq_carrier_packet_{safe_policy}.pdf",
    )


@router.get("/loss-run-template-pdf")
def loss_run_template_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    org_id = current_user["organization_id"]

    claims = get_claims(db, org_id, policy_number)
    profile = get_profile(db, org_id, policy_number)

    safe_policy = safe_file(profile["policy_number"])
    file_path = os.path.join(REPORT_DIR, f"lossq_loss_run_{safe_policy}.pdf")

    doc = SimpleDocTemplate(
        file_path,
        pagesize=landscape(letter),
        rightMargin=30,
        leftMargin=30,
        topMargin=30,
        bottomMargin=30,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "TitleGreen",
        parent=styles["Title"],
        textColor=colors.HexColor("#1f5c3b"),
        fontSize=18,
        spaceAfter=12,
    )

    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        textColor=colors.HexColor("#1f5c3b"),
        fontSize=13,
        spaceAfter=8,
    )

    small = ParagraphStyle(
        "Small",
        parent=styles["Normal"],
        fontSize=8,
        leading=10,
    )

    story = []

    story.append(Paragraph(profile["carrier_name"] or "Carrier Loss Run", title_style))
    story.append(Paragraph("Summary Loss History", section_style))

    story.append(
        Table(
            [
                ["Carrier", profile["carrier_name"], "Evaluation Date", profile["evaluation_date"]],
                ["Insured", profile["business_name"], "Agency", profile["agency_name"]],
                ["Policy Number", profile["policy_number"], "Effective", f'{profile["effective_date"]} - {profile["expiration_date"]}'],
            ],
            colWidths=[1.2 * inch, 3.2 * inch, 1.3 * inch, 2.8 * inch],
        )
    )

    story.append(Spacer(1, 12))

    total_paid = sum(float(c.paid_amount or 0) for c in claims)
    total_reserve = sum(float(c.reserve_amount or 0) for c in claims)
    total_incurred = sum(float(c.total_incurred or 0) for c in claims)

    summary_table = Table(
        [
            [
                "Coverage Type",
                "Claim Count",
                "Paid Loss",
                "Paid Expenses",
                "Case Loss & Expense Reserve",
                "Gross Incurred",
                "Recoveries",
                "Net Incurred",
            ],
            [
                "All Lines",
                len(claims),
                money(total_paid),
                "$0",
                money(total_reserve),
                money(total_incurred),
                "$0",
                money(total_incurred),
            ],
        ],
        colWidths=[
            1.8 * inch,
            0.9 * inch,
            1.1 * inch,
            1.1 * inch,
            1.8 * inch,
            1.2 * inch,
            1.1 * inch,
            1.2 * inch,
        ],
    )

    summary_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8efe3")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f5c3b")),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#29513a")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
            ]
        )
    )

    story.append(summary_table)
    story.append(PageBreak())

    story.append(Paragraph("Detail Loss History", title_style))

    policy_table = Table(
        [
            ["Policy Number", profile["policy_number"]],
            ["Effective", f'{profile["effective_date"]} - {profile["expiration_date"]}'],
            ["Insured", profile["business_name"]],
            ["Agency", profile["agency_name"]],
        ],
        colWidths=[1.3 * inch, 3.0 * inch],
    )

    policy_table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#eeeeee")),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.white),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
            ]
        )
    )

    story.append(policy_table)
    story.append(Spacer(1, 10))

    for claim in claims:
        analysis = build_claim_ai_analysis(claim)

        claim_header = Table(
            [
                ["Claim Number", "Status", "Loss Date", "Date Reported", "Policy"],
                [
                    claim.claim_number or "",
                    claim.status or "",
                    claim.date_of_loss or "",
                    claim.date_reported or "",
                    claim.policy_number or "",
                ],
            ],
            colWidths=[1.4 * inch, 1.2 * inch, 1.2 * inch, 1.3 * inch, 2.2 * inch],
        )

        claim_header.setStyle(
            TableStyle(
                [
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f5c3b")),
                    ("BACKGROUND", (1, 1), (1, 1), colors.HexColor("#777777")),
                    ("TEXTCOLOR", (1, 1), (1, 1), colors.white),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ]
            )
        )

        story.append(claim_header)
        story.append(Paragraph("<b>Loss Description</b>", small))
        story.append(Paragraph(str(claim.description or "No description provided."), small))
        story.append(Spacer(1, 4))

        detail_table = Table(
            [
                [
                    "Claimant",
                    "Coverage Type",
                    "Paid Loss Gross of Recovery",
                    "Paid Expenses",
                    "Case Loss & Expense Reserve",
                    "Gross Incurred",
                    "Recoveries",
                    "Deductible Recovery",
                    "Net Incurred",
                ],
                [
                    "Claimant / Insured",
                    claim.line_of_business or "Unknown",
                    money(claim.paid_amount),
                    "$0",
                    money(claim.reserve_amount),
                    money(claim.total_incurred),
                    "$0",
                    "$0",
                    money(claim.total_incurred),
                ],
                [
                    "Total",
                    "",
                    money(claim.paid_amount),
                    "$0",
                    money(claim.reserve_amount),
                    money(claim.total_incurred),
                    "$0",
                    "$0",
                    money(claim.total_incurred),
                ],
            ],
            colWidths=[
                1.1 * inch,
                1.1 * inch,
                1.2 * inch,
                1.0 * inch,
                1.4 * inch,
                1.0 * inch,
                1.2 * inch,
                1.2 * inch,
                1.0 * inch,
            ],
        )

        detail_table.setStyle(
            TableStyle(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#d8efe3")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f5c3b")),
                    ("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#29513a")),
                    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                    ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                    ("FONTSIZE", (0, 0), (-1, -1), 7),
                    ("ALIGN", (2, 1), (-1, -1), "RIGHT"),
                ]
            )
        )

        story.append(detail_table)
        story.append(Spacer(1, 6))

        story.append(Paragraph("<b>LossQ Claim Analysis</b>", small))
        story.append(
            Paragraph(
                f"Severity: {analysis['severity']} | Score: {analysis['severity_score']} | "
                f"Reserve Concern: {analysis['reserve_concern']} | Renewal Impact: {analysis['renewal_impact']}",
                small,
            )
        )
        story.append(Paragraph(analysis["ai_summary"], small))

        if analysis["broker_actions"]:
            story.append(Paragraph("<b>Broker Action Items</b>", small))
            for action in analysis["broker_actions"]:
                story.append(Paragraph(f"- {action}", small))

        story.append(Spacer(1, 16))

    disclaimer = (
        "This information is being provided for informational purposes only. "
        "LossQ does not make any express or implied representation or warranty "
        "as to the accuracy or completeness of the information."
    )

    story.append(Spacer(1, 20))
    story.append(Paragraph(disclaimer, small))

    doc.build(story)

    return FileResponse(
        file_path,
        media_type="application/pdf",
        filename=f"lossq_loss_run_{safe_policy}.pdf",
    )