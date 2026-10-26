from __future__ import annotations

import os
import unittest

os.environ.setdefault("SECRET_KEY", "test-only-lossq-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_utils import get_current_user
from app.database import Base
from app.models.account_profile import AccountProfile
from app.models.claim import Claim
from app.models.organization import Organization
from app.models.underwriting_rule_set import UnderwritingRuleSet
from app.models.user import User
from app.routes import loss_intelligence


class LossIntelligenceRouteTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        cls.Session = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False)
        Base.metadata.create_all(bind=cls.engine)

        db = cls.Session()
        db.add(Organization(id=1, name="Test Brokerage"))
        db.add(
            AccountProfile(
                organization_id=1,
                business_name="Acme Logistics",
                policy_number="POL-200",
                current_premium="200000",
                validation="{}",
                policies="[]",
            )
        )
        db.add_all(
            [
                Claim(
                    organization_id=1,
                    claim_number="CLM-100",
                    policy_number="POL-100",
                    status="Closed",
                    paid_amount=25000,
                    reserve_amount=0,
                    total_incurred=25000,
                    is_deleted=False,
                ),
                Claim(
                    organization_id=1,
                    claim_number="CLM-100",
                    policy_number="POL-200",
                    status="Open",
                    paid_amount=30000,
                    reserve_amount=90000,
                    total_incurred=120000,
                    is_deleted=False,
                ),
                Claim(
                    organization_id=2,
                    claim_number="PRIVATE-OTHER-ORG",
                    policy_number="POL-200",
                    total_incurred=999999,
                    is_deleted=False,
                ),
            ]
        )
        db.commit()
        db.close()

        cls.app = FastAPI()
        cls.app.include_router(loss_intelligence.router)

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        cls.owner_identity = {
            "user_id": 10,
            "organization_id": 1,
            "role": "owner",
            "email": "owner@example.com",
        }
        cls.app.dependency_overrides[loss_intelligence.get_db] = override_db
        cls.app.dependency_overrides[get_current_user] = lambda: cls.owner_identity
        cls.original_audit = loss_intelligence.record_audit_event
        loss_intelligence.record_audit_event = lambda *args, **kwargs: None
        cls.client = TestClient(cls.app)

    @classmethod
    def tearDownClass(cls):
        loss_intelligence.record_audit_event = cls.original_audit
        cls.engine.dispose()

    def test_export_is_versioned_and_organization_scoped(self):
        response = self.client.get(
            "/loss-intelligence/export",
            params={"policy_number": "POL-200", "format": "json"},
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["schema_version"], "lossq.loss-intelligence.v1")
        self.assertEqual(len(data["claims"]), 1)
        self.assertEqual(data["claims"][0]["claim_number"], "CLM-100")

    def test_rule_update_is_versioned_and_evaluation_uses_it(self):
        payload = {
            "name": "Test appetite",
            "rules": [
                {
                    "id": "single-loss",
                    "label": "Single loss referral",
                    "metric": "max_single_claim",
                    "operator": "gte",
                    "threshold": 100000,
                    "severity": "critical",
                    "action": "Refer",
                    "enabled": True,
                }
            ],
        }
        saved = self.client.put("/loss-intelligence/rules", json=payload)
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["version"], 1)

        evaluated = self.client.get(
            "/loss-intelligence/evaluate", params={"policy_number": "POL-200"}
        )
        self.assertEqual(evaluated.status_code, 200)
        self.assertEqual(evaluated.json()["decision"], "refer")
        self.assertEqual(evaluated.json()["rule_set"]["name"], "Test appetite")

    def test_broker_cannot_change_organization_rules(self):
        self.app.dependency_overrides[get_current_user] = lambda: {
            **self.owner_identity,
            "role": "broker",
        }
        try:
            response = self.client.put(
                "/loss-intelligence/rules",
                json={"name": "Blocked", "rules": [{
                    "id": "blocked", "metric": "claim_count", "operator": "gte", "threshold": 1,
                }]},
            )
            self.assertEqual(response.status_code, 403)
        finally:
            self.app.dependency_overrides[get_current_user] = lambda: self.owner_identity

    def test_comparison_and_csv_export(self):
        compared = self.client.get(
            "/loss-intelligence/renewal-comparison",
            params={"current_policy_number": "POL-200", "prior_policy_number": "POL-100"},
        )
        self.assertEqual(compared.status_code, 200)
        self.assertEqual(compared.json()["direction"], "deteriorated")

        exported = self.client.get(
            "/loss-intelligence/export",
            params={"policy_number": "POL-200", "format": "csv"},
        )
        self.assertEqual(exported.status_code, 200)
        self.assertIn("text/csv", exported.headers["content-type"])
        self.assertIn("CLM-100", exported.text)
        self.assertNotIn("PRIVATE-OTHER-ORG", exported.text)


if __name__ == "__main__":
    unittest.main()
