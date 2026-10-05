# FRAG-harness v1.7.0

The optional [Pi Responses adapter](docs/pi-adapter.md) uses a pinned, reviewed backend-only module selection. Enable it separately for Research, Context and Inference; every request retains exact preview and one-use approval. Synthetic live GPT acceptance remains a Phase 5 human gate.

FRAG-harness is a local application for governed evidence retrieval, an optional bounded Research loop and two formal model stages. It starts with no Finance Core installation, account, token, or database. Research collects selected evidence through real read tools; the Context LLM compresses approved evidence and the Inference LLM produces a cited answer. Selection, redaction, token budgeting, approval, output validation, and citation checks are deterministic host code.

## What runs in the core

The React interface offers Harness, RAG Lab, Runs, Memory, and Plugins. The FastAPI backend owns local source parsing, exact outbound previews, single-use approval tokens for each model stage, the two model routes, citation validation, durable run history and human review, and a rebuildable SQLite FTS5 index for a bundled synthetic RAG dataset. Fake model providers work offline. Real model API credentials live only in `backend/.env`.

Both stages execute the server-owned `PreparedCall` that was previewed. It binds the complete request JSON, destination, transport, model, output schema, timeout, source revisions, selected locators, checklist and host policy versions. Revalidation rejects changed bindings; execution does not rebuild a request from evidence. Source hashing and parsing use one byte snapshot, and RAG hits, parent text and index revision share a database read snapshot. Input estimates include instructions and schemas; each stage and the cumulative run have budget checks.

The host exposes executable CLI, tool and loop registrations through `GET /api/harness/capabilities`. The fixed runner remains available; optional Research proposes selected read calls, executes them through host policy, and returns observations to a later separately approved model turn. `frag.host` operates the same running FastAPI host over loopback HTTP; `kb.search` searches explicitly selected evidence and `kb.read` starts a fixed CLI process to read the selected redacted snapshot. Tools cannot expand file, locator, revision or Workspace scope. Reviewed memory is available through the [human memory workflow](docs/runtime-memory.md); only explicitly confirmed, active versions enter a fresh request. Blocking checklist items require a reviewed `met` status before approval is available. See [Research loop](docs/research-loop.md), [runtime contracts](docs/runtime-contracts.md), [host CLI](docs/host-cli.md) and [KB tools](docs/kb-tools.md).

Runs stores explicitly selected, redacted snapshots and request specifications in an independent, Git-ignored `.local-runtime/runtime.sqlite3`. Use the session picker to group work. Editing input creates a linked new run; editing output creates a separate human revision while retaining the model original. The Runs page records acceptance, rejection and pause, and exports the same structured report as JSON or Markdown. A new revision requires its own review.

Recovery requires explicit reselection matching the saved sources, scope, revisions and request configuration, then a fresh preview and approval. A validated Context checkpoint resumes at Inference. A durably saved response can finish deterministic validation after restart. An interrupted dispatch without a committed response becomes `outcome_unknown` and cannot resume in the same run. It is never resent automatically. See [sessions and recovery](docs/runtime-sessions.md) for state, privacy and endpoint details.

Offline evaluation uses versioned synthetic Gold and the production retrieval, model-stage validators, selected-read policy and tool carriers. Research cases record actual approved turns, serial tool execution, result feedback and finish decisions. Evaluation separates host enforcement, scripted model artifacts, trajectory checks, missing checks and scorer failures. Literal fact and trajectory checks do not establish semantic support; human review remains undetermined. See [offline evaluation](docs/offline-evaluation.md).

Memory candidates come from a saved model output or human revision. Editing, reviewing and promoting are human operations; FTS5 recommends at most three records after scope, status and conflict filtering. The next request binds their exact versions as background, while citations remain restricted to current evidence. Changing memory invalidates old previews. See [runtime memory](docs/runtime-memory.md).

## Architecture review diagrams

These six SVG exports describe the fixed Harness, RAG Lab, optional Research and reviewed-memory paths. Each Archify diagram has a linked interactive HTML view and an editable Archify JSON specification under `docs/architecture/`. They are review documentation, not runtime telemetry or orchestration. Reviewed memory follows the same exact preview, version revalidation and one-use approval gates.

### Harness

The Harness path assembles only explicitly selected local excerpts or optional, bounded Finance Core records. The host controls redaction, exact outbound previews, approvals, and validation around the two model APIs. [Explore the Harness data flow](docs/architecture/harness/dataflow.html).

![Harness data flow from selected evidence through the Context and Inference gates to human review](docs/architecture/harness/dataflow.svg)

Each stage requires a separate exact-input preview and a single-use approval. The host re-reads evidence and checks source bindings and confirmed memory versions before a call; invalid approval stops that stage. [Explore the Harness approval lifecycle](docs/architecture/harness/lifecycle.html).

![Harness lifecycle with separate Context and Inference approval gates and human review](docs/architecture/harness/lifecycle.svg)

### RAG Lab

