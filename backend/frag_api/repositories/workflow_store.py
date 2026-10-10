"""Separate safe receipts on the existing database owner; no draft storage/replay."""
from datetime import datetime, timezone

from frag_api.errors import RuntimeConflictError, RuntimeNotFoundError
from frag_api.schemas.workflow import WorkflowReceipt


def utc_now():
    return datetime.now(timezone.utc).isoformat()


class WorkflowStore:
    def __init__(self, owner):
        self.owner = owner
        with owner.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS recommendation_receipts (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            for key, body in db.execute("SELECT id,record FROM recommendation_receipts").fetchall():
                receipt = WorkflowReceipt.model_validate_json(body)
                if receipt.status == "active":
                    recovered = WorkflowReceipt.model_validate({**receipt.model_dump(by_alias=True),
                        "revision": receipt.revision + 1, "updatedAt": utc_now(), "stage": "finished",
                        "status": "interrupted", "reasonCode": "INTERRUPTED_UNKNOWN"})
                    db.execute("UPDATE recommendation_receipts SET record=? WHERE id=?", (recovered.model_dump_json(by_alias=True), key))

    def save(self, receipt, *, expected_revision=0, revoke_unreleased=False):
        # Revalidate even a model_copy/constructed instance. Unknown fields never enter storage.
        receipt = WorkflowReceipt.model_validate(receipt.model_dump(by_alias=True))
        with self.owner.connection() as db:
            row = db.execute("SELECT record FROM recommendation_receipts WHERE id=?", (receipt.id,)).fetchone()
            old = WorkflowReceipt.model_validate_json(row[0]) if row else None
            if (old.revision if old else 0) != expected_revision or receipt.revision != expected_revision + 1:
                raise RuntimeConflictError()
            if old and old.status != "active" and not (revoke_unreleased and old.status == "checked" and receipt.status == "refused"):
                raise RuntimeConflictError()
            db.execute("INSERT INTO recommendation_receipts VALUES(?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record",
                (receipt.id, receipt.model_dump_json(by_alias=True)))
        return receipt

    def get(self, key):
        with self.owner.connection() as db:
            row = db.execute("SELECT record FROM recommendation_receipts WHERE id=?", (key,)).fetchone()
        if row is None:
            raise RuntimeNotFoundError()
        return WorkflowReceipt.model_validate_json(row[0])

    def receipts(self):
        with self.owner.connection() as db:
            return [WorkflowReceipt.model_validate_json(row[0]) for row in db.execute(
                "SELECT record FROM recommendation_receipts ORDER BY rowid DESC LIMIT 200")]
