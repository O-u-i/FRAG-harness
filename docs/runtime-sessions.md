# Sessions, review and safe recovery

Fixed and optional Research workflows share one application lifecycle owner. A Session groups related Runs. A Run owns its explicitly selected redacted snapshot, frozen request specifications, stage attempts, charged budget, reliable Context checkpoint, model original, human decisions, independent revisions and selected-read tool observations. Runtime database schema version 1 is independent of the application version; older reports default to an empty toolCalls list and null research state. RAG indexing remains a separate, rebuildable cache.

The default database is `.local-runtime/runtime.sqlite3`; `FRAG_RUNTIME_PATH` or `create_app(runtime_path=...)` can select another local path. Keep the database, WAL/SHM files, owner lock and exports outside Git. One app lifetime holds a nonblocking file lease; a second app cannot take ownership of the same database. SQLite transactions commit each dispatch claim, response, checkpoint or review as one record, and roll back incomplete writes. This is crash recovery, not tamper-proof storage or legal audit certification.

Snapshots, committed response payloads and human revision content carry SHA-256 digests of canonical redacted JSON. Recovery checks the saved snapshot digest and startup checks an unfinished saved response digest. Request fingerprints already bind outbound specifications and version metadata. These digests detect content mismatch; they do not certify authorship, factual truth or immutable filesystem storage.

## State and approvals

Preview saves a `ready_context` Run, or a paused Run if its input checklist blocks approval. It creates a volatile one-use token only when allowed. Each stage atomically claims its currently active prepared attempt before dispatch. Replacing a preview invalidates the previous attempt even if its token remains in RAM. Context saves an `awaiting_inference` checkpoint before building the next preview. Completed Inference becomes `awaiting_review` after structural and citation checks.

Provider responses are redacted before the HTTP response and persistence. Credential settings, authentication headers, executable approval tokens and raw exception text are not persisted. Selected input copies are redacted history, not reusable authorization. Automatic redaction cannot identify every private value; review outbound text and protect local files.

Calls reserve estimated input plus the output ceiling before dispatch. Committed responses replace that reservation with reported usage, using reserved components when usage is missing. Unknown and failed calls retain conservative reservations. Subsequent attempts carry the same cumulative 30,000-token budget. Estimates are not model-specific tokenization.

## Explicit recovery

Opening history, exporting reports or preparing recovery makes no model call. Reselect files/locators, the synthetic query or released plugin records explicitly. The host matches source identities/root namespaces, revisions, parsers, evidence scope, redacted content, goal, checklist, model routes, limits, prompt/output contracts and host/policy versions. Changing these requires Reopen, which creates a linked Run in the same Session. A changed FC Workspace never inherits permission from an earlier Run.

Raw selection hashes cannot be reconstructed from redacted history. Recovery compares explicit source bindings and the complete request specification, excluding only old selection/context correlation hashes, and creates a fresh request/token. Historical specifications remain in the report. Redacted file paths may require manual re-entry. Configuration or source changes reject continuation.

A reliable selected snapshot before Context can produce a fresh Context preview. After validated Context, recovery produces a fresh Inference preview and carries the persisted budget. A committed response interrupted before host validation finishes is checked offline on startup; a valid saved response is not repeated. While live host processing remains unresolved, continuation is refused. A dispatch with no committed response becomes `outcome_unknown` on restart and cannot resume or automatically retry. Reconcile it manually before deliberately reopening a distinct Run.

Tokens expire after ten minutes, are one-use, and are cleared at both lifecycle boundaries. No token is restored from SQLite. Model timeout remains 120 seconds and automatic retries remain zero. In-flight approved work cannot be revoked, but a durable pause/rejection prevents the next stage. Returned results do not overwrite that decision.

## Human decisions and reports

Review preserves checklist identities, text and blocking flags; only status and reviewed flags may change. Attempted acceptance with an unmet/unreviewed blocking item records a pause. Nonblocking gaps remain `missing`, `unknown` or `pending`. Missing model output cannot be accepted. A review before output exists controls the workflow and does not assert correctness of a future output. Resuming a paused Run requires satisfied critical review items and a new outbound approval.

