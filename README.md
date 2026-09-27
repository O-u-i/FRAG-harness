# FRAG-harness v1.0.0

FRAG-harness is a local application for governed evidence retrieval and two model API stages. It starts with no Finance Core installation, account, token, or database. The Context LLM compresses approved evidence; the Inference LLM produces a cited answer. Selection, redaction, token budgeting, approval, output validation, and citation checks are deterministic host code.

## What runs in the core

The React interface offers Harness, RAG Lab, and Plugins. The FastAPI backend owns local source parsing, exact outbound previews, single-use approval tokens for each model stage, the two model routes, citation validation, and a rebuildable SQLite FTS5 index for a bundled synthetic RAG dataset. Fake model providers work offline. Real model API credentials live only in `backend/.env`.

## Architecture review diagrams

These static SVG exports summarize the current host code. Each has a linked interactive HTML view and an editable Archify JSON specification under `docs/architecture/`. They are review documentation, not runtime telemetry or orchestration.

### Harness

The Harness path assembles only explicitly selected local excerpts or optional, bounded Finance Core records. The host controls redaction, exact outbound previews, approvals, and validation around the two model APIs. [Explore the Harness data flow](docs/architecture/harness/dataflow.html).

![Harness data flow from selected evidence through the Context and Inference gates to human review](docs/architecture/harness/dataflow.svg)

Each stage requires a separate exact-input preview and a single-use approval. The host re-reads evidence and checks the fingerprint before a call; invalid approval stops that stage. [Explore the Harness approval lifecycle](docs/architecture/harness/lifecycle.html).

![Harness lifecycle with separate Context and Inference approval gates and human review](docs/architecture/harness/lifecycle.svg)

### RAG Lab

RAG Lab indexes only the bundled synthetic Markdown file after an explicit Build action. Section chunks enter a separate SQLite FTS5 index; source changes make it stale until a rebuild. Query search ranks keyword matches, and Search and Preview make no model call. [Explore the RAG index and retrieval flow](docs/architecture/rag-lab/dataflow.html).

![RAG Lab flow from explicit synthetic indexing through FTS5 retrieval to an exact Context preview](docs/architecture/rag-lab/dataflow.svg)

The RAG query path needs a ready index and retrieved evidence before Context Run. Its Context and Inference calls have independent one-time approvals; compressed evidence IDs and answer citations are checked before human review. [Explore the RAG query and approval lifecycle](docs/architecture/rag-lab/lifecycle.html).

![RAG Lab lifecycle from a ready-index query through two approvals and citation checks to human review](docs/architecture/rag-lab/lifecycle.svg)

Preview never calls a model. The first Run executes only the Context stage and returns validated compression plus the exact Inference instructions and input JSON for a second approval. Inference Run executes the second stage after approval. Tokens expire after ten minutes, are consumed once, and bind the displayed input to its source or index revision. Changed inputs and reused tokens are rejected. Provider credentials stay in the backend.

## Start locally

Requires Node.js, npm, Python 3.12, and `uv`. From the repository root:

```powershell
npm install
uv sync --project backend --cache-dir .tmp/uv-cache
npm run dev
```

Open `http://localhost:5173`; the backend listens on `http://127.0.0.1:8787`. To configure either model, copy `backend/.env.example` to the Git ignored `backend/.env` and set provider, model, and backend-only credentials. `fake` is the default for both stages. Put supported `.md`, `.txt`, `.html`, `.pdf`, `.docx`, `.csv`, or `.xlsx` files under `local-sources/`; the folder is ignored except for instructions and placeholders. Files are never automatically indexed by the product.

The RAG Lab source is `shared/demo/rag/synthetic-risk-review.md`. It has no embedding or vector retrieval in v1.0.0.

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

LangGraph is installed in the backend development dependency group for isolated orchestration experiments. The FRAG runtime does not import it; a production environment can use `uv sync --project backend --no-dev`. Archify is an optional project-local Codex skill under the Git-ignored `.agents/skills/archify` directory for development review, not an application dependency.

Thanks to [Archify](https://github.com/tt-a1i/archify) for the diagram tooling.
