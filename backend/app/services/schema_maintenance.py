from __future__ import annotations

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine


def ensure_claim_soft_delete_columns(engine: Engine) -> None:
    """Bring legacy claim tables forward before ORM queries select these columns."""
    inspector = inspect(engine)
    if "claims" not in inspector.get_table_names():
        return
    existing = {column["name"] for column in inspector.get_columns("claims")}
    statements = []
    if "is_deleted" not in existing:
        statements.append("ALTER TABLE claims ADD COLUMN is_deleted BOOLEAN DEFAULT FALSE")
    if "deleted_at" not in existing:
        statements.append("ALTER TABLE claims ADD COLUMN deleted_at TIMESTAMP")
    if not statements:
        return
    with engine.begin() as connection:
        for statement in statements:
            connection.execute(text(statement))
