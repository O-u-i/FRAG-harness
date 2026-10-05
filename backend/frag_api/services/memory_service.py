"""Versioned reviewed memory in the existing application-owned SQLite database."""
import json
import re
from datetime import datetime, timezone
from uuid import uuid4

from pydantic import ValidationError

from frag_api.errors import PolicyRejectedError, RuntimeConflictError, RuntimeNotFoundError
from frag_api.request_spec import canonical_json, fingerprint
from frag_api.schemas.governance import SourceBinding
from frag_api.schemas.memory import MemoryRecord, MemorySelection
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
    def _latest(db, memory_id):
        row = db.execute("SELECT record FROM memory_versions WHERE id=? ORDER BY version DESC LIMIT 1", (memory_id,)).fetchone()
        if row is None:
            raise RuntimeNotFoundError()
        return MemoryRecord.model_validate_json(row[0])

    @staticmethod
    def _eligible(record, sources):
        selected = {canonical_json(source.identity.model_dump(by_alias=True)) for source in sources}
        scope = {canonical_json(source.model_dump(by_alias=True)) for source in record.scope}
        return record.status == "active" and not record.conflicts and (record.general or bool(scope) and scope.issubset(selected))

    @staticmethod
    def sources(report):
        if not report.requests:
            raise RuntimeConflictError()
        if report.snapshot_digest and report.snapshot_digest != fingerprint(report.selection.model_dump(by_alias=True)):
            raise RuntimeConflictError()
        try:
            sources = tuple(SourceBinding.model_validate(item) for item in report.requests[0].prepared_call.request_binding()["sources"])
        except (KeyError, TypeError, ValidationError) as error:
            raise RuntimeConflictError() from error
        if not sources or sources != report.selection.source_bindings:
            raise RuntimeConflictError()
        return sources

    def _append(self, db, record, **changes):
        value = MemoryRecord.model_validate({**record.model_dump(by_alias=True), **changes,
            "version":record.version + 1, "createdAt":datetime.now(timezone.utc).isoformat()})
        self._insert(db, value)
        return value

    @staticmethod
    def _insert(db, record):
        row = db.execute("INSERT INTO memory_versions VALUES (?,?,?)", (record.id, record.version, record.model_dump_json(by_alias=True)))
        db.execute("INSERT INTO memory_fts(rowid,tokens) VALUES (?,?)", (row.lastrowid, " ".join(search_terms(record.text))))

    def records(self):
        with self.repository.connection() as db:
            rows = db.execute("SELECT record FROM memory_versions m WHERE version=(SELECT MAX(version) FROM memory_versions WHERE id=m.id) ORDER BY rowid DESC").fetchall()
        return [MemoryRecord.model_validate_json(row[0]) for row in rows]

    def versions(self, memory_id):
        with self.repository.connection() as db:
            self._latest(db, memory_id)
            rows = db.execute("SELECT record FROM memory_versions WHERE id=? ORDER BY version", (memory_id,)).fetchall()
        return [MemoryRecord.model_validate_json(row[0]) for row in rows]

    def candidate(self, request):
        report = self.repository.get(request.run_id)
        sources = self.sources(report)
        output = report.model_output
        if output is None:
            raise RuntimeConflictError()
        if request.revision_id:
            revision = next((item for item in report.revisions if item.id == request.revision_id), None)
            if revision is None:
                raise RuntimeNotFoundError()
            if revision.content_digest and revision.content_digest != fingerprint(revision.result.model_dump(by_alias=True)):
                raise RuntimeConflictError()
            output = revision.result
        if request.revision_id is None:
            completed = [item for item in report.requests if item.stage == "inference" and item.status == "completed"]
            if completed and completed[-1].output_digest:
                saved = completed[-1]
                if (saved.output_digest != fingerprint(saved.output)
                        or fingerprint(output.model_dump(by_alias=True)) != saved.output_digest):
                    raise RuntimeConflictError()
        record = MemoryRecord(id=uuid4().hex, version=1, status="candidate",
            text=self._clean(request.text if request.text is not None else output.answer),
            scope=list(dict.fromkeys(s.identity for s in sources)), general=request.general, conflicts=[],
            provenanceRunId=report.run.id, provenanceRevisionId=request.revision_id,
            createdAt=datetime.now(timezone.utc).isoformat())
        with self.repository.connection() as db:
            self._insert(db, record)
        return record

    def revise(self, memory_id, request):
        with self.repository.connection() as db:
            saved = self._latest(db, memory_id)
            if saved.version != request.version:
                raise RuntimeConflictError()
            return self._append(db, saved, status="candidate", text=self._clean(request.text),
                general=saved.general if request.general is None else request.general, reviewNote=None)

    def promote(self, memory_id, request):
        with self.repository.connection() as db:
            saved = self._latest(db, memory_id)
            if saved.version != request.version or saved.status != "candidate" or saved.conflicts or request.reviewed is not True:
                raise RuntimeConflictError()
            return self._append(db, saved, status="active", reviewNote=self._clean(request.note))

    def retire(self, memory_id, request):
        with self.repository.connection() as db:
            saved = self._latest(db, memory_id)
            if saved.version != request.version or saved.status == "retired":
                raise RuntimeConflictError()
            return self._append(db, saved, status="retired")

    def conflict(self, request, resolve=False):
        with self.repository.connection() as db:
            records = [self._latest(db, item) for item in request.memory_ids]
            if resolve and {item.memory_id:item.version for item in request.versions} != {item.id:item.version for item in records}:
                raise RuntimeConflictError()
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
        return [MemoryRecord.model_validate_json(row[0]) for row in rows]

    def select(self, selections, sources, *, db=None):
        if len(selections) > 3 or len({item.memory_id for item in selections}) != len(selections):
            raise PolicyRejectedError()
        if db is None:
            with self.repository.connection() as connection:
                return self.select(selections, sources, db=connection)
        records = [self._latest(db, selection.memory_id) for selection in selections]
        if any(saved.version != choice.version or not self._eligible(saved, sources) for saved, choice in zip(records, selections)):
            raise PolicyRejectedError()
        return [{"memoryId":item.id, "version":item.version, "text":self._clean(item.text),
                 "general":item.general, "scope":[scope.model_dump(by_alias=True) for scope in item.scope]} for item in records]

    def validate_bindings(self, binding, *, db=None):
        try:
            references = binding.get("memoryVersions", [])
            if not isinstance(references, list):
                raise PolicyRejectedError()
            selections = [MemorySelection.model_validate(item) for item in references]
            sources = tuple(SourceBinding.model_validate(item) for item in binding["sources"])
            self.select(selections, sources, db=db)
        except (KeyError, TypeError, ValidationError, RuntimeNotFoundError) as error:
            raise PolicyRejectedError() from error
