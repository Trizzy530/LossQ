from __future__ import annotations

import unittest

from app.services.source_evidence import build_loss_run_evidence, locate_source_value


class SourceEvidenceTests(unittest.TestCase):
    def test_locates_exact_value_with_page_and_excerpt(self):
        match = locate_source_value(
            ["Account: Acme Logistics\n", "Claim CLM-100 Total Incurred $12,500.00"],
            "CLM-100",
        )
        self.assertEqual(match["page"], 2)
        self.assertEqual(match["match"], "exact")
        self.assertIn("CLM-100", match["excerpt"])

    def test_locates_normalized_identifier(self):
        match = locate_source_value(["Policy number POL 100 22"], "POL-100-22")
        self.assertEqual(match["match"], "normalized")
        self.assertTrue(match["verified"])

    def test_builds_claim_evidence_and_coverage(self):
        evidence = build_loss_run_evidence(
            content=(b"Named Insured Acme Logistics\nPolicy POL-100\n"
                     b"Claim CLM-100 Paid 75.00 Reserve 25.00 Total 100.00 Closed"),
            filename="loss-run.txt",
            profile={"business_name": "Acme Logistics", "policy_number": "POL-100"},
            policies=[{"policy_number": "POL-100"}],
            claims=[{
                "claim_number": "CLM-100", "policy_number": "POL-100", "status": "Closed",
                "paid_amount": 75, "reserve_amount": 25, "total_incurred": 100,
            }],
        )
        self.assertEqual(evidence["page_count"], 1)
        self.assertIn("claim_number", evidence["claims"][0]["fields"])
        self.assertGreater(evidence["summary"]["coverage_percent"], 50)

    def test_missing_value_is_not_falsely_verified(self):
        self.assertIsNone(locate_source_value(["No matching identifier"], "CLM-999"))


if __name__ == "__main__":
    unittest.main()
