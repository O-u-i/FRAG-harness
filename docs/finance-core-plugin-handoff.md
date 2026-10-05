# Finance Core plugin handoff

Phase 7 adds a generic read-only evidence interface while preserving the original Finance Core plugin protocol. FRAG owns host policy, registries, CLI, evaluation, model providers, common plugin interfaces and integration acceptance. Finance Core owns the authoritative plugin source, financial entities, deterministic calculations, storage, authentication, released HTTP APIs and standalone UI. FC remains independently runnable without FRAG or model providers.

## Compatibility and authoritative artifact

| Item | Version or path |
| --- | --- |
| FRAG host | 1.8.0 or later |
| FC product | 3.2.0 |
| FC released API | 3.1.1 |
| FC plugin | 1.1.0, protocol 2 |
| Capability | `evidence.read` |
| Authoritative FC source | `plugins/finance-core/adapter.py`, `manifest.json`, `ui.js` in the FC repository |
| FC artifact builder | `tools/build_frag_plugin.py` in the FC repository |
| Current FC archive | `docs/release/finance-core-frag-plugin-v1.1.0.zip` in the FC repository |
| Current archive SHA-256 | `a96d5d2c4c8e4c8a7232db4be825925d37fb80052e74f6eab450744c62ccfacb` |

The current archive contains exactly `manifest.json`, `adapter.py` and `ui.js`. The manifest declares `name: Finance Core`, the versions above and SHA-256 hashes for both code files. FRAG consumes a pinned build artifact and does not maintain a second editable FC adapter. Product, API, database and plugin versions remain independent.

The original FC `docs/release/finance-core-frag-plugin-v1.0.0.zip` remains byte-identical at SHA-256 `79918f940b29dd6def5a3702bf043719eebbe0a9ece28da67f0d806a0428a6bd`. It uses protocol 1 and minimum host 1.0.0. The protocol 2 adapter retains the legacy `read_evidence(workspace_id, record_ids)` hook and the existing read-only UI routes. See [Plugin protocol](plugin-protocol.md) for host requirements.

## Selected evidence and configuration binding

Protocol 2 exposes `list_scopes(scope_id=None)`, `read_evidence_request(request)` and `source_revision()`. Scope discovery returns `{"scopes": [...]}` with scope `id`, `label` and `records`; each record has `id` and `label`. An optional scope ID restricts discovery to one configured, active Workspace.

The evidence request contains exactly `protocolVersion: 2`, `pluginId: finance-core`, `scopeId` and `recordIds`. The response contains exactly `protocolVersion`, `pluginId`, `scopeId` and `records`, preserving the requested plugin, scope and record order. Each record contains exactly `recordId`, `label`, `text` and `revision`. Reads accept one to ten distinct configured IDs and use only released single-record HTTP contracts. The record revision hashes canonical FC record JSON; it does not establish factual accuracy or complete evidence coverage.

`source_revision()` returns a lowercase 64-hex SHA-256 of canonical JSON containing `apiUrl` and `recordsJson`. `apiUrl` is `FINANCE_CORE_PLUGIN_API_URL`, defaulting to `http://127.0.0.1:8788`, with trailing slashes removed. `recordsJson` is the exact `FINANCE_CORE_PLUGIN_RECORDS_JSON` string, defaulting to `{}`. The hook requires no credentials or HTTP. It excludes read tokens, authentication headers and the standalone UI URL, and returns no descriptor values.

FRAG 1.8.0 pins this configuration revision when loading the plugin and checks it before and after reads. Source identities and parser versions bind it for both protocols; protocol 1 uses the host's compatible FC configuration binding. Supplier or candidate-list changes therefore invalidate old previews and recovery, even if Workspace IDs and record content match. Restart FRAG after configuration changes and select sources again for a fresh preview and approval.

Existing protocol 1 runtime memories with unqualified source identities remain visible in history. They are not automatically recommended or injected under FRAG 1.8.0's supplier-bound identities, including when continuing to use the original protocol 1 archive. Reusing a lesson requires a new candidate from the current source and human review/promotion; historical memory is not silently rebound.