RAG Lab has a Build path and a query path. Explicit Build parses headings and title paths from the bundled synthetic Markdown file, recursively splits each section into overlapping small chunks, and stores child-to-parent relationships in a separate SQLite FTS5 index. Source or index-strategy changes require an explicit rebuild. A query ranks small chunks by retrieval `chunkId`; Preview deduplicates their parent sections and shows bounded parent context with a marked hit window and a distinct Context `evidenceId`. Search and Preview make no model call. [Explore the RAG index and retrieval flow](docs/architecture/rag-lab/dataflow.html).

![RAG Lab flow from explicit synthetic indexing through FTS5 retrieval to an exact Context preview](docs/architecture/rag-lab/dataflow.svg)

After retrieval, the optional answer path needs a ready index and retrieved evidence before Context Run. Context and Inference each require an exact input preview and independent one-time approval. The host checks compressed Context `evidenceId` values after the Context call and answer `evidenceIds` citations after the Inference call, before human review. [Explore the RAG query and approval lifecycle](docs/architecture/rag-lab/lifecycle.html).

![RAG Lab lifecycle from a ready-index query through two approvals and citation checks to human review](docs/architecture/rag-lab/lifecycle.svg)

Preview never calls a model. The first Run executes only the Context stage and returns validated compression plus the exact Inference instructions and input JSON for a second approval. Inference Run executes the second stage after approval. Tokens expire after ten minutes, are consumed once, and bind the displayed input to its source or index revision. Changed inputs and reused tokens are rejected. Provider credentials stay in the backend.

### Research and recovery

Research gathers evidence before Context and Inference. A model proposes complete calls; the host validates scope and budgets, runs the registered read tools, and persists their observations. Continuing requires a new exact preview and approval. Finishing selects observed evidence for the two separately approved answer stages. [Explore the Research workflow](docs/architecture/research/workflow.html) · [Editable source](docs/architecture/research/workflow.json).

![Research workflow with approved model turns, bounded read tools and separate answer stages](docs/architecture/research/workflow.svg)

The following recovery flow summarizes the reliable-checkpoint path. Source, configuration or selected memory version changes reject continuation. Unknown dispatch outcomes cannot be resent in the same run. A saved response may complete deterministic validation after restart; validation is not human acceptance.

```mermaid
flowchart TD
    Restart[Restart and inspect durable run] --> Outcome{Reliable checkpoint or saved response?}
    Outcome -->|No committed response after dispatch| Unknown[outcome_unknown - no automatic resend]
    Outcome -->|Reliable| Select[Explicitly reselect saved sources]
    Select --> Check{Scope revisions configuration and memory versions match?}
    Check -->|No| Reject[Reject continuation]
    Check -->|Yes| Restore[Restore reliable stage and validate saved response]
    Restore -->|Already complete| Review[Awaiting human review]
    Restore -->|Model stage remains| Preview[Fresh exact preview for next model call]
    Preview --> Approval[Fresh one-use approval]
    Approval --> Execute[Execute frozen PreparedCall]
```

### Reviewed memory

A saved Run supplies a candidate, not reusable authority. Human editing, review and promotion produce an active version. Scope and conflict filtering precede FTS5 recommendations; you confirm at most three exact versions before a fresh preview. The host revalidates them before each Research, Context or Inference dispatch. Memory stays separate from current evidence, the rebuildable RAG index and shared Mei storage. [Explore the memory workflow](docs/architecture/memory/workflow.html) · [Editable source](docs/architecture/memory/workflow.json) · [Runtime memory details](docs/runtime-memory.md).

![Reviewed memory workflow from a saved Run through human promotion and scoped recommendation to approved dispatch](docs/architecture/memory/workflow.svg)

The lifecycle below summarizes human-controlled version changes. Retired and known-conflict records are excluded from normal recommendations; editing an active record requires review again. Historical outputs retain the versions they used.

```mermaid
flowchart LR
    Saved[Saved model output or human revision] --> Candidate[Editable candidate]
    Candidate -->|Human review and promotion| Active[Active reviewed version]
    Active -->|Edit creates a new version| Candidate
    Active -->|Record known conflict| Conflict[Excluded pending reviewed resolution]
    Conflict -->|Review current versions and resolve| Active
    Active -->|Human retirement| Retired[Retired with history retained]
    Candidate -->|Human retirement| Retired
```

## Start locally

Requires Node.js, npm, Python 3.12, and `uv`. From the repository root:

```powershell
npm install
uv sync --project backend --cache-dir .tmp/uv-cache
npm run dev
```

Open `http://localhost:5173`; the backend listens on `http://127.0.0.1:8787`. To configure either model, copy `backend/.env.example` to the Git ignored `backend/.env` and set provider, model, and backend-only credentials. `fake` is the default for both stages. Put supported `.md`, `.txt`, `.html`, `.pdf`, `.docx`, `.csv`, or `.xlsx` files under `local-sources/`; the folder is ignored except for instructions and placeholders. Files are never automatically indexed by the product.

The RAG Lab source is `shared/demo/rag/synthetic-risk-review.md`. English words and Chinese bigrams are indexed as keyword terms; there is no embedding or vector retrieval. KB notes are not a product source.

