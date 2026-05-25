from fastapi import APIRouter, Depends, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from reportlab.lib.pagesizes import letter, landscape
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
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


@router.get("/underwriting-pdf")
def underwriting_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    return loss_run_template_pdf(policy_number, db, current_user)


@router.get("/loss-run-template-pdf")
def loss_run_template_pdf(
    policy_number: str | None = Query(default=None),
    db: Session = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    org_id = current_user["organization_id"]

    claims = get_claims(db, org_id, policy_number)
    profile = get_profile(db, org_id, policy_number)

    safe_policy = (profile["policy_number"] or "selected_policy").replace("/", "_").replace("\\", "_")
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
                    "",
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