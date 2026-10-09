# FRAG in VS Code Agents — Plan E / v1.10.4

**Required pair: `frag-host-1.10.4.zip` + `frag-bridge-1.10.4.vsix`.** A newer VSIX cannot start an older Host. An explicit `frag.hostInstallation` overrides the extension's default path.

| Your situation | Start here |
| --- | --- |
| Existing FRAG installation | [Upgrade](#upgrade-to-v1104) |
| New dedicated instance | [First install](#first-install) |
| Both components already match | [Daily start](#daily-start) |

## Upgrade to v1.10.4

Keep the existing instance, models, credentials and project state. **Do not delete ports, replace model JSON with `[]`, or remove the old Host.**

### 1. Stop the old Host — Agents

`Ctrl+Shift+P` → **FRAG: Stop Project Host**. If no Host is running, continue.

### 2. Install the Host ZIP — external PowerShell 7

Extract **`frag-host-1.10.4.zip`**. Run the installer from that extracted bundle, not the source checkout:

```powershell
$fragBundle = '<absolute-extracted-host-directory>'
pwsh -NoProfile -File "$fragBundle\install-host.ps1"
```

Default destination: `%LOCALAPPDATA%\FRAG\host\1.10.4`.

- Success prints **Host installed:** followed by the destination.
- Existing directories are never overwritten. Skip installation only for a verified, initialized 1.10.4 Host. Otherwise choose a new directory with `-InstallPath`; do not delete an old installation.

### 3. Install the VSIX — dedicated ordinary editor

`Ctrl+Shift+P` → **Extensions: Install from VSIX...** → select **`frag-bridge-1.10.4.vsix`**.

Verify **FRAG Local Host 1.10.4** in Extensions. Already at that exact version? Skip reinstalling the VSIX, but still install the matching Host.

### 4. Set the new Host path — same instance's User settings

Run this in PowerShell and copy its output:

```powershell
Join-Path $env:LOCALAPPDATA 'FRAG\host\1.10.4'
```

In the dedicated ordinary editor: `Ctrl+,` → search **frag.hostInstallation** → paste the full path. If you used a custom `-InstallPath`, paste that actual destination instead.

**Change only this setting.** Preserve `frag.modelConfigFile`, provider configuration, instance directories and other Remote Hosts.

### 5. Reload — both windows

Run **Developer: Reload Window** in the ordinary editor **and** any already-open **Agents** window. Then follow [Daily start](#daily-start).

**Checkpoint:** VSIX **1.10.4** + initialized Host **1.10.4** + `frag.hostInstallation` pointing to that Host. A checkout edit or empty `chat.remoteAgentHosts` does not satisfy this checkpoint.

## First install

### 1. Check prerequisites — external terminal

```powershell
pwsh --version
uv --version
```

Use PowerShell 7 and an approved `uv` installation. Windows PowerShell 5.1 is not the installer environment; FRAG Remote does not provide a terminal.

### 2. Open a dedicated ordinary editor

```powershell
$fragInstance = Join-Path $env:LOCALAPPDATA 'FRAG\vscode-v110-human'
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --new-window
```

Keep these directories on later launches. Do not use a named `--profile`: Agents shares this instance's Default resources.

### 3. Install the pair and set the Host path

Follow steps **2–5** under [Upgrade](#upgrade-to-v1104). They also apply to a new installation.

### 4. Enable FRAG in Agents

In the ordinary editor: **FRAG: Enable in Agents Window** → **Open Agents**. Switch to the window titled **Agents**.

### 5. Bind this instance's model file

In Agents: **Chat: Open Language Models (JSON)** → save the dedicated `User/chatLanguageModels.json`. Configure providers through **Chat: Manage Language Models**.

Set **frag.modelConfigFile** to that file's expanded absolute path in this instance's User settings. Preserve existing providers and keys. Use `[]` only for a new empty, model-free test catalog; it cannot accept model-bound tasks.

[Provider fields and saved effort](MODEL-CONFIGURATION.md). Continue below when the binding is ready.

## Daily start

### 1. Open the same Agents instance

```powershell
$fragInstance = Join-Path $env:LOCALAPPDATA 'FRAG\vscode-v110-human'
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --agents
```

Use your existing paths if they differ. A bare `code` command can open another instance.

### 2. Bind the evidence project

In **Agents**: **FRAG: Start Project Host** → select the evidence folder → **Bind project**. Skip Start if this window already owns the Host.

Choose evidence, not the installed program or its state directory. A local folder in Files is not a selected FRAG Remote project. Review workspace trust only for the intended folder.

### 3. Open Review

**FRAG: Open Review** → paste the copied URL into the right-hand **Browser address bar** → `Enter`.

The port changes between starts: always copy a fresh URL. If Files/Changes is visible, open Browser from the right pane's `+` menu. Do not paste into the composer.

### 4. Configure without a conversation

Leave **Select a native session** empty → **Settings** → save explicit project evidence. No New/Remote selection/Send is required here. Model readiness remains **Not checked** until a task has a selected model.

## Send a task when ready

1. **New / Ctrl+N** → folder-name button above the composer → **Remote → FRAG · project ID → Folders → your project → OK**. Retain the offered native URI-style path.
2. Select a configured model; send a **3–500 character text task** without native Context attachments. Select evidence in Review instead.
3. In Review: choose that session → **Workspace** → **Preview Context** → inspect and approve the exact request. Prepare/approve **Inference** separately, then review the output.

Send saves a task, not a model call. A successful preview creates a Run without dispatching it. Optional Research also needs exact approvals. Saving Settings never indexes or runs a model automatically.

## Troubleshooting

| Symptom | Check / action |
| --- | --- |
| **Could not start during installed Host startup** | Check the upgrade checkpoint: matching versions, initialized Host, actual `frag.hostInstallation`. Keep program, evidence and state separate. Do not clear ports as a repair. |
| Setting still points to an older Host | Change `frag.hostInstallation` after installing the new Host; reload Agents. A VSIX update does not change an explicit saved path. |
| Review/help shows an older FRAG version | Stop the old Host, start the matching pair and copy a fresh URL. The old tab can still target an old process. |
| **Paused due to Notification** | Close the VS Code notification, including the copied-URL notification; press `Ctrl+R` in Browser if needed. |
| **No registered chat.remoteAgentHosts setting** | Run Start in **Agents**, not the ordinary editor. Adding a JSON key cannot register a window capability. |
| FRAG commands are missing | Check this instance's extension version, opt-in, trust and Agents reload. Install/inspect extensions in the ordinary editor. |
| Missing / wrong model file | Bind this dedicated instance's actual `User/chatLanguageModels.json`; do not copy another Profile's credentials. |
| Matching Remote Host already registered | Use Stop in its owner window. After a crash, inspect only the stale owned entry/process before removal; preserve unrelated registrations. |
| No evidence / empty Run history | Save explicit evidence, then preview. Runs shows the waiting task before its first successful preview; it does not fabricate execution. |

If versions and paths match but startup still fails, retain the exact controlled error and inspect the bundle. Do not repeatedly erase settings or models.

## Execution windows and Workspace

| Surface | Responsibility |
| --- | --- |
| Dedicated ordinary editor | Install/inspect VSIX; edit this instance's User settings. |
| Same instance's Agents | Models, Start/Stop, conversation and Browser Review. |
| Review Workspace | Evidence/task controls for the already-bound project; not a folder-binding command. |

## State and verification

Project state stays in extension global storage under `projects/<canonical-path-hash>/`, outside evidence and program directories. Preserve it on upgrade. Stop removes only the owned registration/process; closing its owner window stops that Host. Restart clears approvals, not saved records. Unknown external outcomes never resend automatically.

FRAG is an evidence agent, not a filesystem/editor/terminal agent. VS Code owns Customizations; its MCP, Skills and Hooks are not imported. Reviewed memory is background, not evidence or permission.

Compatibility is scoped: **VS Code 1.140.0 / AHP 0.9.0** is the original baseline; **1.141.0** native creation/Send/Stop was tested separately with synthetic models. Recheck after VS Code updates. Enumeration does not establish authentication, billing or output quality.

[Current verification](REVIEW-REPAIR-VERIFICATION.md) · [Models](MODEL-CONFIGURATION.md) · [Review UI](../../src/agents/README.md) · [Architecture](../../docs/architecture/vscode-migration/architecture.html).

Earlier reports are historical, not current install steps: [v1.10.3](REVIEW-SETTINGS-VERIFICATION.md), [Plan E checks](PLAN-E-VERIFICATION.md), [native adapter history](NATIVE-AGENTS.md).

## Development packaging

From the checkout: `npm run package:agents`. Outputs: ignored `.tmp/packages/frag-host-1.10.4.zip`, `.tmp/packages/frag-bridge-1.10.4.vsix`, `receipt-1.10.4.json`. The Host ships this guide as `resources/install.md`. Installed use needs no source checkout or backend `.env`.
