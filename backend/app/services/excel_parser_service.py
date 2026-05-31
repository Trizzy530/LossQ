import pandas as pd


def clean_money(value):
    if pd.isna(value):
        return 0.0

    cleaned = (
        str(value)
        .replace("$", "")
        .replace(",", "")
        .replace("(", "-")
        .replace(")", "")
        .strip()
    )

    try:
        return float(cleaned)
    except Exception:
        return 0.0


def clean_text(value):
    if value is None or pd.isna(value):
        return ""
    return str(value).strip()


def get(row, names, default=None):
    for name in names:
        if name in row and pd.notna(row[name]):
            return row[name]
    return default


def parse_claims_from_excel(file_path):
    if file_path.lower().endswith(".csv"):
        df = pd.read_csv(file_path)
    else:
        df = pd.read_excel(file_path)

    df.columns = [str(c).strip() for c in df.columns]

    claims = []

    for _, row in df.iterrows():
        row_dict = row.to_dict()

        claim_number = get(
            row_dict,
            ["Claim Number", "Claim #", "Claim No", "Claim", "claim_number"],
        )

        if not claim_number:
            continue

        paid = clean_money(get(row_dict, ["Paid", "Paid Amount", "Loss Paid"], 0))
        reserve = clean_money(
            get(row_dict, ["Reserve", "Outstanding Reserve", "Loss Reserve"], 0)
        )
        total = clean_money(
            get(row_dict, ["Total Incurred", "Incurred", "Total Loss"], paid + reserve)
        )

        if total == 0:
            total = paid + reserve

        description = clean_text(
            get(row_dict, ["Description", "Loss Description", "Claim Description"], "")
        )

        row_text = " ".join(str(v) for v in row_dict.values())
        lower = row_text.lower()

        litigation = any(
            word in lower
            for word in ["attorney", "litigation", "lawsuit", "counsel", "suit filed"]
        )

        line = clean_text(
            get(row_dict, ["Line of Business", "LOB", "Coverage"], "Unknown")
        )

        flag = None
        if total >= 100000:
            flag = "High severity claim"
        if litigation:
            flag = "Litigation exposure" if not flag else flag + " | Litigation exposure"

        claims.append({
            "claim_number": str(claim_number),
            "policy_id": 1,
            "business_name": clean_text(
                get(row_dict, ["Business Name", "Insured Name", "Named Insured", "Account Name"], "")
            ),
            "carrier_name": clean_text(
                get(row_dict, ["Carrier", "Carrier Name", "Insurance Carrier"], "")
            ),
            "agency_name": clean_text(
                get(row_dict, ["Agency", "Agency Name", "Broker", "Broker Name"], "")
            ),
            "policy_number": clean_text(
                get(row_dict, ["Policy Number", "Policy #", "Policy No", "Policy"], "")
            ),
            "effective_date": clean_text(
                get(row_dict, ["Effective Date", "Policy Effective Date", "Eff Date"], "")
            ),
            "expiration_date": clean_text(
                get(row_dict, ["Expiration Date", "Policy Expiration Date", "Exp Date"], "")
            ),
            "line_of_business": line,
            "claim_type": line,
            "cause_of_loss": clean_text(
                get(row_dict, ["Cause of Loss", "Cause", "Loss Cause"], "Needs Review")
            ),
            "claimant_type": clean_text(
                get(row_dict, ["Claimant Type"], "Needs Review")
            ),
            "date_of_loss": clean_text(
                get(row_dict, ["Date of Loss", "Loss Date", "DOL"], "Needs Review")
            ),
            "date_reported": clean_text(
                get(row_dict, ["Date Reported", "Reported Date", "Report Date"], "")
            ),
            "date_closed": clean_text(
                get(row_dict, ["Date Closed", "Closed Date", "Closure Date"], "")
            ),
            "status": clean_text(
                get(row_dict, ["Status", "Claim Status"], "Open")
            ).title(),
            "description": description,
            "paid_amount": paid,
            "reserve_amount": reserve,
            "total_incurred": total,
            "litigation": litigation,
            "litigation_status": "Litigation detected" if litigation else "None",
            "attorney_assigned": litigation,
            "suit_filed": litigation,
            "venue_state": clean_text(get(row_dict, ["Venue State", "State"], "Needs Review")),
            "injury_type": clean_text(get(row_dict, ["Injury Type"], "Needs Review")),
            "flag": flag,
        })

    return claims