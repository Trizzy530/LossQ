from __future__ import annotations

import unittest

from sqlalchemy import create_engine, inspect, text

from app.services.schema_maintenance import ensure_claim_soft_delete_columns


class SchemaMaintenanceTests(unittest.TestCase):
    def test_legacy_claim_table_receives_soft_delete_columns(self):
        engine = create_engine("sqlite://")
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE claims (id INTEGER PRIMARY KEY, claim_number VARCHAR)"))
        ensure_claim_soft_delete_columns(engine)
        columns = {column["name"] for column in inspect(engine).get_columns("claims")}
        self.assertIn("is_deleted", columns)
        self.assertIn("deleted_at", columns)


if __name__ == "__main__":
    unittest.main()
