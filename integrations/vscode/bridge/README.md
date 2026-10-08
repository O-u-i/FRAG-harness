# FRAG Local Host v1.10.3

Private local VSIX for the native VS Code Agents window. Install the matching Host bundle first; this extension does not download or bundle a model runtime.

1. In the dedicated instance's ordinary editor window, open Extensions (`Ctrl+Shift+X`) → `...` → **Install from VSIX...** and choose `frag-bridge-1.10.3.vsix`. The command palette also offers **Extensions: Install from VSIX...**. Confirm **FRAG Local Host 1.10.3** in the extension details.
2. Run **Developer: Reload Window**, then **FRAG: Enable in Agents Window** in that ordinary isolated window. Select **Open Agents** and switch to the window titled **Agents**; reload it if it was already open.
3. **In the Agents window**, press `Ctrl+Shift+P` → **FRAG: Start Project Host**. In **Choose FRAG evidence project**, select the local folder containing your intended evidence and click **Bind project**. Start requires the native Remote Host settings registered in Agents; the ordinary Welcome/editor window fails before launching a process.
4. In Agents, click **New / Ctrl+N**, then the folder-name button above the composer: **Remote → FRAG · project ID → Folders → your project → OK**. Keep the advertised native URI-style path and trust only that intended folder. Confirm FRAG Remote is selected, then select a configured model and send your task. An empty model catalog permits connection checks only; stop before Send.
5. **In Agents**, run **FRAG: Open Review**. Paste the copied URL into the right-hand Browser address bar and choose your FRAG session. Save explicit project excerpts in **Settings**, then use saved configuration in **Workspace** or customize the current run/conversation. Approve each model stage separately; optional Research also needs fresh exact approvals. Back only views saved snapshots.

## Open FRAG before creating a session

For configuration only, stop after setup step 3 and run **FRAG: Open Review** immediately. No **New**, native session selection or **Send** is required. The command copies the running Host's `/review` URL and attempts to open a right-hand Browser tab; paste into its address bar and press `Enter`. If only Files/Changes is visible, open Browser with the right pane's `+` menu. Files and the chat composer are not URL entry points. The port belongs to the current Host, so use the freshly copied URL.

Leave **Select a native session** empty and open **Settings** in the right navigation (Settings icon in narrow panes). Save application preferences and explicit project evidence first; model readiness remains Not checked without a saved native task. Start may enumerate configured models but does not generate a response; opening Review and saving Settings do not call a model or build an index automatically. Create/select a conversation using step 4 only when ready for a task, or run **FRAG: Stop Project Host** when configuration is finished. A native terminal-unavailable notification is expected for this non-coding Host; it is not the way to open Review.

The folder selected by **Bind project** is the evidence Workspace. Keep it separate from the installed Host, VS Code user data and extension state. Opening a local folder with `Ctrl+O` does not select the FRAG Remote provider. Review's **Workspace** page controls evidence/tasks for the bound project; it does not bind another folder. To change projects, stop the owned Host in Agents, start again with the new folder, then select that new FRAG Remote project.

FRAG is a selected-evidence conversation agent. It has no native edit, terminal, coding-tool, MCP, Skills or Hooks bridge. Native Customizations remains VS Code's surface; it does not automatically grant FRAG those capabilities.

Use a dedicated VS Code 1.140.0 Windows instance with separate `--user-data-dir` and `--extensions-dir` directories. Its internal Agents Profile shares that instance's Default settings/models/extensions; `--agents --profile FRAG` does not select a named editor Profile. Install this VSIX into the dedicated instance without `--profile`, enable it from the ordinary isolated window, then reload Agents. The native **Open Agents** action preserves the instance. **Extensions: Show Installed Extensions** is unavailable in Agents; use the isolated ordinary window or CLI. See the source checkout's `integrations/vscode/README.md` for complete installation commands.

The PowerShell alternative below targets the same dedicated instance. Replace the package-directory placeholder with the actual absolute VSIX directory; retain your existing dedicated directories on upgrade.

