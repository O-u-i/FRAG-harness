# VS Code setup · FRAG 1.11.0

Use the **main VS Code window, native Local Agent**. Keep working native model/provider configuration; do not launch a FRAG Remote Host or replace the model manager.

## Installation

Extract `frag-host-1.11.0.zip` and run its `install-host.ps1` with Python 3.12 and `uv` available. The installer creates a new versioned directory, never overwriting old installations. `uv sync --frozen` initializes locked dependencies; Python/wheels are not bundled.

Install matching `frag-bridge-1.11.0.vsix` using **Extensions: Install from VSIX**. Open one trusted local folder. Set `frag.hostInstallation` if needed; default installation is `%LOCALAPPDATA%/FRAG/host/1.11.0`.

Run **FRAG: Open Settings**, approve a directory/exclusions, save, then explicitly **Build / Refresh index**. Opening a project never automatically indexes or sends evidence. Enable `frag_search`, `frag_read` and optional `frag_fc_read` in the native tools picker. Source ID `kb` is the default; mention other Settings IDs explicitly.

## Upgrade from 1.10.x

1. Stop the old FRAG Host and dedicated Agents window.
2. Install matching 1.11.0 Host/VSIX. A newer VSIX cannot replace an explicit old `frag.hostInstallation`: point it to the new directory and reload VS Code.
3. Remove obsolete FRAG entries from the old window's `chat.remoteAgentHosts` yourself, if present. FRAG never silently edits those settings or deletes old installed packages.
4. Use the same workspace and extension ID `frag-local.frag-bridge` to retain project storage. Legacy Runs/Memory are read-only. Reapprove directories/Memory and build new indexes; old file selections do not grant directory access.
5. Keep existing native model credentials/configuration. There is no new FRAG model key or model bridge to configure.

Back up unique private state before upgrading. **FRAG: Open Private State Folder** locates it. Different user-data profiles have separate storage; no automatic cross-profile migration exists. Keep backups/keys/real evidence outside Git.

## Daily use and troubleshooting

Ask the native Agent to use evidence when useful; tool choice is not a Send hook. Refresh changed sources manually. Inspect exact finalized packs in Runs. Write/edit/review/promote Memory yourself, then pin its active version in Settings; edits invalidate old pins.

**FRAG: Stop Evidence Backend** stops this window's owned process only. No tool calls are replayed. Dashboard/writes use **FRAG: Open Finance Core UI**; set `frag.financeCoreUI` to the standalone credential-free loopback URL.

| Symptom | Check |
| --- | --- |
| Tools absent | Matching VSIX, main Local Agent mode, tools enabled, trusted local folder. |
| Startup failure | Exact Host/VSIX match; initialized installation; installation/state/workspace separate and unlinked; no second owner of the project database. |
| `INDEX_NOT_BUILT` | Save source approval and explicitly Build / Refresh. |
| `INDEX_STALE_REFRESH_REQUIRED` | Review changed/added/deleted files and refresh. |
| `POLICY_REJECTED` | Disabled source, wider read than Search returned, or stale/inapplicable/conflicted Memory pin. |
| Tool token budget too small | Reduce selected Memory/evidence or use sufficient native budget; Memory is not silently discarded. |
| Responses fails on a second turn, including chat without FRAG | Diagnose the native provider's continuation support; see the stateless configuration below. Reindexing or reinstalling FRAG cannot fix this. |
| Legacy Run cannot continue | Expected: old runners are removed. Start new native work. |
| FC unavailable | Official pinned reader, private `fc.env`, compatible live API and enabled finance-core source; restart after artifact/config changes. |

### Responses endpoints without reliable server-side continuation

If an endpoint rejects `previous_response_id` (for example, `continuation_unavailable`), VS Code supports a native **model-level** setting in the active instance's `chatLanguageModels.json`:

```json
"zeroDataRetentionEnabled": true
```

Add this property to the affected model object through **Chat: Manage Language Models**. Keep its existing `apiType: "responses"`, endpoint URL and secure API-key input reference. VS Code then sends complete history with `store: false`, rather than depending on a stored response ID. Verify ordinary multi-turn chat first, then a tool call and its model continuation; do not change API protocols speculatively. Reload the window if the model configuration has not refreshed. Existing failed requests are not automatically replayed.

This is a client request-mode setting, **not evidence that a third-party endpoint guarantees zero data retention**. Complete history can increase input tokens and cost; it still goes to the configured provider. Use it only after diagnosing continuation incompatibility. [VS Code configuration reference](https://code.visualstudio.com/docs/agent-customization/language-models#model-configuration-reference).

No tool success implies final factual/citation acceptance. [Core README](../../README.md).
