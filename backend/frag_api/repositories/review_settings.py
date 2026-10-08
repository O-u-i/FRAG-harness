"""Small CAS records; shared preferences never share a runtime owner lease."""
import json
import sqlite3
from pathlib import Path
from frag_api.errors import RuntimeConflictError


class ReviewSettingsRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("CREATE TABLE IF NOT EXISTS review_settings (scope_key TEXT PRIMARY KEY, revision INTEGER NOT NULL, record TEXT NOT NULL)")

    def get(self, key, default):
        with sqlite3.connect(self.path, timeout=10) as db:
            row = db.execute("SELECT revision, record FROM review_settings WHERE scope_key=?", (key,)).fetchone()
        return {"revision": row[0], "settings": json.loads(row[1])} if row else {"revision": 0, "settings": default}

    def put(self, key, revision, value):
        with sqlite3.connect(self.path, timeout=10) as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT revision FROM review_settings WHERE scope_key=?", (key,)).fetchone()
            if (row[0] if row else 0) != revision:
                raise RuntimeConflictError()
            db.execute("INSERT INTO review_settings VALUES (?,?,?) ON CONFLICT(scope_key) DO UPDATE SET revision=excluded.revision,record=excluded.record",
                       (key, revision + 1, json.dumps(value, ensure_ascii=False)))
        return {"revision": revision + 1, "settings": value}

