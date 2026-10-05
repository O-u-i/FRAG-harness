# Reviewed runtime memory

FRAG owns reviewed background memory in the same private runtime SQLite database as Sessions and Runs. Its versioned tables and FTS5 index are separate from the rebuildable RAG index, development ledger and shared Mei. It requires no additional provider or dependency.

## Human workflow

1. Complete a Run and inspect its original model output or a human revision. On Memory, create a candidate using that Run ID and optional revision ID. The host derives provenance and source scope from the saved Run; a candidate cannot grant new source access.
2. Edit the candidate text. Keep its source scope unless intentionally marking a general lesson. Review the content and record a review note before promotion. Promotion creates a new active version; candidates are not usable.
3. From a selected-source preview, recommend memory for the current question. Recommendations are limited to three active, applicable records without known conflicts. Explicitly select each record for the next request, then prepare a fresh outbound preview and approve it.
4. Inspect the memory background in the actual request. Current evidence remains the source of citations and factual support. Each Research, Context or Inference request still needs separate approval.

New content or a changed general flag creates a candidate version requiring another review. Promotion, retirement, conflict declaration and reviewed conflict resolution also append versions. Earlier versions remain inspectable; old selections cannot silently switch to a new version. A mutation makes affected prepared requests unusable, including at a persisted checkpoint. Reselect current versions and start a linked new Run when changing input.

Known conflicts are declared by a human between two records. They block both records from recommendation and explicit selection. Resolve a conflict only after reviewing both current versions and providing a note; a concurrent edit rejects that resolution. FRAG does not automatically infer contradictions or judge whether a memory is true.

## Scope and retrieval

Scoped records require all of their saved source identities to be present in the current selection. Kind, namespace, resource ID and Finance Core Workspace ID participate in the identity check. Marking a lesson general is an explicit human operation; it makes that reviewed background applicable across scopes without expanding evidence permissions. Finance Core remains on the fixed read-only path.

FTS5 searches normalized English terms and Chinese characters/bigrams. The host filters latest version, active status, known conflicts and scope before ranking and returning at most three records. Punctuation-only queries return no matches; blank queries are rejected. Query punctuation is data, not raw FTS syntax. This is keyword recommendation, not vector retrieval or a semantic-relevance claim. A local record scan is sufficient for the current local corpus; add SQL scope indexes only if measured corpus size warrants them.

## Frozen request and recovery

Source requests carry `selectedMemory: [{memoryId, version}]`, with at most three distinct records. This field is the explicit confirmation; recommendation alone never injects memory. The server validates each record and adds a separate `memory` background array to the model input. `PreparedCall.binding.memoryVersions` binds the exact references; the normal request fingerprint, budget checks and redaction cover the memory text too.

All model dispatch paths validate memory again within the durable Run claim transaction. Historical request specifications retain the previously selected snapshots. Memory changes do not rewrite model output, historical reports or earlier request bodies. Restart preserves memory records and version history; it never restores an old approval token. Source/configuration changes and stale memory reject continuation. Unknown model-call outcomes are never resent automatically.

Memory text and review notes are redacted before record/FTS writes and before model input. Runtime databases, snapshots, exports and real sources remain Git-ignored. No memory candidate is written to Mei or published into the repository.

## HTTP contracts

| Operation | Endpoint | Body |
| --- | --- | --- |
| List latest records | `GET /api/memory` | None |
| Inspect versions | `GET /api/memory/{id}/versions` | None |
| Create candidate | `POST /api/memory/candidates` | `runId`, optional `revisionId` / `text`, explicit `general` when needed |
| Edit | `POST /api/memory/{id}/revisions` | Current `version`, edited `text`, optional `general` |
| Promote | `POST /api/memory/{id}/promote` | Current `version`, `reviewed: true`, nonblank `note` |
| Retire | `POST /api/memory/{id}/retire` | Current `version` |
| Declare conflict | `POST /api/memory/conflicts` | Two distinct `memoryIds` |
| Resolve conflict | `POST /api/memory/resolve-conflict` | Two `memoryIds`, their current `versions` references, `reviewed: true`, nonblank `note` |
| Recommend | `POST /api/memory/recommend` | Selected preview's `runId`, `query` |

Lists and recommendations return arrays; single-record mutations return the resulting version. These human HTTP operations are not model tools. The tool registry still exposes only bounded selected-evidence reads.

Phase 6 acceptance uses synthetic offline providers and real local SQLite/tool execution. The previously deferred Phase 5 live GPT/KB and human semantic acceptance remain pending, as does final Phase 8 integrated acceptance.
