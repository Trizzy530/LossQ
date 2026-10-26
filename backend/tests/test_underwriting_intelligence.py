from __future__ import annotations

import unittest

from app.services.underwriting_intelligence import (
    compare_renewal_claims,
    evaluate_underwriting_rules,
    validate_rules,
)


class UnderwritingIntelligenceTests(unittest.TestCase):
    def test_critical_rule_refers_account(self):
        result = evaluate_underwriting_rules(
            [{"claim_number": "C-1", "policy_number": "P-1", "total_incurred": 150000}],
            premium=200000,
        )
        self.assertEqual(result["decision"], "refer")
        self.assertTrue(any(rule["id"] == "large-loss" for rule in result["triggered_rules"]))

    def test_custom_rule_is_deterministic(self):
        rules = [{
            "id": "frequency", "metric": "claim_count", "operator": "gte",
            "threshold": 2, "severity": "warning", "action": "Review frequency",
        }]
        result = evaluate_underwriting_rules([{}, {}], rules=rules)
        self.assertEqual(result["decision"], "review")
        self.assertEqual(result["triggered_rules"][0]["actual"], 2)

    def test_invalid_metric_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsupported metric"):
            validate_rules([{"id": "bad", "metric": "python_code", "operator": "eq", "threshold": 1}])

    def test_rule_count_is_bounded(self):
        rules = [
            {"id": f"rule-{index}", "metric": "claim_count", "operator": "gte", "threshold": index}
            for index in range(101)
        ]
        with self.assertRaisesRegex(ValueError, "more than 100"):
            validate_rules(rules)

    def test_renewal_comparison_detects_new_and_changed_claims(self):
        prior = [{
            "claim_number": "C-1", "policy_number": "P-OLD", "status": "Open",
            "paid_amount": 10, "reserve_amount": 90, "total_incurred": 100,
        }]
        current = [
            {
                "claim_number": "C-1", "policy_number": "P-OLD", "status": "Closed",
                "paid_amount": 100, "reserve_amount": 0, "total_incurred": 100,
            },
            {"claim_number": "C-2", "policy_number": "P-NEW", "total_incurred": 200},
        ]
        result = compare_renewal_claims(current, prior)
        self.assertEqual(result["direction"], "deteriorated")
        self.assertEqual(len(result["new_claims"]), 1)
        self.assertIn("status", result["changed_claims"][0]["changes"])


if __name__ == "__main__":
    unittest.main()
