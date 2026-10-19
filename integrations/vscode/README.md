# VS Code setup · FRAG 1.13.4

Use the **main VS Code window, native Local Agent**. Keep working native model/provider configuration; do not launch a FRAG Remote Host or replace the model manager.

## Installation

Follow [First install](../../README.md#first-install) for the PowerShell 7 commands, matching packages, native model check and source authorization. Extract `frag-host-1.13.4.zip` and run its `install-host.ps1` with Python 3.12 and `uv` available. The installer creates a new versioned directory, never overwriting old installations. `uv sync --frozen` initializes locked dependencies; Python/wheels are not bundled.

Install matching `frag-bridge-1.13.4.vsix` using **Extensions: Install from VSIX**. Open one trusted local folder. Set `frag.hostInstallation` if needed; default installation is `%LOCALAPPDATA%/FRAG/host/1.13.4`.

Run **FRAG: Open Settings**, approve a directory/exclusions, save, then explicitly **Build / Refresh index**. Opening a project never automatically indexes or sends evidence. Enable `frag_search`, `frag_read` and optional `frag_fc_read` in the native tools picker. Source ID `kb` is the default; mention other Settings IDs explicitly.

## Optional Finance Core

The Host bundles the exact official reader; first start prepares it without granting source access. Use **FC Settings → Connect FRAG → Copy FRAG configuration**, then `Ctrl+Shift+P` → `FRAG: Connect Finance Core`. The exact backend-only `fc.env` opens in Notepad. Paste/save, then **Check connection**, select the smaller FRAG subset and **Save authorization** in FRAG Settings. No separate reader install, Workspace-ID lookup or JSON editing. [Connection and factual-Run guide](../../docs/finance-core-plugin-handoff.md).

## Upgrade from 1.11.x or later native-tool versions

Use the [upgrade checklist](../../README.md#update): stop the owned backend, preserve private state, install the exact matching Host/VSIX, review any explicit `frag.hostInstallation`, and reload the same instance/profile. A native-tool upgrade does not require a new model provider or API key. Existing approved sources stay subject to current revision/index/Memory checks; do not blindly erase and recreate them. Verify ordinary chat before testing evidence tools.

## Upgrade from 1.10.x

1. Stop the old FRAG Host and dedicated Agents window.
2. Install matching 1.13.4 Host/VSIX. A newer VSIX cannot replace an explicit old `frag.hostInstallation`: point it to the new directory and reload VS Code.
3. Remove obsolete FRAG entries from the old window's `chat.remoteAgentHosts` yourself, if present. FRAG never silently edits those settings or deletes old installed packages.
4. Use the same workspace and extension ID `frag-local.frag-bridge` to retain project storage. Legacy Runs/Memory are read-only. Reapprove directories/Memory and build new indexes; old file selections do not grant directory access.
5. Keep existing native model credentials/configuration. There is no new FRAG model key or model bridge to configure.

Back up unique private state before upgrading. **FRAG: Open Private State Folder** locates it. Different user-data profiles have separate storage; no automatic cross-profile migration exists. Keep backups/keys/real evidence outside Git.

## Daily use and troubleshooting

Use [Daily use and safety](../../README.md#daily-use-and-safety); there is no daily installation script. Ask the native Agent to use evidence when useful; tool choice is not a Send hook. Refresh changed sources manually. Inspect exact finalized packs in Runs. Write/edit/review/promote Memory yourself, then pin its active version in Settings; edits invalidate old pins.

**FRAG: Stop Evidence Backend** stops this window's owned process only. No tool calls are replayed. Dashboard/writes use **FRAG: Open Finance Core UI**; set `frag.financeCoreUI` to the standalone credential-free loopback URL.

| Symptom | Check |
| --- | --- |
| `The selected model 'copilot/auto' is not available` | Select an actual available native model explicitly. Copilot Auto and a configured BYOK endpoint are different selections; FRAG does not supply Auto. |
| `401` / `Invalid token` in ordinary chat | Native provider authentication was rejected. Check the active instance/profile and provider details through the native UI below. After a key update, reload the actual failed main window, not just a separate diagnostic window; do not reinstall FRAG, erase generated settings or treat GitHub sign-in as the BYOK fix. |
| `Set BYOK utility models` / `copilot-utility-small` unavailable | Configure optional native utility models separately after the main model works; this does not fix a main-model `401`. |
| Extra `agent-host-copilotcli` settings or JSON warnings | See the native configuration explanation below. A saved effort preference is not itself an endpoint/authentication error; inspect each actual diagnostic rather than deleting configuration wholesale. |
| Tools absent | Matching VSIX, main Local Agent mode, tools enabled, trusted local folder. |
| Startup failure | Exact Host/VSIX match; initialized installation; installation/state/workspace separate and unlinked; no second owner of the project database. |
| `NOT_FOUND` from `frag_search` | The requested source ID has no saved profile in this project's private state; omitted `sourceId` defaults to `kb`. Open Settings, enter the intended directory/exclusions, explicitly approve and **Save authorization**, then **Build / Refresh index**. A new-source form displaying `kb` is not a saved source. If using another saved ID, name it explicitly in the request. |
| `INDEX_NOT_BUILT` | Save source approval and explicitly Build / Refresh. |
| `INDEX_STALE_REFRESH_REQUIRED` | Review changed/added/deleted files and refresh. |
| `POLICY_REJECTED` | Disabled source, wider read than Search returned, or stale/inapplicable/conflicted Memory pin. |
| `TOOL_TOKEN_BUDGET_INVALID` | The native tool budget is invalid, not merely too small. Check the selected model's input/context and output limits [below](#native-model-token-limits), then reload the actual main window. Do not change `topK`, reauthorize/reindex sources, rotate keys or bypass budget validation to repair invalid metadata. |
| Tool token budget too small | Reduce selected Memory/evidence or use sufficient native budget; Memory is not silently discarded. |
| Responses replies once, then returns `400` / `invalid_request` | First-turn authentication does not establish continuation support. A generic `400` is inconclusive: distinguish a plain second turn from a tool request, then see the stateless diagnosis below. Do not reinstall or reindex FRAG to repair a native request rejection. |
| Legacy Run cannot continue | Expected: old runners are removed. Start new native work. |
| FC unavailable | Use Connect Finance Core, then Check connection. Verify FC API 3.10.0, the single-Vault read-only grant and explicitly saved FRAG subset. Checking pauses old access; it does not read reports. Nonprivate configuration refuses rather than being repaired automatically. |

### Native model configuration and errors

**Who writes `chatLanguageModels.json`?** VS Code owns it. Its native model picker persists non-default options in `settings` and can create a settings-only provider group containing `name`, `vendor` and a model-ID map. This behavior is present in the verified VS Code 1.141.0 build; see [the matching native implementation](https://github.com/microsoft/vscode/blob/2a59476c9bfcb90b3ddc372c36762471b7dfad1c/src/vs/workbench/contrib/chat/common/languageModels.ts#L1520-L1592). It does not require someone to have typed that JSON manually.

`vendor: "agent-host-copilotcli"` identifies the native Copilot Agent Host provider, not a FRAG model bridge. A `thinkingLevel` preference there is distinct from the Local Agent Custom Endpoint provider's `reasoningEffort` preference, even when the model-ID text names the same endpoint model. Do not merge or delete these groups as a speculative authentication fix. This identifies a native writer capable of producing that shape, not the exact historical action that created any particular entry.

**Diagnose the main model without FRAG first.** In a new Local Agent chat with no private context and FRAG tools disabled, select the intended model explicitly and try one short greeting. If authentication fails:

1. Open **Chat: Manage Language Models** in that same instance/profile. Check the existing provider's endpoint/API type/model ID against the setup that works elsewhere; do not create duplicate providers or copy secrets between profiles.
2. If a key update is needed, open the gear beside the **provider group**, choose **Update API Key**, enter the valid current key in the native secure input, and confirm. **Open in Language Models (JSON)** is a different action; merely opening that file does not update the stored secret. Leave the `${input:...}` reference native-managed rather than replacing it with a literal key.
3. After confirming the key update, run **Developer: Reload Window in the original main project window whose chat failed**. Reloading only the model-manager/diagnostic window, or merely starting another chat, is not the same operation. In that target window, reselect the intended model and send one short greeting. Earlier error messages remain in chat history; judge the new response. If it still fails while the same endpoint/key works elsewhere, stop repeated requests and inspect the active profile, native credential binding and client/provider compatibility using redacted diagnostics. Do not reinstall FRAG, erase provider groups or change API protocols speculatively.

VS Code documents this [provider update flow](https://code.visualstudio.com/docs/agent-customization/language-models#update-model-provider-details). Recovery after a secure key update confirms current authentication, but does not by itself identify whether the previous key was stale or its native binding was wrong.

A `${input:...}` reference is a secure-input reference, not proof that a usable credential is present in this instance or accepted by the server. A remote `401 Invalid token` alone cannot distinguish a missing/wrong/expired credential, endpoint/header mismatch or provider-side rejection; it does not establish user error or a FRAG regression. Never paste a key into chat, request logging, a project file or a Git-tracked example. A stack under the built-in Copilot extension can also be its BYOK response wrapper, not a request to a GitHub-hosted model. Reindexing and the Responses continuation setting below cannot repair authentication.

**Utility models are separate.** Once the main BYOK model works, native Settings can select **Main Agent Model** for `chat.byokUtilityModelDefault` (`"mainAgent"`), or set `chat.utilityModel` / `chat.utilitySmallModel` to suitable available models. Explicit utility selections take precedence. This enables background features such as titles and intent detection; it can send additional requests to your provider and incur cost. FRAG does not change these settings. [Native utility-model choices](https://code.visualstudio.com/docs/agent-customization/language-models#change-the-model-for-utility-tasks).

For JSON warnings, inspect the Problems panel and the active provider's schema; configure required model properties from its actual contract. Do not suppress validation, invent token limits or remove reasoning levels just to clear warnings. Keep verification separate: **ordinary provider chat in the actual target window → FRAG tool round trip → human evidence/answer review**. A successful SDK probe or a fresh development window verifies that test path, not an already-open Local Agent window. Historical/offline acceptance receipts cannot substitute for a current authenticated request in the target window.

### Native model token limits

A greeting can succeed even when the model's token-limit metadata is invalid. Native tool-result sizing also needs a usable input budget. In the verified VS Code 1.141.0 build, an explicitly configured model with missing output limits can produce `NaN` input/context limits; the [matching native limit resolver](https://github.com/microsoft/vscode/blob/2a59476c9bfcb90b3ddc372c36762471b7dfad1c/extensions/copilot/src/extension/byok/common/byokProvider.ts) does not substitute defaults for incomplete explicit capabilities. FRAG rejects an invalid supplied budget before counting tokens or omitting evidence. `NaN` is a computed metadata failure, not a value to enter in JSON.

1. In the affected instance/profile, open **Chat: Manage Language Models** → existing provider group's gear → **Open in Language Models (JSON)**. This is not the key-update action.
2. Inside the affected Custom Endpoint `models` entry, set **positive integer JSON numbers** for `maxInputTokens` and `maxOutputTokens`, using that exact provider/model's published limits. If the provider publishes a total context window instead, use `contextWindow` and `maxOutputTokens`; the window must exceed the output reservation, and VS Code derives the remaining input budget. Do not mistake a total context window for an additional input allowance, guess from a model name, or copy limits from an unrelated example. See the [native configuration reference](https://code.visualstudio.com/docs/agent-customization/language-models#custom-endpoint-configuration-reference).
3. Keep the API type, URL, secure key reference, capabilities and other models unchanged. These limits belong alongside the model's `id`, not in provider `settings` or a separate `agent-host-copilotcli` settings-only group. If limits are undocumented, stop and obtain them from the provider rather than inventing a fallback.
4. Save and **Developer: Reload Window in the original main project window**. Retry one tool request against an approved nonsecret source and inspect its new Run. A finite metadata-only SDK check needs no generation request, but is not proof of delivery in the original window or of the final answer's correctness.

### Responses endpoints without reliable server-side continuation

A successful greeting followed by `400 invalid_request` can be a native Responses continuation compatibility issue, but the generic error alone does not prove it. If needed, compare one short second turn in the same chat with FRAG tools disabled and no private context; a first-turn tool rejection can instead involve tool capabilities/schema. After a failure, refresh Runs: no new Run means no finalized FRAG invocation is recorded, not that retrieval returned no evidence. Avoid repeated paid probes or raw request logging.

When the endpoint rejects `previous_response_id` (for example, `continuation_unavailable`), or a scoped diagnosis supports stateless continuation, VS Code supports this native **model-level** setting:

```json
"zeroDataRetentionEnabled": true
```

1. Open **Chat: Manage Language Models** in the affected instance/profile. Use the existing provider group's gear → **Open in Language Models (JSON)** to open its native `chatLanguageModels.json`; this is not the **Update API Key** action.
2. Add only the property above inside the affected entry in the provider's `models` array, alongside that model's `id` and `url`. Do **not** put it in provider `settings` or the separate `agent-host-copilotcli` settings-only group. Keep the existing Responses API type, endpoint URL, model ID, capabilities, other models and secure API-key reference unchanged.
3. Save, then run **Developer: Reload Window in the original main project window whose request failed**. A new chat or a separately reloaded diagnostic window is not a substitute. Existing failed requests are not automatically replayed.
4. Verify a short ordinary multi-turn exchange, then a tool call and its model continuation using an approved nonsecret test source. Inspect the new Run and its warnings separately from the native final answer. A tool result or local authorization/index hint confirms the tool path was reached, not that the evidence or answer is correct.

With this enabled, the native Responses client sends complete history with `store: false` instead of relying on `previous_response_id`; see [the matching VS Code 1.141.0 implementation](https://github.com/microsoft/vscode/blob/2a59476c9bfcb90b3ddc372c36762471b7dfad1c/extensions/copilot/src/extension/byok/node/openAIEndpoint.ts#L254-L274). Do not change API protocols or disable tool/schema validation speculatively. FRAG never adds this setting automatically.

This is a client request-mode setting, **not evidence that a third-party endpoint guarantees zero data retention**. Complete history can increase input tokens and cost; it still goes to the configured provider. Use it only after diagnosing continuation incompatibility. [VS Code configuration reference](https://code.visualstudio.com/docs/agent-customization/language-models#model-configuration-reference).

No tool success implies final factual/citation acceptance. [Core README](../../README.md).
