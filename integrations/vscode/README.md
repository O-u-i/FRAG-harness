# FRAG in VS Code Agents — Plan E / v1.10.3

FRAG is an installed selected-evidence conversation agent under **Remote**, with a right-hand **Browser** review page. Three directories stay separate: installed program, explicitly selected project folder, and project state. It does not modify the project with coding tools or implicitly use the FRAG development repository.

## Execution windows and Workspace

| Surface | What to do there |
| --- | --- |
| Dedicated instance's ordinary editor / Welcome window | Install or inspect the VSIX, edit this instance's settings, then run **FRAG: Enable in Agents Window → Open Agents**. |
| The same instance's **Agents** window | Configure models, run **FRAG: Start Project Host**, select the FRAG Remote project, chat, open Review and stop the owned Host. |
| **Choose FRAG evidence project → Bind project** dialog | Select the local folder containing the intended evidence. This is the folder the Host binds. |
| Right-hand Review **Workspace** page | Select evidence and control the current task's stages within that bound folder. It does not change the Host's project binding. |

**Run FRAG: Start Project Host in the Agents window.** The ordinary editor does not register the native Remote Host settings required by Start. A key saved in `settings.json` does not add that capability to the ordinary window. Preserve the same `--user-data-dir` and `--extensions-dir` when switching windows; a normal VS Code instance or named editor Profile can use different resources. Confirm the title is **Agents** before starting.

The evidence Workspace is your selected source folder, for example a separate `FRAG-Test` folder containing `sample.txt`. Select one local folder; for a multi-root VS Code workspace, choose the intended evidence root rather than the `.code-workspace` file. It is distinct from the installed Host directory, extension global-storage state and VS Code user-data directory. You do not need to open the FRAG source checkout. Selecting the project bounds file selection; it does not index all files or send them to a model. Opening a local folder alone does not connect the native conversation to FRAG: select **Remote → FRAG · project ID → Folders** after startup.

## Build and install

From the source checkout, build the two private local artifacts:

```powershell
npm.cmd run package:agents
```

The installation files are **`frag-host-1.10.3.zip`** and **`frag-bridge-1.10.3.vsix`**, both in **`.tmp/packages/`**. The extension filename starts with `frag-`. If the VSIX is absent from the install dialog's file list, enter its full absolute path. Other temporary verification files are not installation packages.

Extract `.tmp/packages/frag-host-1.10.3.zip` into a temporary bundle directory. With **PowerShell 7**, run that bundle's `install-host.ps1`. It copies only application/resources into `%LOCALAPPDATA%\FRAG\host\1.10.3` and initializes **Python 3.12** plus the unchanged locked backend dependencies using existing `uv`. Use `-InstallPath` for another new directory. An existing target is never overwritten. The ZIP excludes wheels, a Python runtime, development rules, `.env`, tests and private runtime/source data. Keep its distributed notices with the application.

For an explicit new target:

```powershell
pwsh -File ./bundle/install-host.ps1 -InstallPath "$env:LOCALAPPDATA/FRAG/host/1.10.3-local"
```

The installer rejects unknown arguments and uses dependency copy mode across drives. If initialization fails, retain the directory for inspection and choose another new target; no recursive cleanup is performed.

### Dedicated VS Code instance (Windows / 1.140.0)

A named editor Profile alone does **not** isolate Agents in VS Code 1.140.0, commit `07f806f999227108933c2e30515b26eecc1fda74`. The internal **Agents** profile shares the same instance's Default settings, extensions and `chatLanguageModels.json`. `--agents --profile FRAG` still opens that internal profile. Installing the VSIX only into a named profile does not install it for Agents. A visible setting in another window does not prove the executing extension host registers it.

Use new, dedicated user-data and extension directories. This creates FRAG-owned resources without changing your normal instance or copying its models, secrets or extensions:

```powershell
$fragInstance = Join-Path $env:LOCALAPPDATA 'FRAG\vscode-v110-human'
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --new-window
$fragVsix = '<absolute-package-directory>\frag-bridge-1.10.3.vsix'
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --install-extension $fragVsix
code --user-data-dir "$fragInstance\user-data" --extensions-dir "$fragInstance\extensions" --list-extensions --show-versions | Select-String '^frag-local\.frag-bridge@'
```

Replace the package-directory placeholder with the actual absolute directory containing the matching VSIX. If you already have a dedicated instance, retain its existing directories. Confirm `frag-local.frag-bridge@1.10.3` in the version listing. Do not add `--profile`: the isolated instance's Default resources are intentionally dedicated to FRAG.

