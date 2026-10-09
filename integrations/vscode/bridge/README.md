# FRAG Local Host v1.10.4

**This VSIX requires Host 1.10.4. It does not install or upgrade the Host.** The matching Host ZIP ships the complete installation guide as `resources/install.md`.

## Upgrade an existing instance

1. In **Agents**, run **FRAG: Stop Project Host**. Skip if no Host is running.
2. Extract **`frag-host-1.10.4.zip`** and run its `install-host.ps1` with PowerShell 7. The default destination is `%LOCALAPPDATA%\FRAG\host\1.10.4`.
3. Set **frag.hostInstallation** to that initialized Host's expanded absolute path. A saved older path is not changed by installing this VSIX.
4. Verify **FRAG Local Host 1.10.4** in the dedicated ordinary editor's Extensions view, then reload both the ordinary editor and Agents.

Keep the old installation, project state, instance directories, `frag.modelConfigFile`, providers and credentials. **Deleting Remote addresses does not upgrade the Host.**

## First use

Use a dedicated instance with separate `--user-data-dir` and `--extensions-dir`. Do not use a named `--profile`: Agents shares this instance's Default resources.

In its **ordinary editor**: install this VSIX → **FRAG: Enable in Agents Window** → **Open Agents**. Install/inspect extensions in that ordinary window; run Start/Stop in the same instance's **Agents** window.

## Daily use

1. **FRAG: Start Project Host** → select the evidence folder → **Bind project**. Program, evidence and state directories must be separate.
2. **FRAG: Open Review** → paste the fresh URL into the right-hand **Browser address bar** → `Enter`. Do not reuse old ports.
3. Configure evidence in Review **Settings**; a conversation is not required yet.
4. When ready: **New → folder-name button → Remote → FRAG → Folders → your project**. Select a configured model and send text without native Context attachments.
5. Review and approve exact **Context** and **Inference** requests separately. Stop the owned Host when finished.

If Browser pauses due to a notification, close that notification and press `Ctrl+R`. An ordinary local folder in Files is not a FRAG Remote selection.

## Model binding and limits

- In Agents, use **Chat: Manage Language Models** and **Chat: Open Language Models (JSON)**. Bind **frag.modelConfigFile** explicitly to this dedicated instance's `User/chatLanguageModels.json`.
- Preserve existing providers. Use `[]` only for a new empty installation test; it cannot accept model-bound tasks. No Profile, key or default-model fallback is copied.
- Start can enumerate models; Send saves a task without generation. Each Research/Context/Inference dispatch requires its own fresh exact approval.
- FRAG does not expose native filesystem, editing or terminal operations or import Customizations' MCP/Skills/Hooks. Reviewed memory is background, not evidence or permission.

State stays in extension global storage, not the evidence folder. Stop removes only the owned process/registration. Restart clears approvals; unknown external outcomes are never resent automatically. Supplier HTTP fields, retries, usage, billing and response quality remain separate verification boundaries.