Local caches, browser review profiles, and disposable test evidence under `.tmp/` have different retention rules. See the [temporary workspace guide](docs/tmp-workspace.md) before moving or cleaning them.

## Optional Finance Core plugin

The core has no Finance Core routes or navigation while the plugin is absent or disabled. A trusted plugin archive contains exactly `manifest.json`, `adapter.py`, and `ui.js`. Its manifest declares `id: finance-core`, `protocolVersion: 1`, its semantic version, `minHostVersion: 1.0.0`, `fcApiVersion: 3.1.1`, and SHA-256 hashes for both code files. The installer checks the pinned archive hash, bounded entry sizes, file hashes, and compatibility before activation. Installed code executes in the local backend, so install only a trusted release. Finance Core distributes the optional archive separately; synthetic tests verify the host without FC credentials or a live Vault.

```powershell
# Official pinned GitHub release asset
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/install-plugin.ps1 -ReleaseUrl '<github-release-asset-url>' -ExpectedSha256 '<64-character-sha256>'

# Or a separately obtained local archive
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/install-plugin.ps1 -ArchivePath './finance-core-plugin.zip' -ExpectedSha256 '<64-character-sha256>'

# Disable without removing installed files
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/install-plugin.ps1 -Disable

# Re-enable an installed version
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/install-plugin.ps1 -Enable
```

Restart FRAG after install or disable. The plugin supplies a read-only dashboard and scoped Workspace record choices. Journal and all other mutations open Finance Core's own UI. A selected Workspace and at most ten record IDs enter the host preview through a read-only FC `/api/v3` adapter; the host never opens FC SQLite or indexes the whole finance database. The FC token stays backend-only. The adapter checks FC 3.1.1 health and version before bounded reads. Installing the archive does not configure FC or establish live integration; that requires a separately reviewed local FC setup.

The local Plugins page also accepts a trusted ZIP and its published SHA-256 for installation, and offers Enable, Disable, and Uninstall controls when a package is on disk. These controls run the same pinned PowerShell installer. Uninstall removes all locally installed Finance Core plugin versions and the activation pointer, after confirming every version contains only the three expected files. A successful management action hides plugin routes for the rest of that server session. Restart FRAG to load or unload the package. The private Sites design preview cannot perform these local operations.

```mermaid
flowchart LR
    Installer[Pinned archive and SHA-256] --> Manifest[Versioned plugin manifest]
    Manifest --> Loader[Restart and runtime loader]
    Loader --> Dashboard[Read-only dashboard UI]
    Loader --> Adapter[Backend-only FC adapter]
    Adapter --> FC[Finance Core 3.1.1 read APIs]
    Dashboard -->|Journal action| FCUI[Finance Core standalone UI]
    Adapter -->|Selected Workspace and record IDs| Preview[FRAG exact preview]
    Preview --> Harness[Separate approval for each model stage]
```

Plugin adapter contract: `create_router()` returns only `GET` or `HEAD` routes under `/api/plugins/finance-core/`. It should expose `GET /api/plugins/finance-core/scopes` for Workspace and bounded record choices and `GET /api/plugins/finance-core/dashboard` for read-only display. `read_evidence(workspace_id, record_ids)` returns one item per selected ID with `recordId`, `label`, `text`, and `revision`. The host re-reads those records on Run and binds their revisions to approval. The UI bundle exports `mount(element, { apiBase })` and returns an optional cleanup function. The archive must not contain secrets.

## Checks and boundaries

```powershell
npm test
npm run typecheck
npm run build
$runId = [guid]::NewGuid().ToString('N')
$env:PYTEST_ADDOPTS="--basetemp=.tmp/pytest-frag-$runId -p no:cacheprovider"
npm run test:python
```

Tests use synthetic sources and temporary indexes. Backend-only keys and optional FC tokens must never enter browser assets, prompts, logs, tracked files, or error responses. Model answers require human review. FRAG does not connect to trading, banking, payment, or live-market APIs. The [plugin handoff](docs/finance-core-plugin-handoff.md) defines the optional FC integration boundary.

LangGraph runs embedded in FastAPI for Research turn/tool routing, Context Run, and Inference Run orchestration. Preview is an ordinary host function and makes no model call. Host code still owns evidence selection, budgets, approval tokens, provider calls, validation and durable checkpoints. The graphs have no LangGraph checkpointer, external Agent Server, or LangSmith tracing. Research supports complete typed model proposals and optional native Pi tool-call transport; synthetic live GPT and human semantic acceptance remain Phase 5 gates. [Future Agent Server assessment](docs/horizon/horizon-1.md). Archify is an optional project-local Codex skill under the Git-ignored `.agents/skills/archify` directory for development review, not an application dependency.

Thanks to [Archify](https://github.com/tt-a1i/archify) for the diagram tooling. The Archify 2.17 viewers are distributed with their [MIT copyright and permission notice](docs/architecture/ARCHIFY-LICENSE.txt); retain this notice when sharing the viewers separately.