```powershell
$fragInstance = Join-Path $env:LOCALAPPDATA 'FRAG\vscode-v110-human'
$fragVsix = '<absolute-package-directory>\frag-bridge-1.10.3.vsix'
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --install-extension $fragVsix
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --list-extensions --show-versions | Select-String '^frag-local\.frag-bridge@'
```

Expect `frag-local.frag-bridge@1.10.3`, then reload the ordinary and Agents windows. Installing the VSIX and running the Host ZIP installer are separate operations. Both components must be **1.10.3** before Start; a **1.10.0** extension rejects the new Host's health version. See [VS Code's VSIX installation instructions](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#install-from-a-vsix).

For an already configured instance with matching components, skip reinstalling and enabling again. Preserve the existing provider configuration and credentials, then open its Agents window directly:

```powershell
$fragInstance = Join-Path $env:LOCALAPPDATA 'FRAG\vscode-v110-human'
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --agents
```

**Open User Settings (JSON)** verifies saved paths/settings, not a running Host or native setting registration. If Start reports `This window has no registered chat.remoteAgentHosts setting`, open the same instance's Agents window and retry there; adding the key again in the ordinary editor cannot register that capability. If Agents still reports it, check instance directories and extension version, reload Agents and recheck the supported VS Code build. If a matching Remote Host is already registered, inspect its connection before starting a duplicate.

Model setup belongs to **Chat: Manage Language Models** in that dedicated Agents window. **Chat: Open Language Models (JSON)** opens `<dedicated-user-data>/User/chatLanguageModels.json`. Set `frag.modelConfigFile` explicitly to that absolute path. Empty, missing, linked or different Profile paths fail before any process starts. No default-profile configuration is guessed or copied. Save `[]` explicitly for a model-free installation check; it exposes no models. FRAG reads the bound file locally only to bind changes and report saved `settings[modelId].reasoningEffort`; raw keys and URLs are never copied to Host storage. There is no FRAG effort override picker. Unbound models are excluded; ambiguous registrations fail closed.

v1.10.3 accepts native provisional session creation before model selection. Native Send requires an explicit currently configured model, saves its ID and makes zero model calls. It does not reuse a saved model when Send omits the selection. Missing IDs, stale selections and unavailable catalogs have distinct errors; invalid IDs, effort overrides and changed approval bindings remain rejected.

The model management page can list the supplier (for example MirrorCoding) and **Frag** with the same model name. Frag is the running Host's bridge registration over the dedicated bound configuration, not a second JSON provider or key. **FRAG: Stop Project Host** withdraws those entries and leaves the supplier configuration and project state intact. The ordinary VS Code instance's model file is separate.

Upgrade Host and VSIX together: Stop, initialize the v1.10.3 Host in a new directory, update `frag.hostInstallation`, install this VSIX into the existing dedicated instance, then reload Agents. Keep the dedicated instance directories and explicit model-file binding. Source changes do not patch an old installed Host.

Start requires registered native Remote Host settings in the executing window. The ordinary editor fails early with a specific prompt. Partial registration failures close the owned Host/bridge and attempt to remove only that exact name/address; other Hosts are preserved. Cleanup cannot hide the original failure, and an incomplete owned cleanup can be retried with **FRAG: Stop Project Host**. Start/Stop are serialized and idempotent. Closing the owner window stops its owned process; crashes can leave stale state for manual inspection.

The stable `vscode.lm` API receives exactly the previewed user messages and `modelOptions.max_tokens`. VS Code/provider code may add HTTP fields or retry internally. Final HTTP body, provider retries, usage and relay-side effort execution remain unknown. Configuration changes require a new preview. FRAG performs zero automatic retries.

One extension instance owns one bound Host. Stop it explicitly before selecting another project. Separate project state lives under this extension's local global storage, keyed by canonical project path. Never place it in project Git.

Application settings: optional `frag.hostInstallation` for the initialized v1.10.3 directory, and required `frag.modelConfigFile` for the dedicated Agents instance. No backend `.env` or Pi configuration is used by this route. Use a local trusted Windows folder. Recheck Agents discovery and model settings after VS Code updates.
