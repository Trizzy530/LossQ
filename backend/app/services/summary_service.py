def generate_underwriting_summary(claims):
    total_claims = len(claims)

    if total_claims == 0:
        return {
            "summary": "No claims were found.",
            "risk_level": "Low",
            "risk_score": 0,
            "recommendation": "No loss activity identified."
        }

    open_claims = [c for c in claims if str(c.status).lower() == "open"]
    closed_claims = [c for c in claims if str(c.status).lower() == "closed"]
    gl_claims = [c for c in claims if c.line_of_business == "General Liability"]
    auto_claims = [c for c in claims if c.line_of_business == "Commercial Auto"]
    litigation_claims = [c for c in claims if c.litigation]
    flagged_claims = [c for c in claims if c.flag]

    total_paid = sum(float(c.paid_amount or 0) for c in claims)
    total_reserve = sum(float(c.reserve_amount or 0) for c in claims)
    total_incurred = sum(float(c.total_incurred or 0) for c in claims)

    risk_score = 0
    risk_score += len(open_claims) * 10
    risk_score += len(litigation_claims) * 20
    risk_score += len(flagged_claims) * 10

    if total_incurred >= 100000:
        risk_score += 30
    elif total_incurred >= 50000:
        risk_score += 20
    elif total_incurred >= 25000:
        risk_score += 10

    if risk_score >= 70:
        risk_level = "High"
    elif risk_score >= 35:
        risk_level = "Moderate"
    else:
        risk_level = "Low"

    summary = (
        f"{total_claims} claim(s) identified. "
        f"{len(open_claims)} open and {len(closed_claims)} closed. "
        f"Total paid is ${total_paid:,.2f}, reserves are ${total_reserve:,.2f}, "
        f"and total incurred is ${total_incurred:,.2f}. "
        f"{len(gl_claims)} General Liability claim(s), "
        f"{len(auto_claims)} Commercial Auto claim(s), "
        f"and {len(litigation_claims)} litigation-related claim(s) were detected."
    )

    concerns = []

    if open_claims:
        concerns.append("Open claims remain active and may affect underwriting.")
    if total_reserve > 0:
        concerns.append("Outstanding reserves may create pricing pressure.")
    if litigation_claims:
        concerns.append("Litigation indicators were detected and should be reviewed.")
    if flagged_claims:
        concerns.append("Flagged claim issues require manual review.")
    if not concerns:
        concerns.append("No major claim concerns detected from the uploaded loss data.")

    return {
        "summary": summary,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "recommendation": " ".join(concerns)
    }