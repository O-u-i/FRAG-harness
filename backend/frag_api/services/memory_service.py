"""Versioned reviewed memory in the existing application-owned SQLite database."""
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from frag_api.errors import PolicyRejectedError, RuntimeConflictError, RuntimeNotFoundError
from frag_api.request_spec import canonical_json
from frag_api.schemas.memory import MemoryRecord
from frag_api.services.runtime_policy import redact


def search_terms(text, *, query=False):
    terms = re.findall(r"[^\W_]+", text.lower(), flags=re.UNICODE)
    result = []
    for term in terms:
        for part in re.findall(r"[\u3400-\u9fff]+|[^\u3400-\u9fff]+", term):
            if re.fullmatch(r"[\u3400-\u9fff]+", part):
                if not query or len(part) == 1:
                    result.extend(part)
                result.extend(part[index:index + 2] for index in range(len(part) - 1))
            else:
                result.append(part)
    return list(dict.fromkeys(result))


class MemoryService:
    def __init__(self, runtime):
        self.runtime = runtime
        self.repository = runtime.repository
        with self.repository.connection() as db:
            db.execute("CREATE TABLE IF NOT EXISTS memory_meta (id INTEGER PRIMARY KEY CHECK(id=1), schema_version INTEGER NOT NULL)")
            row = db.execute("SELECT schema_version FROM memory_meta WHERE id=1").fetchone()
            if row is not None and row[0] != 1:
                raise ValueError("Unsupported memory database schema.")
            db.execute("INSERT OR IGNORE INTO memory_meta VALUES (1,1)")
            db.execute("CREATE TABLE IF NOT EXISTS memory_versions (id TEXT NOT NULL, version INTEGER NOT NULL, record TEXT NOT NULL, PRIMARY KEY(id,version))")
            db.execute("CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts USING fts5(tokens)")

    def _clean(self, text):
        value = redact(text, self.runtime.redaction_secrets).strip()
        if not value or len(value) > 4000:
            raise RuntimeConflictError()
        return value

    @staticmethod
    def _content(record):
        return (record.text, record.general, tuple(sorted(canonical_json(item.model_dump(by_alias=True)) for item in record.scope)))

    @classmethod
    def _history(cls, db, memory_id):
        rows = db.execute("SELECT record FROM memory_versions WHERE id=? ORDER BY version", (memory_id,)).fetchall()
        if not rows:
            raise RuntimeNotFoundError()
        history, previous, content_version = [], None, 0
        for row in rows:
            record = MemoryRecord.model_validate_json(row[0])
            content = cls._content(record)
            content_version += content != previous
            previous = content
            # Derive old content versions without rewriting immutable audit rows or pins.
            history.append(record.model_copy(update={"content_version": content_version}))
        return history

    @classmethod
    def _latest(cls, db, memory_id):
        return cls._history(db, memory_id)[-1]

    @staticmethod
    def _eligible(record, sources):
        selected = {canonical_json(source.identity.model_dump(by_alias=True)) for source in sources}
        scope = {canonical_json(source.model_dump(by_alias=True)) for source in record.scope}
        return record.status == "active" and not record.conflicts and (record.general or bool(scope) and scope.issubset(selected))

    @staticmethod
    def sources(report):
        sources = tuple(report.source_bindings)
        if report.status != "completed" or not sources or not report.pack:
            raise RuntimeConflictError()
        return sources

    def _append(self, db, record, **changes):
        value = MemoryRecord.model_validate({**record.model_dump(by_alias=True), **changes,
            "version":record.version + 1, "createdAt":datetime.now(timezone.utc).isoformat()})
        value = value.model_copy(update={"content_version": record.content_version + (self._content(value) != self._content(record))})
        self._insert(db, value)
        return value

    @staticmethod
    def _insert(db, record):
        # Content version is derived from history; keep the stored audit schema unchanged.
        row = db.execute("INSERT INTO memory_versions VALUES (?,?,?)", (record.id, record.version, record.model_dump_json(by_alias=True, exclude={"content_version"})))
        db.execute("INSERT INTO memory_fts(rowid,tokens) VALUES (?,?)", (row.lastrowid, " ".join(search_terms(record.text))))

    def records(self):
        with self.repository.connection() as db:
            rows = db.execute("SELECT id FROM memory_versions m WHERE version=(SELECT MAX(version) FROM memory_versions WHERE id=m.id) ORDER BY rowid DESC").fetchall()
            return [self._latest(db, row[0]) for row in rows]

    def versions(self, memory_id):
        with self.repository.connection() as db:
            return self._history(db, memory_id)

    def candidate(self, request):
        report = self.repository.get(request.run_id)
        sources = self.sources(report)
        record = MemoryRecord(id=uuid4().hex, version=1, status="candidate",
            text=self._clean(request.text),
            scope=list(dict.fromkeys(s.identity for s in sources)), general=request.general, conflicts=[],
            provenanceRunId=report.id,
            createdAt=datetime.now(timezone.utc).isoformat())
        with self.repository.connection() as db:
            self._insert(db, record)
        return record

    def require_native(self, db, record):
        if not db.execute("SELECT 1 FROM tool_runs WHERE id=?", (record.provenance_run_id,)).fetchone():
            raise PolicyRejectedError()

    def revise(self, memory_id, request):
        with self.repository.connection() as db:
            saved = self._latest(db, memory_id)
            self.require_native(db, saved)
            if saved.version != request.version:
                raise RuntimeConflictError()
            text = self._clean(request.text)
            general = saved.general if request.general is None else request.general
            if (text, general) == (saved.text, saved.general):
                return saved
            return self._append(db, saved, status="candidate", text=text, general=general, reviewNote=None)

    def promote(self, memory_id, request):
        with self.repository.connection() as db:
            saved = self._latest(db, memory_id)
            self.require_native(db, saved)
            if saved.version != request.version or saved.status != "candidate" or saved.conflicts or request.reviewed is not True:
                raise RuntimeConflictError()
            return self._append(db, saved, status="active", reviewNote=self._clean(request.note))

    def retire(self, memory_id, request):
        with self.repository.connection() as db:
            saved = self._latest(db, memory_id)
            self.require_native(db, saved)
            if saved.version != request.version or saved.status == "retired":
                raise RuntimeConflictError()
            return self._append(db, saved, status="retired")

    def conflict(self, request, resolve=False):
        with self.repository.connection() as db:
            records = [self._latest(db, item) for item in request.memory_ids]
            if resolve and {item.memory_id:item.version for item in request.versions} != {item.id:item.version for item in records}:
                raise RuntimeConflictError()
            for record in records:
                self.require_native(db, record)
            result = []
            for saved, other in ((records[0], records[1]), (records[1], records[0])):
                if resolve:
                    if request.reviewed is not True or other.id not in saved.conflicts:
                        raise RuntimeConflictError()
                    conflicts = [item for item in saved.conflicts if item != other.id]
                    note = self._clean(request.note)
                else:
                    if saved.status == "retired" or other.id in saved.conflicts:
                        raise RuntimeConflictError()
                    conflicts, note = sorted([*saved.conflicts, other.id]), saved.review_note
                result.append(self._append(db, saved, conflicts=conflicts, reviewNote=note))
            return result

    def recommend(self, query, sources):
        terms = search_terms(self._clean(query), query=True)
        if not terms:
            return []
        # ponytail: local record scan; SQL scope indexes only if corpus size warrants them.
        expression = " OR ".join('"' + item.replace('"', '""') + '"' for item in terms)
        with self.repository.connection() as db:
            latest = db.execute("SELECT record FROM memory_versions m WHERE version=(SELECT MAX(version) FROM memory_versions WHERE id=m.id)").fetchall()
            eligible = {f"{item.id}:{item.version}" for row in latest
                        if self._eligible(item := MemoryRecord.model_validate_json(row[0]), sources)}
            if not eligible:
                return []
            rows = db.execute("""SELECT m.record FROM memory_fts JOIN memory_versions m ON m.rowid=memory_fts.rowid
                WHERE memory_fts MATCH ? AND (m.id || ':' || m.version) IN (SELECT value FROM json_each(?))
                ORDER BY bm25(memory_fts), m.rowid DESC LIMIT 3""", (expression, json.dumps(sorted(eligible)))).fetchall()
            return [self._latest(db, MemoryRecord.model_validate_json(row[0]).id) for row in rows]

    def select(self, selections, sources, *, db=None):
        if len(selections) > 3 or len({item.memory_id for item in selections}) != len(selections):
            raise PolicyRejectedError()
        if db is None:
            with self.repository.connection() as connection:
                return self.select(selections, sources, db=connection)
        records = [self._latest(db, selection.memory_id) for selection in selections]
        if any(saved.version != choice.version or not self._eligible(saved, sources) for saved, choice in zip(records, selections)):
            raise PolicyRejectedError()
        return [{"memoryId":item.id, "version":item.version, "contentVersion":item.content_version, "text":self._clean(item.text),
                 "general":item.general, "scope":[scope.model_dump(by_alias=True) for scope in item.scope]} for item in records]