Alternatively, in that instance's **ordinary editor window**, press `Ctrl+Shift+X` → Extensions view `...` menu → **Install from VSIX...** → select `frag-bridge-1.10.3.vsix`. The command palette (`Ctrl+Shift+P`) also offers **Extensions: Install from VSIX...**. Inspect **FRAG Local Host** there and confirm version **1.10.3**. Both installation methods install the extension into the chosen instance; the Host ZIP's `install-host.ps1` installs the separate backend program. [Official VSIX installation instructions](https://code.visualstudio.com/docs/configure/extensions/extension-marketplace#install-from-a-vsix).

Keep those same directory arguments on every subsequent launch. No Marketplace publication, configuration schema injection or VS Code installation edits are required. Before Start, the extension and Host must both be **1.10.3**; an old **1.10.0** extension rejects the new Host's health version even when `frag.hostInstallation` points to the new directory.

In that ordinary isolated window, reload after installation and run **FRAG: Enable in Agents Window**. It preserves other `extensions.supportAgentsWindow` entries and opts in `frag-local.frag-bridge`. Select **Open Agents** to use VS Code's native same-instance window command. Alternatively:

```powershell
$fragInstance = Join-Path $env:LOCALAPPDATA 'FRAG\vscode-v110-human'
code --user-data-dir "$fragInstance/user-data" --extensions-dir "$fragInstance/extensions" --agents
```

Switch to that **Agents** window before running **FRAG: Start Project Host**. Keep the ordinary window for extension installation and inspection.

Reload an already open Agents window with **Developer: Reload Window**. Its `Ctrl+Shift+P` palette must list all four FRAG commands. **Extensions: Show Installed Extensions** is unavailable in this Agents window; install/list extensions using the isolated ordinary window or the CLI with the same directory arguments. Do not diagnose it using a different ordinary Profile. If commands are absent, check installation in the isolated Default extension list, the opt-in, workspace trust and reload before proceeding.

For the zero-model installation check, choose **Continue Without Signing In** if the fresh Agents onboarding dialog offers it. Signing in or configuring a provider is separate from installation acceptance.

Set `frag.hostInstallation` in this isolated instance if the Host was installed at a nonstandard path. Set `frag.modelConfigFile` explicitly as described below. Application settings belong to the isolated instance, rather than a named editor Profile.

## Open Review and Settings without a session

After installation/configuration, use the dedicated **Agents** welcome screen; do not create or open a native session just to enter FRAG:

1. `Ctrl+Shift+P` → **FRAG: Start Project Host** → choose the evidence folder → **Bind project**. A project is required, but a session is not. Skip Start if this window already owns the running Host.
2. `Ctrl+Shift+P` → **FRAG: Open Review**. This copies the running Host's `/review` URL and attempts to open a right-hand Browser tab. There is no session ID in this entry URL, and no session is created by the command.
3. Paste the copied URL into the **Browser address bar** and press `Enter`; opening the tab alone does not navigate it. If the right pane still shows Files/Changes, use its `+` menu to open Browser. Do not use the composer or Files search, and do not reuse an old port.
4. On **Select a native session**, leave the selection empty and open **Settings** from the right navigation (Settings icon in narrow panes). Save application preferences and explicit project sources. No New/Remote conversation selection/Send is needed for this configuration route. Model readiness is Not checked until a native task has a saved model selection.
5. Start a native conversation using the next section only when ready for a task. For configuration only, finish with **FRAG: Stop Project Host**.

Start can enumerate configured models, but neither Start nor opening Review generates a model response. Saving Settings does not automatically index evidence or run Research/Context/Inference. A terminal-unavailable notification is the deliberate native coding-tool boundary, not an instruction to open FRAG through a terminal. Files is not the Review page.

## Start a conversation in a separate test project

1. Create a separate local folder containing only intended synthetic evidence, such as `FRAG-Test/sample.txt`. Open **Agents in the dedicated instance** using the steps above. Configure its own model file; use `[]` only for a new empty model-free test configuration. Preserve existing providers when reusing an instance. If Workspace Trust restricts the current window, review that intended workspace before Start.
2. Confirm the window is titled **Agents**, press `Ctrl+Shift+P`, then run **FRAG: Start Project Host**. In **Choose FRAG evidence project**, select the folder containing `sample.txt` and click **Bind project**. The extension checks registered settings, the local trusted execution environment and the explicit model-file binding before opening a bridge or child process. It starts its own loopback Host on an unused port and adds only its new Remote entry. A matching stale entry is preserved and requires manual inspection before restart. Starting from the ordinary editor fails with a clear message before any process is launched.
3. Click **New / Ctrl+N**. Click the **current folder-name capsule above the composer**. There is no fixed menu named Workspace. Under **Remote**, choose **FRAG · project ID → Folders**. Accept the advertised root with **OK**, retaining its native URI-style path (for example `/S:/.../project/` on this Windows build). Do not replace it with a backslash path. The Host supplies virtual ancestry containing only that selected path so the native picker can validate parents; it never enumerates actual parent directories, siblings or project files. Confirm trust only for your intended synthetic folder. The normal local-folder `Ctrl+O` action does not select a Remote FRAG provider.
4. Select an available model and send a 3–500 character task. Native Send saves a task, with zero model calls or automatic indexing.
5. Run **FRAG: Open Review**. The URL is copied; paste it into the right-hand Browser address bar. Choose the matching FRAG session. Save explicit project sources/locators in **Settings**, return to **Workspace** and use saved configuration to preview Context. **Special configuration** optionally customizes this run or conversation and enables Research; saving settings never runs a model or builds an index automatically.
6. Review exact API arguments and bindings, check consent, and approve Context. Explicitly prepare and separately approve Inference. Each optional Research turn also needs fresh approval. Review the cited result and record human acceptance separately.

Before Send, confirm that the native folder picker is using the intended **FRAG Remote** project. When opening Review, select the matching Host/session. For installation acceptance with `[]`, stop after connection/folder selection and run **FRAG: Stop Project Host** in Agents. The FRAG composer has no configured model, so do not send a task. The native window can display sign-in notices or a terminal-unavailable error after folder trust: FRAG deliberately rejects native terminal/coding requests. These notices do not authorize those capabilities or certify provider readiness.

To change the evidence project, stop the owned Host in that Agents window, start again and bind the new folder, then choose its new FRAG Remote entry. Changing a local editor folder or clicking Review's Workspace page does not rebind an existing Host. Saved per-project state stays separate.

### Reuse an already configured instance

If the matching v1.10.3 components, dedicated paths and Agents opt-in are already present, skip artifact installation and opt-in setup. Retain the existing model JSON and credentials. Open Agents with the same directory arguments above, check whether the existing FRAG Host is connected, and select its Remote project. Run Start only when a new owned Host is needed; inspect a matching stale registration before restarting.

**Open User Settings (JSON)** confirms saved configuration and which instance's file is open. It does not certify running processes or settings registration in the executing window. `This window has no registered chat.remoteAgentHosts setting` is the window-capability preflight failure: open the dedicated Agents window and retry there. If it persists in Agents, confirm the same instance directories and extension version, reload Agents and recheck the supported VS Code build. Adding another JSON entry in the ordinary editor does not resolve an unregistered setting.

Native Send completes with a saved-task receipt. Live workflow progress and output belong to Review; reconnect snapshots include the same saved run's answer/status. Right-hand navigation provides Workspace, Runs and Memory with gray transparent icons and Archivo. Models/Plugins management is not duplicated there. Native Customizations remains available; it does not imply FRAG imported its MCP, Skills, Hooks or coding tools. FRAG selected-evidence plugins remain backend features.

## Model configuration

### v1.10.3 composer and Review repair

Native Send saves the task and completes its native reply immediately. Review displays **Choose task configuration** or **Waiting for approval**; neither waiting state sends a model request. Use **Cancel task** in Review to revoke the waiting workflow. A new task in the same conversation cancels the previous unfinished task and replaces Review's evidence/approval controls. A cancelled task remains cancelled in history, with explicit restart steps. Unknown external outcomes still require reconciliation.

Draft text, model selection and Context attachment descriptors are acknowledged unchanged and retained only in Host process memory for same-process reconnects. Drafts are never written to the runtime database, attachment URIs are never dereferenced, and a Host restart discards unsent drafts. Successful Send or an explicit draft-clear action clears the volatile draft. Native attachments cannot become evidence through Send: remove Context attachments, resend the text task, then choose evidence in Review. Length, attachment, message-format, model-selection and turn/session-state failures have distinct messages.

Upgrade an installed v1.10.1 setup with the matching **v1.10.3 Host ZIP and VSIX**, update `frag.hostInstallation`, reload Agents and restart the project Host. Preserve the old installation and saved project state. A source checkout change does not update a running installed Host. See [repair verification](PLAN-E-VERIFICATION.md).

### v1.10.1 session repair and upgrade

That earlier repair was desktop-tested on VS Code **1.141.0** for native provisional creation, explicit model selection, task persistence and owned Stop with a synthetic model and zero generation calls. The original **1.140.0** configuration/API review remains historical; this bounded check does not certify real-provider authentication, effort, generation or full upgrade compatibility. See [repair verification](PLAN-E-VERIFICATION.md).

VS Code can create a provisional session without a model before the composer submits a task. The Host now accepts that unbound session without choosing a default. Send must supply an explicit ID from the current model catalog; it binds the saved task without a model call or automatic indexing. Missing selection, a model no longer in the bound catalog and catalog retrieval failure produce distinct errors. Invalid IDs and per-session effort overrides remain rejected; each generation still needs its own exact preview and one-use approval.

For an installed v1.10.0 setup, run **FRAG: Stop Project Host**, install the new Host ZIP into a new v1.10.1 directory and update `frag.hostInstallation`. Install the matching v1.10.1 VSIX using the same dedicated user-data and extensions directories, then reload Agents. Retain `frag.modelConfigFile` and the provider's VS Code-managed credentials. Restart against the intended evidence folder and create a new native task. Do not overwrite or delete the old installation or saved state. A checkout-only repair cannot change an already installed Host.

In the dedicated **Agents** window, use **Chat: Manage Language Models** and **Chat: Open Language Models (JSON)**. For the instance above the active resource is `$fragInstance/user-data/User/chatLanguageModels.json`. Set `frag.modelConfigFile` to that full absolute path; VS Code settings do not expand the PowerShell variable. An empty setting, another named Profile's file, a missing file or a linked file fails before startup. There is no `%APPDATA%` fallback. Preserve VS Code secret references and configure only this dedicated instance. FRAG does not read, copy or display API keys.

Saving `[]` permits an installation/connection/Stop check with an empty model catalog. A real provider is not required for that check. Models not represented in the explicitly bound configuration are excluded. Research, Context and Inference use the same native-selected model and saved per-model default effort. See [configuration paths, verification steps and pinned API evidence](MODEL-CONFIGURATION.md).

**Manage Language Models** lists both the configured supplier and the running Host's published models. A provider such as MirrorCoding and a **Frag** group can therefore show the same model name from the same dedicated configuration. The JSON does not need a second `name: FRAG` provider object. The groups represent separate registrations with different internal IDs, not separate keys or evidence permissions. Stopping the owned Host withdraws its Frag entries; the original provider remains configured. Do not delete the provider to address this normal double listing.

The preview freezes the stable model API inputs. It does not certify final provider HTTP fields, hidden retries, usage, billing or relay execution. FRAG performs zero automatic retries; schema/citation checks do not establish semantic correctness.

## State and lifecycle

State lives in the extension's local global storage under `projects/<canonical-path-hash>/`: `runtime.sqlite3`, `rag/` caches and `plugins/`. No state or credentials are written into the bound folder. The Host advertises only that root; native filesystem, terminal and edit operations remain unsupported. Linked paths, hidden configuration, rules and generated directories are excluded from project evidence.

**FRAG: Stop Project Host** waits for the owned process shutdown, closes its bridge and removes only the exact owned name/address pair. Repeated Start/Stop operations are serialized; Start while a Host or incomplete cleanup is owned asks you to Stop first. Other registrations and processes are preserved. Enablement flags are restored only when there are no other registered hosts. Configuration writes are not atomic: a partial registration triggers independent cleanup attempts. Cleanup failures cannot replace the original startup error. An incomplete cleanup message retains the owned handle for an explicit Stop retry; inspect stale entries manually if the settings remain unavailable. Arbitrary provider error details are not printed because they can contain secrets.

One extension instance owns one active project Host. Stop it explicitly before selecting another project. Closing the owner window also stops it. After an abrupt process crash, inspect the stale owned process/registration manually before restarting. A different project's database is never reused.

Restart clears approvals. Reconnect reads snapshots without calling a model. Source/configuration changes require new preview; unknown outcomes require reconciliation and never resend. Legacy Pi reports stay readable/exportable but cannot resume. Native Stop waits for the governed boundary and cannot retract a dispatched provider request.

The source standalone GUI remains available through `npm run dev` with direct backend Fake/Responses configuration. Legacy `FRAG_*_LLM_ADAPTER=pi` is rejected; remove those retired keys before starting that development route. `npm run agents` now prints this installed workflow and does not start a source-bound Host.

## Evidence

The compatibility baseline is **VS Code 1.140.0 / AHP 0.9.0**, with source/manifest checks for installed Copilot Chat **0.68.0**. [Plan D desktop evidence](NATIVE-AGENTS.md) is historical and uses Fake providers; it is not acceptance of the new model bridge. New synthetic tests cover selected-model stages, changed configuration, duplicate approvals, origin/auth boundaries and directory separation. Real-provider calls require their own human-reviewed approval.

[Plan E delivery checks](PLAN-E-VERIFICATION.md) record installed-package, native desktop and Review evidence separately from real-provider/human acceptance.

[Plan E scope](../../docs/plan-e.md) · [Review UI](../../src/agents/README.md) · [Host adapter](../../backend/frag_api/services/AGENT-HOST.md) · [Architecture](../../docs/architecture/vscode-migration/architecture.html). The original failed Chat probe remains [historical](CHAT-PROBE.md).
