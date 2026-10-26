from __future__ import annotations

import unittest

from app.services.review_confirmation import prepare_review_confirmation


class PrepareReviewConfirmationTests(unittest.TestCase):
    def payload(self):
        return {
            "profile": {"policy_number": "POL-100", "business_name": "Acme"},
            "policies": [{"policy_number": "POL-100"}],
            "claims": [{"claim_number": "CLM-100", "policy_number": "POL-100", "paid_amount": 75, "reserve_amount": 25, "total_incurred": 100}],
        }

    def test_valid_review_is_normalized(self):
        prepared = prepare_review_confirmation(self.payload())
        self.assertEqual(prepared.policy_numbers, ("POL-100",))
        self.assertEqual(prepared.claims[0]["claim_number"], "CLM-100")
        self.assertEqual(prepared.warnings, ())

    def test_duplicate_claim_is_rejected_before_database_mutation(self):
        payload = self.payload()
        payload["claims"].append(dict(payload["claims"][0]))
        with self.assertRaisesRegex(ValueError, "Duplicate reviewed claim"):
            prepare_review_confirmation(payload)

    def test_missing_policy_is_rejected(self):
        payload = self.payload()
        payload["profile"]["policy_number"] = ""
        payload["policies"] = []
        payload["claims"][0]["policy_number"] = ""
        with self.assertRaisesRegex(ValueError, "valid policy number"):
            prepare_review_confirmation(payload)

    def test_empty_history_requires_explicit_no_loss_confirmation(self):
        payload = self.payload()
        payload["claims"] = []
        with self.assertRaisesRegex(ValueError, "Confirm this is a no-loss account"):
            prepare_review_confirmation(payload)
        payload["confirm_no_loss"] = True
        self.assertEqual(prepare_review_confirmation(payload).claims, [])

    def test_manual_confirmation_preserves_financial_warning(self):
        payload = self.payload()
        payload["claims"][0]["total_incurred"] = 150
        prepared = prepare_review_confirmation(payload)
        self.assertEqual(len(prepared.warnings), 1)
        self.assertIn("not equal to incurred", prepared.warnings[0])


if __name__ == "__main__":
    unittest.main()
