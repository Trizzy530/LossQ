from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session
from datetime import datetime
from io import BytesIO
import html

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
    return html.escape(clean(value) or "-")


def claim_attr(claim, *names, default=""):
    for name in names:
        value = getattr(claim, name, None)
        if value not in [None, ""]:
            return value
    return default


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

    # Prefer summary metrics when the guardrail engine returned them.
    summary_metrics = summary.get("renewal_metrics") or summary.get("metrics") or {}
    for key in [
        "total_claims",
        "open_claims",
        "closed_claims",
        "litigation_claims",
        "flagged_claims",
        "total_paid",
        "total_reserve",
        "total_incurred",
    ]:
        if key in summary_metrics:
            metrics[key] = summary_metrics[key]

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
    }


def make_doc(title: str):
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=0.5 * inch,
        leftMargin=0.5 * inch,
        topMargin=0.5 * inch,
        bottomMargin=0.5 * inch,
        title=title,
    )
    styles = getSampleStyleSheet()
    styles.add(
        ParagraphStyle(
            name="LossQTitle",
            parent=styles["Title"],
            fontSize=22,
            leading=26,
            textColor=colors.HexColor("#0f172a"),
            spaceAfter=10,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LossQHeading",
            parent=styles["Heading2"],
            fontSize=14,
            leading=18,
            textColor=colors.HexColor("#1d4ed8"),
            spaceBefore=12,
            spaceAfter=8,
        )
    )
    styles.add(
        ParagraphStyle(
            name="LossQBody",
            parent=styles["BodyText"],
            fontSize=9,
            leading=12,
            spaceAfter=6,
        )
    )
    return buffer, doc, styles


def p(text, styles):
    return Paragraph(safe_text(text), styles["LossQBody"])


def heading(text, styles):
    return Paragraph(safe_text(text), styles["LossQHeading"])


def title(text, styles):
    return Paragraph(safe_text(text), styles["LossQTitle"])


def table(data, widths=None, header=True):
    tbl = Table(data, colWidths=widths, repeatRows=1 if header else 0)
    tbl.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1e293b") if header else colors.white),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white if header else colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("LEADING", (0, 0), (-1, -1), 10),
                ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#cbd5e1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#f8fafc")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
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


