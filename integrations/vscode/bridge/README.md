# FRAG Local Host v1.10.1

Private local VSIX for the native VS Code Agents window. Install the matching Host bundle first; this extension does not download or bundle a model runtime.

1. Install the VSIX with **Extensions: Install from VSIX**.
2. Run **FRAG: Enable in Agents Window** in regular VS Code, then reload the Agents window.
3. Run **FRAG: Start Project Host**, explicitly choose your evidence project folder.
4. In Agents, click **New / Ctrl+N**, then the folder-name button above the composer: **Remote → FRAG · project ID → Folders → your project**. Select a model and send your task.
5. Run **FRAG: Open Review**. Paste the copied URL into the right-hand Browser address bar and choose your FRAG session. Select excerpts and approve each stage separately.

FRAG is a selected-evidence conversation agent. It has no native edit, terminal, coding-tool, MCP, Skills or Hooks bridge. Native Customizations remains VS Code's surface; it does not automatically grant FRAG those capabilities.

Use a dedicated VS Code 1.140.0 Windows instance with separate `--user-data-dir` and `--extensions-dir` directories. Its internal Agents Profile shares that instance's Default settings/models/extensions; `--agents --profile FRAG` does not select a named editor Profile. Install this VSIX into the dedicated instance without `--profile`, enable it from the ordinary isolated window, then reload Agents. The native **Open Agents** action preserves the instance. **Extensions: Show Installed Extensions** is unavailable in Agents; use the isolated ordinary window or CLI. See the source checkout's `integrations/vscode/README.md` for complete installation commands.

Model setup belongs to **Chat: Manage Language Models** in that dedicated Agents window. **Chat: Open Language Models (JSON)** opens `<dedicated-user-data>/User/chatLanguageModels.json`. Set `frag.modelConfigFile` explicitly to that absolute path. Empty, missing, linked or different Profile paths fail before any process starts. No default-profile configuration is guessed or copied. Save `[]` explicitly for a model-free installation check; it exposes no models. FRAG reads the bound file locally only to bind changes and report saved `settings[modelId].reasoningEffort`; raw keys and URLs are never copied to Host storage. There is no FRAG effort override picker. Unbound models are excluded; ambiguous registrations fail closed.

v1.10.1 accepts native provisional session creation before model selection. Native Send requires an explicit currently configured model, saves its ID and makes zero model calls. It does not reuse a saved model when Send omits the selection. Missing IDs, stale selections and unavailable catalogs have distinct errors; invalid IDs, effort overrides and changed approval bindings remain rejected.

The model management page can list the supplier (for example MirrorCoding) and **Frag** with the same model name. Frag is the running Host's bridge registration over the dedicated bound configuration, not a second JSON provider or key. **FRAG: Stop Project Host** withdraws those entries and leaves the supplier configuration and project state intact. The ordinary VS Code instance's model file is separate.

Upgrade Host and VSIX together: Stop, initialize the v1.10.1 Host in a new directory, update `frag.hostInstallation`, install this VSIX into the existing dedicated instance, then reload Agents. Keep the dedicated instance directories and explicit model-file binding. Source changes do not patch an old installed Host.

Start requires registered native Remote Host settings in the executing window. The ordinary editor fails early with a specific prompt. Partial registration failures close the owned Host/bridge and attempt to remove only that exact name/address; other Hosts are preserved. Cleanup cannot hide the original failure, and an incomplete owned cleanup can be retried with **FRAG: Stop Project Host**. Start/Stop are serialized and idempotent. Closing the owner window stops its owned process; crashes can leave stale state for manual inspection.

The stable `vscode.lm` API receives exactly the previewed user messages and `modelOptions.max_tokens`. VS Code/provider code may add HTTP fields or retry internally. Final HTTP body, provider retries, usage and relay-side effort execution remain unknown. Configuration changes require a new preview. FRAG performs zero automatic retries.

One extension instance owns one bound Host. Stop it explicitly before selecting another project. Separate project state lives under this extension's local global storage, keyed by canonical project path. Never place it in project Git.

Application settings: optional `frag.hostInstallation` for the initialized v1.10.1 directory, and required `frag.modelConfigFile` for the dedicated Agents instance. No backend `.env` or Pi configuration is used by this route. Use a local trusted Windows folder. Recheck Agents discovery and model settings after VS Code updates.
