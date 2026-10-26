from __future__ import annotations

import unittest

from app.services.loss_intelligence_guard import decide_claim_replacement


def claim(number: str, *, paid: float = 50, reserve: float = 50, incurred: float = 100):
    return {
        "claim_number": number,
        "policy_number": "POL-100",
        "paid_amount": paid,
        "reserve_amount": reserve,
        "total_incurred": incurred,
    }


class ClaimReplacementDecisionTests(unittest.TestCase):
    def test_complete_trusted_extraction_can_replace(self):
        decision = decide_claim_replacement(
            existing_claim_count=1,
            incoming_claims=[claim("CLM-1")],
            extraction_quality={"status": "passed", "critical_issues": []},
            reported_total_claims=1,
        )

        self.assertTrue(decision.safe_to_replace)
        self.assertEqual(decision.mode, "replace")
        self.assertEqual(decision.reasons, ())

    def test_review_required_extraction_never_replaces(self):
        decision = decide_claim_replacement(
            existing_claim_count=1,
            incoming_claims=[claim("CLM-1")],
            extraction_quality={"status": "review_required"},
        )

        self.assertFalse(decision.safe_to_replace)
        self.assertEqual(decision.mode, "review_only")

    def test_smaller_incoming_history_does_not_destroy_existing_claims(self):
        decision = decide_claim_replacement(
            existing_claim_count=3,
            incoming_claims=[claim("CLM-1"), claim("CLM-2")],
            extraction_quality={"status": "passed", "critical_issues": []},
        )

        self.assertFalse(decision.safe_to_replace)
        self.assertIn("fewer claims", " ".join(decision.reasons))

    def test_reported_claim_count_mismatch_requires_review(self):
        decision = decide_claim_replacement(
            existing_claim_count=0,
            incoming_claims=[claim("CLM-1")],
            extraction_quality={"status": "passed", "critical_issues": []},
            reported_total_claims=2,
        )

        self.assertFalse(decision.safe_to_replace)
        self.assertIn("reported total", " ".join(decision.reasons))

    def test_unreconciled_money_requires_review(self):
        decision = decide_claim_replacement(
            existing_claim_count=0,
            incoming_claims=[claim("CLM-1", paid=50, reserve=10, incurred=100)],
            extraction_quality={"status": "passed", "critical_issues": []},
        )

        self.assertFalse(decision.safe_to_replace)
        self.assertIn("do not reconcile", " ".join(decision.reasons))


if __name__ == "__main__":
    unittest.main()
