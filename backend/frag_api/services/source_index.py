"""Explicitly refreshed, directory-scoped multi-file FTS evidence."""
import json
import os
from pathlib import Path
from frag_api.errors import PolicyRejectedError, RagIndexNotReadyError, RagIndexStaleError
from frag_api.request_spec import fingerprint
from frag_api.repositories.rag_index_repository import RagIndexRepository, IndexDocument, IndexParent, IndexChunk
from frag_api.schemas.governance import SourceIdentity, SourceBinding
from frag_api.services.context_source_service import ContextSourceService, ContextSourceError, PARSER_VERSION, SUPPORTED
from frag_api.services.memory_service import search_terms
from frag_api.services.rag_markdown import MarkdownSection, children_for
from frag_api.services.runtime_policy import redact

EXCLUDED = {"node_modules", "dist", "venv", "agents.md", "agents.override.md", "settings.json", "chatlanguagemodels.json"}


class SourceIndex:
    def __init__(self, profile, directory):
        self.profile = profile
        root = Path(profile.root)
        if not root.is_absolute():
            raise PolicyRejectedError()
        if any(ContextSourceService._is_reparse_point(path) for path in (root, *root.parents)):
            raise PolicyRejectedError()
        self.sources = ContextSourceService(root, project_files=True)
        if not self.sources.root.is_dir() or self.sources._is_reparse_point(self.sources.root):
            raise PolicyRejectedError()
        for value in profile.excluded_paths:
            path = Path(value)
            if not value or path.is_absolute() or path.drive or ".." in path.parts or ":" in value:
                raise PolicyRejectedError()
        self.scope = {"sourceId": profile.id, "root": str(self.sources.root), "excludedPaths": profile.excluded_paths}
        self.repository = RagIndexRepository(Path(directory) / (fingerprint(self.scope) + ".sqlite3"))

    def excluded(self, path):
        parts = path.parts
        if any(part.startswith(".") or part.casefold() in EXCLUDED for part in parts):
            return True
        normalized = path.as_posix().casefold()
        return any(normalized == value.replace("\\", "/").strip("/").casefold() or normalized.startswith(value.replace("\\", "/").strip("/").casefold() + "/") for value in self.profile.excluded_paths)

    def manifest(self):
        files = {}
        for directory, folders, names in os.walk(self.sources.root, followlinks=False):
            parent = Path(directory)
            folders[:] = sorted(name for name in folders if not self.excluded((parent / name).relative_to(self.sources.root)) and not self.sources._is_reparse_point(parent / name))
            for name in sorted(names):
                path = parent / name
                relative = path.relative_to(self.sources.root)
                if self.excluded(relative) or path.suffix.lower() not in SUPPORTED or self.sources._is_reparse_point(path):
                    continue
                metadata, _ = self.sources.read_snapshot(relative.as_posix())
                files[relative.as_posix()] = metadata.sha256
        return {"scope": self.scope, "parserVersion": PARSER_VERSION + "/markdown-hierarchy-v2", "files": files}

    def saved_manifest(self):
        if not self.repository.path.exists():
            raise RagIndexNotReadyError()
        with self.repository._connect() as db:
            row = db.execute("SELECT value FROM rag_meta WHERE key='manifest'").fetchone()
        if row is None:
            raise RagIndexNotReadyError()
        return json.loads(row[0])

    def ready(self):
        saved = self.saved_manifest()
        if saved != self.manifest():
            raise RagIndexStaleError()
        return saved

    def status(self):
        try:
            self.ready()
            state = "ready"
        except RagIndexNotReadyError:
            state = "not_built"
        except (RagIndexStaleError, ContextSourceError, OSError):
            state = "stale"
        snapshot = self.repository.snapshot()
        return {"state": state, "documentCount": snapshot.document_count, "chunkCount": snapshot.chunk_count, "indexRevision": snapshot.index_revision}

    def build(self):
        manifest = self.manifest()
        documents, parents, chunks = [], [], []
        for relative, revision in manifest["files"].items():
            parsed = self.sources.parse(relative)
            if parsed.source.sha256 != revision:
                raise RagIndexStaleError()
            document_id = fingerprint(relative.casefold())[:24]
            documents.append(IndexDocument(document_id, self.profile.id, self.profile.id, revision))
            for item in parsed.sections:
                parent_id = fingerprint({"document": document_id, "locator": item.locator.id})[:24]
                text = redact(item.text)
                section = MarkdownSection(parent_id, item.locator.id, item.locator.label, item.locator.label, text)
                parents.append(IndexParent(parent_id, document_id, item.locator.id, item.locator.label, item.locator.label, text))
                for child in children_for(section):
                    chunk_id = fingerprint({"parent": parent_id, "ordinal": child.ordinal})[:24]
                    chunks.append(IndexChunk(chunk_id, document_id, self.profile.id, item.locator.id, item.locator.label,
                        child.ordinal, child.text, fingerprint(child.text), parent_id, " ".join(search_terms(child.text))))
        if manifest != self.manifest():
            raise RagIndexStaleError()
        self.repository.rebuild(documents, chunks, parents, fingerprint(manifest), manifest)
        return self.status()

    def identity(self, relative, revision):
        return SourceIdentity(kind="local_file", namespace="native-local-v1/" + fingerprint({"scope": self.scope, "hash": revision}), resourceId=fingerprint(relative.casefold())[:24])

    def scope_bindings(self, manifest):
        return [SourceBinding(identity=self.identity(relative, revision), revision=revision, parserVersion=manifest["parserVersion"], locatorIds=("scope",), evidenceIds=("scope",)) for relative, revision in manifest["files"].items()]

    def search(self, query, top_k):
        manifest = self.ready()
        terms = search_terms(query, query=True)
        if not terms:
            return [], []
        expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
        snapshot, hits, parents = self.repository.search_snapshot(expression, top_k)
        if snapshot.index_revision != fingerprint(manifest):
            raise RagIndexStaleError()
        relative_by_id = {fingerprint(path.casefold())[:24]: path for path in manifest["files"]}
        evidence, bindings = [], []
        for parent_id in dict.fromkeys(hit.parent_id for hit in hits):
            parent = parents[parent_id]
            relative = relative_by_id[parent.document_id]
            revision = manifest["files"][relative]
            hit = next(item for item in hits if item.parent_id == parent_id)
            position = max(0, parent.text.find(hit.text.partition("\n")[2]))
            start = max(0, position - 400)
            text = parent.text[start:start + 2200]
            evidence_id = fingerprint({"parent": parent_id, "revision": revision})[:24]
            evidence.append({"evidenceId": evidence_id, "sourceId": self.profile.id, "locatorId": parent.locator_id,
                "locatorLabel": parent.locator_label, "text": text, "sourceUri": self.sources._resolve(relative).as_uri(),
                "relativePath": relative, "parentId": parent_id, "windowed": start > 0 or len(text) < len(parent.text)})
            bindings.append(SourceBinding(identity=self.identity(relative, revision), revision=revision, parserVersion=manifest["parserVersion"], locatorIds=(parent.locator_id,), evidenceIds=(evidence_id,)))
        self.ready()
        return evidence, bindings

    def expand(self, evidence):
        self.ready()
        result = []
        for item in evidence:
            parent = self.repository.parent(item["parentId"])
            position = max(0, parent.text.find(item["text"]))
            start = max(0, min(position - 1500, len(parent.text) - 8000))
            result.append({**item, "text": parent.text[start:start + 8000], "windowed": start > 0 or len(parent.text) > 8000})
        self.ready()
        return result
