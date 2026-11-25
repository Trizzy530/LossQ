import unittest
from app.services.reconciled_pdf import parse_reconciled_layout, StructuredPDFError


def fixture():
    def row(values, widths):
        return "".join(str(v).ljust(w) for v, w in zip(values, widths)).rstrip()
    a = [36, 24, 35, 25]
    p = [22, 35, 15, 15, 20, 20, 15]
    f = [22, 22, 20, 15, 12, 18, 18, 18]
    d = [22, 30, 8, 15, 15, 20, 15, 55]
    return "\n".join([
        "Commercial insurance loss experience",
        "Example Mutual Insurance Company | Valuation date: 10/31/2026 | USD",
        row(["Named insured", "Account number", "Producing agency", "Domicile"], a),
        row(["Example Mechanical LLC", "US-EXM-84720", "Example Trade Risk Partners", "NC, United States"], a),
        "Policy schedule and exposure basis",
        row(["Policy number", "Coverage", "Effective", "Expiration", "Annual premium", "Exposure basis", "Exposure"], p),
        row(["GL-847201-26", "Commercial General Liability", "12/01/2025", "12/01/2026", "$42,000", "Annual revenue", "3,850,000"], p),
        row(["CA-847202-26", "Commercial Auto", "12/01/2025", "12/01/2026", "$68,500", "Vehicles", "18"], p),
        row(["WC-847203-26", "Workers Compensation", "12/01/2025", "12/01/2026", "$51,000", "Payroll", "1,920,000"], p),
        row(["IM-847204-26", "Inland Marine", "12/01/2025", "12/01/2026", "$18,000", "Equipment TIV", "1,100,000"], p),
        row(["UMB-847205-26", "Umbrella", "12/01/2025", "12/01/2026", "$12,500", "Limit", "5,000,000"], p),
        "Claim financial detail",
        row(["Claim number", "Policy number", "LOB", "Loss date", "Status", "Paid", "Reserve", "Total incurred"], f),
        row(["TR-260101", "GL-847201-26", "GL", "01/12/2026", "Closed", "$12,500", "$0", "$12,500"], f),
        row(["TR-260114", "CA-847202-26", "Auto", "02/08/2026", "Open", "$32,000", "$48,000", "$80,000"], f),
        row(["TR-260125", "WC-847203-26", "WC", "03/02/2026", "Closed", "$8,700", "$0", "$8,700"], f),
        row(["TR-260149", "IM-847204-26", "Inland Marine", "05/19/2026", "Closed", "$19,600", "$0", "$19,600"], f),
        row(["TR-260173", "WC-847203-26", "WC", "08/14/2026", "Open", "$15,500", "$24,500", "$40,000"], f),
        "TOTAL     $88,300     $72,500     $160,800",
        "Claims administration and descriptions",
        row(["Claim number", "Claimant", "Jur.", "Reported", "Closed", "Adjuster", "Litigation", "Description"], d),
        row(["TR-260101", "Cedar Court HOA", "NC", "01/13/2026", "03/18/2026", "A. Mercer", "No", "Water damage."], d),
        row(["TR-260114", "Westfield Supply LLC", "SC", "02/08/2026", "", "B. Ellis", "Yes", "Service van collision; counsel retained."], d),
        row(["TR-260125", "Jordan Blake", "NC", "03/03/2026", "06/12/2026", "C. Lane", "No", "Wrist sprain."], d),
        row(["TR-260149", "Example Mechanical LLC", "NC", "05/20/2026", "07/09/2026", "D. Reid", "No", "Tools stolen."], d),
        row(["TR-260173", "Morgan Hale", "NC", "08/15/2026", "", "C. Lane", "No", "Back injury."], d),
        "Operations: HVAC and plumbing.",
    ])


class ReconciledPDFTests(unittest.TestCase):
    def test_split_tables(self):
        claims, profile = parse_reconciled_layout(fixture())
        self.assertEqual(profile["business_name"], "Example Mechanical LLC")
        self.assertEqual(profile["carrier_name"], "Example Mutual Insurance Company")
        self.assertEqual(profile["agency_name"], "Example Trade Risk Partners")
        self.assertEqual(profile["account_number"], "US-EXM-84720")
        self.assertEqual(profile["state"], "NC")
        self.assertEqual(len(claims), 5)
        self.assertEqual(sum(c["status"] == "Open" for c in claims), 2)
        self.assertEqual(sum(c["paid_amount"] for c in claims), 88300)
        self.assertEqual(sum(c["reserve_amount"] for c in claims), 72500)
        self.assertEqual(sum(c["total_incurred"] for c in claims), 160800)
        self.assertEqual([p["claim_count"] for p in profile["policies"]], [1, 1, 2, 1, 0])
        self.assertEqual([p["total_incurred"] for p in profile["policies"]], [12500, 80000, 48700, 19600, 0])
        self.assertEqual(claims[1]["policy_number"], "CA-847202-26")
        self.assertEqual(claims[1]["jurisdiction_state"], "SC")
        self.assertTrue(claims[1]["litigation"])
        self.assertIsNone(claims[1]["date_closed"])
        self.assertEqual(claims[-1]["claimant"], "Morgan Hale")
        self.assertEqual(profile["revenue"], "3850000")
        self.assertEqual(profile["vehicle_count"], "18")

    def test_mismatched_total_rejected(self):
        with self.assertRaises(StructuredPDFError):
            parse_reconciled_layout(fixture().replace("$160,800", "$120,800"))

    def test_unknown_layout_unchanged(self):
        self.assertIsNone(parse_reconciled_layout("Other carrier layout\nClaim number: A12345"))
        self.assertIsNone(parse_reconciled_layout(fixture().replace("USD", "CAD")))

    def test_duplicate_financial_row_rejected(self):
        text = fixture()
        line = next(x for x in text.splitlines() if x.startswith("TR-260101"))
        with self.assertRaises(StructuredPDFError):
            parse_reconciled_layout(text.replace(line, line + "\n" + line, 1))
