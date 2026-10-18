"""Owned tool state; historical tables are left untouched."""
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from frag_api.errors import RuntimeConflictError, RuntimeNotFoundError
from frag_api.schemas.native import SourceProfile, ToolRun


class ToolStore:
    def __init__(self, path: Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lease = self.owner_lease()
        self._lease.__enter__()
        with self.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS source_profiles (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, record TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS tool_runs (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            # No external requests are replayed. These are only unfinished local deliveries.
            for key, body in db.execute("SELECT id,record FROM tool_runs").fetchall():
                run = ToolRun.model_validate_json(body)
                if run.status == "prepared":
                    db.execute("UPDATE tool_runs SET record=? WHERE id=?", (run.model_copy(update={"status": "interrupted"}).model_dump_json(by_alias=True), key))

    def close(self):
        self._lease.__exit__(None, None, None)

    @contextmanager
    def owner_lease(self):
        """Only one app lifetime may classify unfinished calls in this database."""
        handle = self.path.with_suffix(self.path.suffix + ".owner.lock").open("a+b")
        locked = False
        try:
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            locked = True
            yield
        finally:
            if locked:
                handle.seek(0)
                if os.name == "nt":
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
            handle.close()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=10)
        try:
            db.execute("PRAGMA foreign_keys=ON")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def profiles(self):
        with self.connection() as db:
            return [SourceProfile.model_validate_json(row[0]) for row in db.execute("SELECT record FROM source_profiles ORDER BY id")]

    def profile(self, key):
        with self.connection() as db:
            row = db.execute("SELECT record FROM source_profiles WHERE id=?", (key,)).fetchone()
        if row is None:
            raise RuntimeNotFoundError()
        return SourceProfile.model_validate_json(row[0])

    def save_profile(self, value):
        with self.connection() as db:
            old = db.execute("SELECT revision FROM source_profiles WHERE id=?", (value.id,)).fetchone()
            if value.revision != (old[0] if old else 0):
                raise RuntimeConflictError()
            value = value.model_copy(update={"revision": value.revision + 1})
            # Clearing the feature retains the pre-plan source contract for a reviewed downgrade.
            record = value.model_dump_json(by_alias=True, exclude={"confirmed_plans"} if not value.confirmed_plans else set())
            db.execute("INSERT INTO source_profiles VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,record=excluded.record", (value.id, value.revision, record))
        return value

    def save(self, value, *, validate=None):
        with self.connection() as db:
            if validate:
                validate(db)
            old = db.execute("SELECT record FROM tool_runs WHERE id=?", (value.id,)).fetchone()
            if old and ToolRun.model_validate_json(old[0]).status != "prepared":
                raise RuntimeConflictError()
            db.execute("INSERT INTO tool_runs VALUES(?,?) ON CONFLICT(id) DO UPDATE SET record=excluded.record", (value.id, value.model_dump_json(by_alias=True)))
        return value

    def get(self, key):
        with self.connection() as db:
            row = db.execute("SELECT record FROM tool_runs WHERE id=?", (key,)).fetchone()
        if row is None:
            raise RuntimeNotFoundError()
        return ToolRun.model_validate_json(row[0])

    def runs(self):
        with self.connection() as db:
            return [ToolRun.model_validate_json(row[0]) for row in db.execute("SELECT record FROM tool_runs ORDER BY rowid DESC LIMIT 200")]