FC reads remain fixed and outside the Research tool loop. The backend uses a Workspace-scoped `ledger:read` token and loopback HTTP. The plugin reads health, accessible Workspaces, dashboard and configured single records; it does not scan entire Journals, open FC SQLite or calculate financial values. Journal changes open FC's standalone UI, where FC authenticates and performs every write.

## Verification and delivery state

FC's released-contract baseline passed 12 synthetic tests before plugin changes. The final FC plugin passed 29 synthetic tests, including actual released API handlers with a read-only token, strict request rejection, Workspace selection, configuration changes with identical content, credential exclusion, artifact integrity and unchanged legacy ZIP/UI. FC product-version and published OpenAPI checks passed at product 3.2.0/API 3.1.1. The existing Starlette TestClient/httpx deprecation warning remains; no dependency was added.

These FC changes remain uncommitted. FRAG host integration and full-suite verification are reported separately at Phase 7 delivery. Live FC and real Vault acceptance remain pending; this handoff records no installed or live-runtime state. Git staging, commits, pushes, tags and publication remain manual user decisions.

## Future FC task prompt

```text
READ_ONLY first: inspect the current FC checkout, its applicable AGENTS.md, product/API/plugin versions, released /api/v3 contracts and plugin artifact checks. Classify ownership as FRAG_ONLY, FC_ONLY or BOTH. Do not edit FRAG from the FC task. The prompt itself grants no implementation authority.

Before implementation, confirm the user's exact task authorization and writable scope. A plugin-only task may name plugins/finance-core/adapter.py, manifest.json, tools/build_frag_plugin.py, backend/tests/test_frag_plugin_artifact.py and docs/md/02-frag-finance-core-plugin.md. Any ui.js change must be separately named. Name one exact new versioned archive path and its exact .gitignore exception; preserve already handed-off archives. Rule changes must explicitly name the ignored AGENTS.md and preserve unrelated rules. Do not modify financial domain, calculation, storage, authentication or API implementation under plugin-only authority.

Current compatibility is FRAG >=1.8.0, FC product 3.2.0, released API 3.1.1 and plugin 1.1.0/protocol 2; verify it rather than assuming it remains current. Preserve protocol 1 compatibility. FC contract and synthetic tests precede plugin packaging and FRAG integration. Financial/API changes require a separate FC-owned task and released contract before host integration.

Use only GET /api/v3/health, GET /api/v3/workspaces, GET /api/v3/workspaces/{workspaceId}/dashboard, GET /api/v3/workspaces/{workspaceId}/journal-entries/{entryId} and GET /api/v3/workspaces/{workspaceId}/journal-entry-drafts/{draftId} for the current adapter. Keep selected Workspace/record scope, exact generic envelopes, canonical record revisions and nonsecret source_revision binding. Preserve FC-provided Decimal strings; do not recalculate financial values in the adapter or FRAG. Journal writes remain in FC's standalone UI.

Use synthetic fixtures, MockTransport or temporary FC API handlers only. Verify released contracts, Workspace/token isolation, bounded selected reads, malformed and extra fields, source-configuration changes with identical record data, missing credentials, unavailable/incompatible FC, archive and source hashes, protocol 1 preservation and browser credential exclusion. Never access real Vault data, read/copy FC SQLite, expose secrets or adopt a dependency without its license decision. Do not commit/push/tag/publish.

Return the exact changed paths, compatible versions, contract classification, archive SHA-256, actual checks and remaining limits, reviewed Git/ignore/staged state, proposed English commit message and a complete FRAG integration prompt. FRAG leads host interfaces and acceptance; FC retains the authoritative plugin source and all financial ownership.
```

```text
Cross-repo impact: BOTH_REQUIRED
Contract change: ADDITIVE
Other repo status: UPDATED
Required compatible version: FRAG >=1.8.0; FC product 3.2.0/API 3.1.1; FC plugin 1.1.0/protocol 2. Original plugin 1.0.0/protocol 1 retained.
Reason: Generic read-only evidence integration and ownership handoff; FC changes are updated and uncommitted.
Prompt for the other repo: Use the scoped future FC task prompt above, with current user authorization and exact paths.
```
