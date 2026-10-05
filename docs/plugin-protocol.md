# Read-only plugin protocol

FRAG v1.8.0 supports independently installed protocol 2 plugins and the original protocol 1 Finance Core package. A package is trusted backend code, not a sandbox. Registration permits neither model dispatch nor additional source access.

The host catalog is version 2. Use matching FRAG frontend/backend v1.8.0 or later; an older frontend expecting catalog version 1 is not compatible with this catalog. Archive protocol 1 compatibility refers to the original FC package and its selected-read interface.

The archive contains exactly `manifest.json`, `adapter.py` and `ui.js` at its root. The archive is at most 20 MiB; entry limits are 64 KiB, 2 MiB and 5 MiB respectively. Duplicate names, extra files, traversal, links and unsupported manifests fail validation. The installer pins the archive SHA-256 and verifies both source file hashes; the loader executes and serves verified byte snapshots. Activation changes require restart. Every selected read rechecks the package and configuration before and after execution.

Protocol 2 manifest example:

```json
{
  "id": "kb",
  "name": "KB",
  "protocolVersion": 2,
  "version": "1.0.0",
  "minHostVersion": "1.8.0",
  "capabilities": ["evidence.read"],
  "files": {"adapter.py": "<SHA-256>", "ui.js": "<SHA-256>"}
}
```

IDs are lowercase slugs, at most 63 characters. Protocol 2 currently declares minimum host `1.8.0`; protocol 1 keeps `1.0.0`. Finance Core additionally requires `fcApiVersion: "3.1.1"`. Unsupported protocols, versions, capabilities and fields are rejected. The UI exports `mount(element, { apiBase })`, optionally returning a cleanup function. The host derives `apiBase` from that plugin's ID.

The adapter exports four functions:

- `create_router()` returns an `APIRouter`; plugin routes are GET/HEAD only under `/api/plugins/<id>/`. They cannot collide with host evidence discovery or include path parameters, traversal or WebSockets.
- `source_revision()` returns a lowercase SHA-256 of non-sensitive source configuration without reading records or making network calls. KB binds its canonical source root; FC binds its read API URL and configured record allowlist. Credentials and authentication headers are excluded. Changing this configuration requires restart and invalidates prior source bindings.
- `list_scopes(scope_id=None)` returns `{"scopes":[{"id":"...","label":"...","records":[{"id":"...","label":"..."}]}]}`. Discovery is bounded and does not authorize later reading. KB lists file metadata first and parses locators only after an explicit file selection.
- `read_evidence_request(request)` receives and returns the strict envelopes below. It must read only selected records and refuse unavailable scope.

```json
{"protocolVersion":2,"pluginId":"kb","scopeId":"selected.md","recordIds":["section-1"]}
```

```json
{"protocolVersion":2,"pluginId":"kb","scopeId":"selected.md","records":[{"recordId":"section-1","label":"Finding","text":"Selected synthetic evidence.","revision":"<source revision>"}]}
```

The host requires exact plugin and scope equality and exactly one record for each selected ID. It rejects extras, duplicates, missing or unknown IDs, invalid types and structured results larger than 64 KiB. Selection accepts one scope and at most ten distinct record IDs; scope IDs are bounded to 500 characters, record IDs to 128. The host restores requested order and derives evidence/citation IDs itself. A legal citation ID or matching digest does not prove factual truth.

Harness accepts `pluginSelection: {pluginId, scopeId, recordIds}`. Legacy `{pluginId:"finance-core", workspaceId, recordIds}` remains accepted; exactly one non-null scope identifier is allowed. `SourceBinding` contains record revision plus the package and configuration fingerprints. Both protocols' source namespaces include the configuration fingerprint, isolating reviewed memories between sources even when filenames or Workspace IDs match. Historical records remain visible; old unqualified protocol 1 memories require a candidate from the current source and a new human review/promotion before reuse in this host. No automatic memory migration or promotion occurs.

Protocol 1 adapts its existing `read_evidence(workspace_id, record_ids)` and `/scopes` response to this validated boundary. Its Finance Core compatibility bridge also binds non-sensitive read API/allowlist configuration. The official original archive is unchanged. Both protocols retain fresh exact preview and one-use approval for each Context and Inference request. Plugin evidence does not enter Research in this phase.

Host endpoints:

| Endpoint | Purpose |
| --- | --- |
| `GET /api/plugins` | Catalog protocol 2; each entry reports its own package protocol and active capabilities. |
| `GET /api/plugins/<id>/evidence-scopes?scopeId=<selected scope>` | Validated generic discovery; omit the query for candidates. |
| `POST /api/plugin-management/install` | ZIP body, `X-Expected-Sha256` and `X-FRAG-Plugin-Action: install`. |
| `POST /api/plugin-management/state` | `{pluginId, enabled}` with `X-FRAG-Plugin-Action: state`; omitted ID defaults to FC for compatibility. |
| `POST /api/plugin-management/uninstall` | Returns `409 PLUGIN_MANUAL_REMOVAL_REQUIRED`; no files deleted. `X-FRAG-Plugin-Id` identifies the package. |

Disabled or invalid plugins advertise no capability, reader, routes or UI. A state change hides only that package for the rest of the current server session. Installation also leaves the target inactive until restart. Other valid plugins continue operating. Host management accepts local actions only and rejects arbitrary origins.

## Manual removal

No cleanup is required merely because a new version exists or a test left ignored evidence. To remove a particular package:

1. Use its **Disable plugin** control, or run `scripts/install-plugin.ps1 -Disable -PluginId <id>`.
2. Stop FRAG's backend so it holds no loaded plugin.
3. In File Explorer, inspect `<FRAG repository>/.local-plugins/<id>/`. A version directory contains only the three package files; `current.json` selects the version. Review unexpected files before deletion.
4. Manually delete only the selected plugin's directory. Preserve other plugin IDs, `.local-runtime/`, local evidence and `.local-plan-b/`.
5. Restart FRAG and verify that the package is absent/inactive and its UI/scopes routes return 404.

The configured plugin root may differ in tests or custom deployments; resolve the exact root first. Do not issue recursive shell deletion commands. Requesting removal instructions does not disable a package or remove its files automatically.

KB source/build/archive belong to FRAG. FC plugin source/build/archive belong to FC; installed pinned bytes are artifacts. See [FC handoff](finance-core-plugin-handoff.md). No new runtime framework, vector store or plugin dependency installer is introduced.
