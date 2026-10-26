from __future__ import annotations

import os
import unittest
from datetime import datetime, timedelta, timezone

os.environ.setdefault("SECRET_KEY", "test-only-lossq-secret")

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.auth_utils import get_current_user
from app.database import Base
from app.models.loss_run_request import LossRunRequest, LossRunRequestEvent
from app.models.organization import Organization
from app.routes import loss_run_requests
from app.services.loss_run_requests import needs_attention, validate_transition


class LossRunRequestServiceTests(unittest.TestCase):
    def test_transition_rules_reject_skipping_receipt(self):
        with self.assertRaisesRegex(ValueError, "Cannot move"):
            validate_transition("requested", "completed")

    def test_overdue_requested_item_needs_attention(self):
        now = datetime.now(timezone.utc)
        self.assertTrue(needs_attention("requested", now - timedelta(minutes=1), now=now))
        self.assertFalse(needs_attention("requested", now + timedelta(days=1), now=now))


class LossRunRequestRouteTests(unittest.TestCase):
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
        db.add_all([Organization(id=1, name="Test Brokerage"), Organization(id=2, name="Other Brokerage")])
        db.add(LossRunRequest(organization_id=2, insured_name="Private Account", carrier_name="Other Carrier"))
        db.commit()
        db.close()

        cls.app = FastAPI()
        cls.app.include_router(loss_run_requests.router)

        def override_db():
            db = cls.Session()
            try:
                yield db
            finally:
                db.close()

        cls.identity = {"user_id": 10, "organization_id": 1, "role": "owner", "email": "owner@example.com"}
        cls.app.dependency_overrides[loss_run_requests.get_db] = override_db
        cls.app.dependency_overrides[get_current_user] = lambda: cls.identity
        cls.original_audit = loss_run_requests.record_audit_event
        loss_run_requests.record_audit_event = lambda *args, **kwargs: None
        cls.client = TestClient(cls.app)

    def setUp(self):
        db = self.Session()
        db.query(LossRunRequestEvent).filter(LossRunRequestEvent.organization_id == 1).delete()
        db.query(LossRunRequest).filter(LossRunRequest.organization_id == 1).delete()
        db.commit()
        db.close()

    @classmethod
    def tearDownClass(cls):
        loss_run_requests.record_audit_event = cls.original_audit
        cls.engine.dispose()

    def test_request_pipeline_is_organization_scoped_and_audited(self):
        created = self.client.post("/loss-run-requests", json={
            "insured_name": "Acme Logistics",
            "carrier_name": "Test Mutual",
            "contact_email": "lossruns@test.example",
            "authorization_received": True,
            "status": "requested",
            "next_follow_up_at": (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat(),
        })
        self.assertEqual(created.status_code, 201)
        request_id = created.json()["id"]

        listed = self.client.get("/loss-run-requests")
        self.assertEqual(listed.status_code, 200)
        self.assertEqual(len(listed.json()["items"]), 1)
        self.assertEqual(listed.json()["items"][0]["insured_name"], "Acme Logistics")
        self.assertTrue(listed.json()["items"][0]["needs_attention"])

        received = self.client.patch(f"/loss-run-requests/{request_id}", json={"status": "received"})
        self.assertEqual(received.status_code, 200)
        self.assertIsNotNone(received.json()["received_at"])

        events = self.client.get(f"/loss-run-requests/{request_id}/events")
        self.assertEqual(events.status_code, 200)
        self.assertEqual([event["event_type"] for event in events.json()["items"]], ["status_changed", "created"])

    def test_authorization_and_transition_guards(self):
        blocked = self.client.post("/loss-run-requests", json={
            "insured_name": "No Auth LLC",
            "carrier_name": "Test Mutual",
            "authorization_received": False,
            "status": "requested",
        })
        self.assertEqual(blocked.status_code, 422)

        created = self.client.post("/loss-run-requests", json={
            "insured_name": "Draft LLC",
            "carrier_name": "Test Mutual",
            "status": "draft",
        })
        request_id = created.json()["id"]
        skipped = self.client.patch(f"/loss-run-requests/{request_id}", json={"status": "completed"})
        self.assertEqual(skipped.status_code, 422)


if __name__ == "__main__":
    unittest.main()
