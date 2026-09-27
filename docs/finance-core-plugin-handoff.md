# Finance Core plugin handoff

The FRAG host and synthetic package are implemented in this repository. Finance Core has produced a local optional v1.0.0 archive with SHA-256 `d9faa77f88d414b75f3db21811567f1e5a8a342c52327a54c50d30e3e41faf25`. FRAG verified and installed that archive against plugin protocol 1 and FC API 3.1.1. Host and adapter checks use synthetic FC responses; live FC and real Vault integration remain a separate acceptance gate.

The original Finance Core production handoff is retained below as the artifact contract.

```text
READ_ONLY first: inspect Finance Core 3.1.1, its AGENTS.md, released /api/v3 contracts, Demo UI, and release process. Do not edit FRAG.

After this FC task receives its own writable scope and IMPLEMENT_APPROVED, create an optional, versioned FRAG-harness plugin release artifact in the Finance Core repository. Keep FC domain, application, API, database, and standalone UI independently runnable; no FC runtime module may import FRAG. Package a read-only dashboard adapter, bounded read-only Workspace record-source adapter, frontend bundle, and FRAG plugin manifest. Provide SHA-256 for the archive and declare compatible FRAG plugin protocol and FC API versions. Use existing FC 3.1.1 /api/v3/health, Workspace dashboard, and selected-record read contracts; propose an additive versioned endpoint only if those contracts cannot support bounded selection. FRAG Journal actions must open FC's own UI, where FC performs authentication and all writes.

The archive must contain exactly manifest.json, adapter.py, and ui.js at its root. The manifest declares id finance-core, protocolVersion 1, semantic version, minHostVersion 1.0.0, fcApiVersion 3.1.1, and SHA-256 hashes in files for ui.js and adapter.py. adapter.py exports create_router() with GET/HEAD routes only under /api/plugins/finance-core/, including GET dashboard and GET scopes; it also exports read_evidence(workspace_id, record_ids). That function returns exactly one dict per requested ID with recordId, label, text, and revision, and refuses invalid Workspace scope or more than ten IDs. ui.js exports mount(element, { apiBase }) and renders a read-only dashboard with an action opening FC's own UI for Journal changes. FC credentials remain backend-only.

Test installation artifact integrity, compatibility failure, Workspace isolation, bounded reads, dashboard values, disabled/unavailable FC behavior, and absence of finance credentials in browser assets. Use synthetic fixtures only. Do not access real Vault data, copy FC SQLite, edit FRAG, commit, push, tag, or publish. Return the exact archive contract, test results, diff, and required compatible versions for FRAG integration.
```

Cross-repo impact: NONE. Contract change: NONE. Other repo status: NOT_TOUCHED. Required compatible version: FRAG host >=1.0.0, plugin protocol 1, and FC API 3.1.1. The local archive is installed, while live FC acceptance is pending.