def profile_rows(profile, policy_number):
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
    else:
        for pn in policy_numbers_used:
            rows.append(["Account Policy", pn, clean(profile.get("carrier_name")) or "-", "-", "-"])
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

    buffer, doc, styles = make_doc("LossQ Executive Underwriting Report")
    story = []
    insured = clean(profile.get("business_name")) or "Selected Account"
    risk_level = clean(summary.get("renewal_risk_level") or summary.get("risk_level") or "Not Rated")
    renewal_score = summary.get("renewal_score")

    story.append(title("Executive Underwriting Report", styles))
    story.append(p("Boardroom-style renewal, claims, and underwriting intelligence summary.", styles))
    story.append(table(profile_rows(profile, policy_number or profile.get("policy_number")), widths=[1.6 * inch, 5.2 * inch], header=False))

    story.append(heading("Risk Gauge", styles))
    story.append(
        table(
            [
                ["Renewal Score", "Risk Level", "Total Claims", "Open Claims"],
                [f"{renewal_score}/100" if renewal_score is not None else "-", risk_level, metrics["total_claims"], metrics["open_claims"]],
                ["Total Paid", "Total Reserve", "Total Incurred", "Litigation Claims"],
                [dollars(metrics["total_paid"]), dollars(metrics["total_reserve"]), dollars(metrics["total_incurred"]), metrics["litigation_claims"]],
            ],
            widths=[1.7 * inch] * 4,
        )
    )

    story.append(heading("Executive Summary", styles))
    story.append(p(summary.get("renewal_summary") or summary.get("summary") or f"{insured} has {metrics['total_claims']} claim(s) and total incurred losses of {dollars(metrics['total_incurred'])}.", styles))

    story.append(heading("Premium Forecast", styles))
    story.append(
        table(
            [
                ["Current Premium", "Estimated Renewal", "Increase %", "Confidence"],
                [
                    dollars(forecast.get("current_premium")),
                    dollars(forecast.get("expected_renewal_premium")),
                    pct(forecast.get("expected_increase_percent")),
                    pct(forecast.get("confidence_score")),
                ],
            ],
            widths=[1.7 * inch] * 4,
        )
    )
    story.append(p(forecast.get("forecast_summary") or "No premium forecast summary available.", styles))

    story.append(heading("Carrier Appetite and Match", styles))
    story.append(
        table(
            [
                ["Appetite Score", "Appetite Level", "Recommended Carrier", "Match Score"],
                [
                    f"{appetite.get('carrier_appetite_score')}/100" if appetite.get("carrier_appetite_score") is not None else "-",
                    appetite.get("carrier_appetite_level") or "-",
                    carrier_match.get("recommended_carrier") or "-",
                    f"{carrier_match.get('recommended_score')}/100" if carrier_match.get("recommended_score") is not None else "-",
                ],
            ],
            widths=[1.7 * inch] * 4,
        )
    )
    story.append(p(carrier_match.get("carrier_match_summary") or appetite.get("placement_summary") or "No carrier match summary available.", styles))

    story.append(heading("Policy Schedule", styles))
    story.append(table(policy_schedule_table(profile, ctx["policy_numbers_used"]), widths=[1.5 * inch, 1.7 * inch, 1.5 * inch, 1.0 * inch, 1.0 * inch]))

    story.append(PageBreak())
    story.append(heading("Top Claims by Total Incurred", styles))
    story.append(table(top_claim_rows(claims), widths=[0.9 * inch, 1.0 * inch, 0.7 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 1.25 * inch, 1.0 * inch]))

    story.append(heading("Broker Action Plan", styles))
    actions = summary.get("recommended_actions") or summary.get("renewal_drivers") or []
    if not actions:
        actions = ["Prepare current loss runs, open claim updates, reserve commentary, litigation status, and corrective action details before market submission."]
    for index, action in enumerate(actions, start=1):
        story.append(p(f"{index}. {action}", styles))

    story.append(Spacer(1, 12))
    story.append(p("Disclaimer: This report is generated from available claim and account data inside LossQ. All figures should be reviewed against current carrier loss runs and confirmed before formal submission.", styles))

    doc.build(story)
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

    buffer, doc, styles = make_doc("LossQ Carrier Submission Packet")
    story = []
    insured = clean(profile.get("business_name")) or "Selected Account"
    risk_level = clean(summary.get("renewal_risk_level") or "Not Rated")
    renewal_score = summary.get("renewal_score")

    story.append(title("Carrier Submission Packet", styles))
    story.append(p("Underwriter-ready account narrative, loss analysis, claim explanations, and broker positioning.", styles))
    story.append(table(profile_rows(profile, policy_number or profile.get("policy_number")), widths=[1.6 * inch, 5.2 * inch], header=False))

    story.append(heading("Submission Snapshot", styles))
    story.append(
        table(
            [
                ["Renewal Score", "Risk Level", "Claim Count", "Open Claims"],
                [f"{renewal_score}/100" if renewal_score is not None else "-", risk_level, metrics["total_claims"], metrics["open_claims"]],
                ["Paid Losses", "Open Reserves", "Total Incurred", "Litigation Claims"],
                [dollars(metrics["total_paid"]), dollars(metrics["total_reserve"]), dollars(metrics["total_incurred"]), metrics["litigation_claims"]],
            ],
            widths=[1.7 * inch] * 4,
        )
    )

    story.append(heading("Broker Marketing Narrative", styles))
    story.append(p(summary.get("broker_recommendation") or summary.get("renewal_summary") or f"This submission presents {insured} for carrier underwriting review based on {metrics['total_claims']} account-specific claim(s).", styles))

    story.append(heading("Loss Summary", styles))
    story.append(
        table(
            [
                ["Metric", "Value"],
                ["Total Claims", metrics["total_claims"]],
                ["Open Claims", metrics["open_claims"]],
                ["Closed Claims", metrics["closed_claims"]],
                ["Litigation / Attorney Claims", metrics["litigation_claims"]],
                ["Flagged Claims", metrics["flagged_claims"]],
                ["Total Paid", dollars(metrics["total_paid"])],
                ["Total Reserve", dollars(metrics["total_reserve"])],
                ["Total Incurred", dollars(metrics["total_incurred"])],
            ],
            widths=[2.4 * inch, 4.3 * inch],
        )
    )

    story.append(heading("Policy Schedule", styles))
    story.append(table(policy_schedule_table(profile, ctx["policy_numbers_used"]), widths=[1.5 * inch, 1.7 * inch, 1.5 * inch, 1.0 * inch, 1.0 * inch]))

    story.append(PageBreak())
    story.append(heading("Claim Narratives and Underwriting Notes", styles))
    story.append(table(top_claim_rows(claims, max_rows=25), widths=[0.9 * inch, 1.0 * inch, 0.7 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 1.25 * inch, 1.0 * inch]))

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
        f"Please advise if additional loss-control, vehicle, payroll, operations, reserve, or litigation information is needed for quoting consideration."
    )
    story.append(p(email_text, styles))

    story.append(Spacer(1, 12))
    story.append(p("Disclaimer: This carrier packet is generated from available claim and account data inside LossQ. All figures should be reviewed against current carrier loss runs and confirmed before formal submission.", styles))

    doc.build(story)
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

    buffer, doc, styles = make_doc("LossQ Carrier Loss Run")
    story = []
    story.append(title("Carrier Loss Run", styles))
    story.append(p("Account-specific loss run export generated from LossQ claim data.", styles))
    story.append(table(profile_rows(profile, policy_number or profile.get("policy_number")), widths=[1.6 * inch, 5.2 * inch], header=False))
    story.append(heading("Loss Totals", styles))
    story.append(
        table(
            [
                ["Total Claims", "Open Claims", "Total Paid", "Total Reserve", "Total Incurred"],
                [metrics["total_claims"], metrics["open_claims"], dollars(metrics["total_paid"]), dollars(metrics["total_reserve"]), dollars(metrics["total_incurred"])],
            ],
            widths=[1.35 * inch] * 5,
        )
    )
    story.append(heading("Claims", styles))
    story.append(table(top_claim_rows(claims, max_rows=50), widths=[0.9 * inch, 1.0 * inch, 0.7 * inch, 0.8 * inch, 0.8 * inch, 0.8 * inch, 1.25 * inch, 1.0 * inch]))
    doc.build(story)
    return pdf_response(buffer, "lossq_carrier_loss_run.pdf")
