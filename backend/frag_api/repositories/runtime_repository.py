"""Atomic application-owned run records, independent from the rebuildable RAG index."""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Callable

from frag_api.errors import RuntimeNotFoundError
from frag_api.schemas.runtime import RunRecord, RunReport, SessionRecord


class RuntimeRepository:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1):
                raise ValueError("Unsupported runtime database schema.")
            db.execute("CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, record TEXT NOT NULL)")
            db.execute("CREATE TABLE IF NOT EXISTS runs (id TEXT PRIMARY KEY, session_id TEXT NOT NULL REFERENCES sessions(id), record TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS runs_session ON runs(session_id)")
            db.execute("PRAGMA user_version=1")

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
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA synchronous=FULL")
            db.execute("BEGIN IMMEDIATE")
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def create_session(self, session: SessionRecord) -> SessionRecord:
        with self.connection() as db:
            db.execute("INSERT INTO sessions VALUES (?,?)", (session.id, session.model_dump_json(by_alias=True)))
        return session

    def session(self, session_id: str) -> SessionRecord:
        with self.connection() as db:
            row = db.execute("SELECT record FROM sessions WHERE id=?", (session_id,)).fetchone()
        if row is None:
            raise RuntimeNotFoundError()
        return SessionRecord.model_validate_json(row[0])

    def sessions(self) -> list[SessionRecord]:
        with self.connection() as db:
            rows = db.execute("SELECT record FROM sessions ORDER BY rowid DESC LIMIT 200").fetchall()
        return [SessionRecord.model_validate_json(row[0]) for row in rows]

    def create(self, report: RunReport) -> RunReport:
        with self.connection() as db:
            db.execute("INSERT INTO runs VALUES (?,?,?)", (report.run.id, report.run.session_id, report.model_dump_json(by_alias=True)))
        return report

    @staticmethod
    def _read(db, run_id: str) -> RunReport:
        row = db.execute("SELECT record FROM runs WHERE id=?", (run_id,)).fetchone()
        if row is None:
            raise RuntimeNotFoundError()
        return RunReport.model_validate_json(row[0])

    def get(self, run_id: str) -> RunReport:
        with self.connection() as db:
            return self._read(db, run_id)

    def runs(self, session_id: str | None = None) -> list[RunRecord]:
        with self.connection() as db:
            sql = "SELECT record FROM runs"
            args = ()
            if session_id:
                sql += " WHERE session_id=?"
                args = (session_id,)
            rows = db.execute(sql + " ORDER BY rowid DESC LIMIT 200", args).fetchall()
        return [RunReport.model_validate_json(row[0]).run for row in rows]

    def incomplete_returns(self) -> list[RunReport]:
        with self.connection() as db:
            rows = db.execute("SELECT record FROM runs").fetchall()
        return [report for row in rows if (report := RunReport.model_validate_json(row[0])).run.status != "outcome_unknown"
                and any(c.status == "completed" and c.structural_validation == "UNDETERMINED" for c in report.requests)]

    def update(self, run_id: str, mutate: Callable[[RunReport], None]) -> RunReport:
        # The stage claim and append are one transaction, including across owner instances.
        with self.connection() as db:
            report = self._read(db, run_id)
            mutate(report)
            report.run.version += 1
            validated = RunReport.model_validate(report.model_dump(by_alias=True))
            db.execute("UPDATE runs SET record=? WHERE id=?", (validated.model_dump_json(by_alias=True), run_id))
        return validated

    def recover_dispatches(self, now: str) -> None:
        with self.connection() as db:
            for run_id, raw in db.execute("SELECT id,record FROM runs").fetchall():
                report = RunReport.model_validate_json(raw)
                pending = [item for item in report.requests if item.status == "dispatching"]
                pending_tools = [item for item in report.tool_calls if item.status == "dispatching"]
                if not pending and not pending_tools:
                    continue
                for call in pending:
                    call.status, call.error_code, call.finished_at = "outcome_unknown", "INTERRUPTED_CALL", now
                    call.structural_validation = "ERROR"
                for tool in pending_tools:
                    tool.status, tool.error_code, tool.finished_at = "outcome_unknown", "INTERRUPTED_TOOL", now
                report.run.status, report.run.updated_at = "outcome_unknown", now
                report.run.active_call_id = None
                report.run.version += 1
                report.structural_validation = "ERROR"
                if report.research:
                    report.research.status = "outcome_unknown"
                    for turn in report.research.turns:
                        if turn.status in ("model_pending", "tools_pending"):
                            turn.status, turn.error_code = "outcome_unknown", "INTERRUPTED_RESEARCH"
                db.execute("UPDATE runs SET record=? WHERE id=?", (report.model_dump_json(by_alias=True), run_id))