Human revisions receive separate immutable IDs and require independent review. A review of the model original cannot approve a revision. `semanticReview` describes the latest revision when one exists, otherwise the model original. Original output and previous decisions remain visible. Citation membership in a human edit does not prove support; the human checks facts, qualifiers, negation and evidence support.

The page, JSON and Markdown render one `RunReport`. Structural validation and human semantic review separately use `PASS`, `FAIL`, `ERROR`, `NOT_RUN` or `UNDETERMINED`. Authority/freshness remain unknown unless known metadata is supplied. Markdown quotes the complete record with a fence that cannot be terminated by embedded backticks. Exports make no model call. History lists the latest 200 Sessions/Runs; older Runs remain addressable by ID. No deletion, retention scheduler or memory promotion is implemented in this phase.

## HTTP endpoints

| Endpoint | Behavior |
| --- | --- |
| `GET/POST /api/runtime/sessions` | List/create Session groups |
| `GET /api/runtime/runs?sessionId=...` | List latest Runs, optionally within a Session |
| `GET /api/runtime/runs/{id}` | Canonical structured report |
| `GET /api/runtime/runs/{id}/report.json` | Same report as JSON |
| `GET /api/runtime/runs/{id}/report.md` | Deterministic Markdown download |
| `POST /api/runtime/runs/{id}/review` | Human decision bound to model or revision |
| `POST /api/runtime/runs/{id}/revisions` | Separate edited result; original preserved |
| `POST /api/runtime/runs/{id}/resume/preview` | Explicit `{sourceRequest: ...}` and fresh preview |
| `POST /api/runtime/runs/{id}/reopen` | Changed selection creates a linked Run/preview |
| `POST /api/runtime/runs/{id}/tools/execute` | Host-validated selected KB read, with a unique call ID and explicit reselection |
| `POST /api/runtime/research/preview` | Explicit kind and sourceRequest start a Research Run and exact first preview |
| `POST /api/runtime/runs/{id}/research/preview` | Explicit original sourceRequest revalidates and previews the next Research, Context or Inference checkpoint |
| `POST /api/runtime/runs/{id}/research/execute` | One freshly approved frozen checkpoint, followed by its allowed serial read tools; returns the canonical report |

Fixed execution uses the existing `/api/harness/run`, `/api/rag/run` and their `/inference/run` endpoints. Each stage needs its own exact preview and explicit one-use approval. The host CLI uses these same HTTP boundaries, with terminal confirmation before each model stage. Selected KB tools are available before Context, limited to six serial calls. Unresolved tool calls prevent model dispatch; interrupted tools become outcome_unknown on restart. Pi, curated memory, generic plugin protocol and real-KB acceptance remain later phases.

## Research history and restoration

A Research Run begins at `ready_research`. Its separate `research` state records
numbered turns, attempt identities, validated continue/finish decisions, observed
evidence selection and missing information. Attempt preparation and its pending
turn pointer update atomically. A stale preview cannot override a later human
pause. Direct fixed execution and manually submitted tools cannot bypass the
Research runner's decisions.

Research preserves the complete original typed selection for continuation.
Changing inputs uses an explicitly linked new Run. A complete approved decision
may execute its selected read tools automatically; preparing the next model turn
is explicit and requires a fresh approval. After finish, Context receives only
observed selected evidence. Context and Inference remain separate approved calls.

Startup can validate a reliably saved response without repeating its model call.
Pending selected tools resume only on an explicit revalidated continuation; the
host skips reliably completed calls. Interrupted model/tool dispatches become
unknown and cannot resume in the same Run. Saved histories must match the frozen
proposal, tool version/carrier, per-call selected scope, result pairing and
response digest. Restored formal stages apply the same evidence, gap and budget
checks as live validation. These consistency checks do not make local storage
tamper-proof. See [Research loop](research-loop.md).
