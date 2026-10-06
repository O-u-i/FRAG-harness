"""One explicitly selected file/locator cache; never a mutable active dataset."""
from pathlib import Path
import hashlib
import os

from frag_api.errors import HarnessSourceError, RagIndexNotReadyError, RagIndexStaleError
from frag_api.repositories.rag_index_repository import IndexDocument, IndexChunk, IndexParent, RagIndexRepository
from frag_api.request_spec import fingerprint
from frag_api.schemas.rag import RagIndexStatus
from frag_api.services.context_source_service import ContextSourceError, PARSER_VERSION
from frag_api.services.rag_markdown import MarkdownSection, children_for

DATASET_ID = "selected-local-v1"
STRATEGY = "markdown-hierarchy-v2"


class SelectedRagIndex:
    def __init__(self, sources, cache_root: Path, selection):
        try:
            parsed = sources.parse(selection.relative_path)
            selected = {item.locator.id: item for item in parsed.sections}
            self.sections = [selected[key] for key in selection.locator_ids]
            if not parsed.source.sha256 or len({item.locator.id for item in self.sections}) != len(self.sections):
                raise ValueError()
        except (ContextSourceError, KeyError, OSError, ValueError, UnicodeError) as error:
            raise HarnessSourceError() from error
        self.sources, self.relative_path, self.source_hash = sources, parsed.source.relative_path, parsed.source.sha256
        normalized = self.relative_path.casefold() if os.name == "nt" else self.relative_path
        self.scope = {"root": str(sources.root), "relativePath": normalized, "locatorIds": sorted(selection.locator_ids)}
        key = fingerprint(self.scope)
        self.repository = RagIndexRepository(cache_root / (key + ".sqlite3"))
        self.document_id = "rag-selected-" + key[:24]
        self.source_id = "selected-file-" + fingerprint({"root": str(sources.root), "relativePath": normalized})[:24]
        self.namespace = fingerprint({**self.scope, "sourceHash": self.source_hash})
        self.parser_version = PARSER_VERSION + "/" + STRATEGY

    def current_hash(self):
        try:
            return self.sources.read_snapshot(self.relative_path)[0].sha256
        except (ContextSourceError, OSError, ValueError) as error:
            raise HarnessSourceError() from error

    def status(self):
        snapshot = self.repository.snapshot()
        state = ("not_built" if snapshot.index_revision is None else
                 "stale" if snapshot.schema_version != "2" or snapshot.source_hash != self.source_hash else "ready")
        return RagIndexStatus(datasetId=DATASET_ID, state=state, documentCount=snapshot.document_count,
            chunkCount=snapshot.chunk_count, indexRevision=snapshot.index_revision, sourceHash=snapshot.source_hash)

    def require_ready(self):
        status = self.status()
        if status.state == "not_built":
            raise RagIndexNotReadyError()
        if status.state == "stale":
            raise RagIndexStaleError()
        return status

    def rebuild(self, search_text):
        parents, chunks = [], []
        for item in self.sections:
            parent_id = self.document_id + "-" + fingerprint(item.locator.id)[:16]
            section = MarkdownSection(parent_id, item.locator.id, item.locator.label, item.locator.label, item.text)
            parents.append(IndexParent(parent_id, self.document_id, item.locator.id,
                item.locator.label, item.locator.label, item.text))
            try:
                children = children_for(section)
            except ValueError as error:
                raise HarnessSourceError() from error
            for child in children:
                chunks.append(IndexChunk(f"{self.document_id}-c{len(chunks) + 1:03d}", self.document_id,
                    self.source_id, item.locator.id, item.locator.label, len(chunks) + 1, child.text,
                    hashlib.sha256(child.text.encode("utf-8")).hexdigest(), parent_id, search_text(child.text)))
        revision = fingerprint({"datasetId": DATASET_ID, "scope": self.scope, "sourceHash": self.source_hash,
            "parserVersion": self.parser_version, "chunks": [item.text_hash for item in chunks]})
        self.repository.rebuild(IndexDocument(self.document_id, DATASET_ID, self.source_id, self.source_hash),
            chunks, parents, revision)
        if self.current_hash() != self.source_hash:
            raise RagIndexStaleError()
        return self.status()
