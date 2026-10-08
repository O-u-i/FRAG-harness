# FRAG in VS Code Agents — Plan E / v1.10.0

FRAG is an installed selected-evidence conversation agent under **Remote**, with a right-hand **Browser** review page. Three directories stay separate: installed program, explicitly selected project folder, and project state. It does not modify the project with coding tools or implicitly use the FRAG development repository.

## Build and install

From the source checkout, build the two private local artifacts:

```powershell
npm.cmd run package:agents
```

Extract `.tmp/packages/frag-host-1.10.0.zip` into a temporary bundle directory. With **PowerShell 7**, run that bundle's `install-host.ps1`. It copies only application/resources into `%LOCALAPPDATA%\FRAG\host\1.10.0` and initializes **Python 3.12** plus the unchanged locked backend dependencies using existing `uv`. Use `-InstallPath` for another new directory. An existing target is never overwritten. The ZIP excludes wheels, a Python runtime, development rules, `.env`, tests and private runtime/source data. Keep its distributed notices with the application.

For an explicit new target:

```powershell
pwsh -File ./bundle/install-host.ps1 -InstallPath "$env:LOCALAPPDATA/FRAG/host/1.10.0-local"
```

The installer rejects unknown arguments and uses dependency copy mode across drives. If initialization fails, retain the directory for inspection and choose another new target; no recursive cleanup is performed.

In VS Code, run **Extensions: Install from VSIX**, selecting `.tmp/packages/frag-bridge-1.10.0.vsix`. No Marketplace publication or VS Code source modification is required. Run **FRAG: Enable in Agents Window** in regular VS Code; it sets the existing `extensions.supportAgentsWindow` opt-in for `frag-local.frag-bridge`. Reload the Agents window. If installed elsewhere, set the application setting `frag.hostInstallation` to the initialized Host directory.

## Start in a separate test project

1. Create a new folder containing only intended synthetic evidence, such as a Markdown note. Open VS Code there, then the **Agents window** (`code --agents`).
2. In Agents, run **FRAG: Start Project Host**. Explicitly select that evidence folder. The extension starts its own loopback Host on an unused port and adds only its named Remote entry, preserving other registrations. It does not stop unrelated Hosts.
3. Click **New / Ctrl+N**. Click the **current folder-name capsule above the composer**. There is no fixed menu named Workspace. Select **Remote → FRAG · project ID → Folders → your folder**. The normal local-folder `Ctrl+O` action does not select a Remote FRAG provider.
4. Select an available model and send a 3–500 character task. Native Send saves a task, with zero model calls or automatic indexing.
5. Run **FRAG: Open Review**. The URL is copied; paste it into the right-hand Browser address bar. Choose the matching FRAG session, select files/locators or retrieval scope, and preview Context.
6. Review exact API arguments and bindings, check consent, and approve Context. Explicitly prepare and separately approve Inference. Each optional Research turn also needs fresh approval. Review the cited result and record human acceptance separately.

The native conversation receives the same saved run's answer/status. Right-hand navigation provides Workspace, Runs and Memory with gray transparent icons and Archivo. Models/Plugins management is not duplicated there. Native Customizations remains available; it does not imply FRAG imported its MCP, Skills, Hooks or coding tools. FRAG selected-evidence plugins remain backend features.

## Model configuration

Use **Chat: Manage Language Models**. The default Windows profile still stores providers in `%APPDATA%\Code\User\chatLanguageModels.json`; another profile needs its actual path in `frag.modelConfigFile`. Preserve VS Code secret references. Research, Context and Inference use the same native-selected model and saved per-model default effort. There is no Pi configuration or FRAG effort override picker. See [exact keys, limits and pinned API evidence](MODEL-CONFIGURATION.md).

The preview freezes the stable model API inputs. It does not certify final provider HTTP fields, hidden retries, usage, billing or relay execution. FRAG performs zero automatic retries; schema/citation checks do not establish semantic correctness.

## State and lifecycle

State lives in the extension's local global storage under `projects/<canonical-path-hash>/`: `runtime.sqlite3`, `rag/` caches and `plugins/`. No state or credentials are written into the bound folder. The Host advertises only that root; native filesystem, terminal and edit operations remain unsupported. Linked paths, hidden configuration, rules and generated directories are excluded from project evidence.

One extension instance owns one active project Host. Starting another project stops only its previous owned Host. **FRAG: Stop Project Host** removes only its registered address; closing the owner window stops it. After an abrupt process crash, inspect the stale owned process/registration manually before restarting. A different project's database is never reused.

Restart clears approvals. Reconnect reads snapshots without calling a model. Source/configuration changes require new preview; unknown outcomes require reconciliation and never resend. Legacy Pi reports stay readable/exportable but cannot resume. Native Stop waits for the governed boundary and cannot retract a dispatched provider request.

The source standalone GUI remains available through `npm run dev` with direct backend Fake/Responses configuration. Legacy `FRAG_*_LLM_ADAPTER=pi` is rejected; remove those retired keys before starting that development route. `npm run agents` now prints this installed workflow and does not start a source-bound Host.

## Evidence

The compatibility baseline is **VS Code 1.140.0 / AHP 0.9.0**, with source/manifest checks for installed Copilot Chat **0.68.0**. [Plan D desktop evidence](NATIVE-AGENTS.md) is historical and uses Fake providers; it is not acceptance of the new model bridge. New synthetic tests cover selected-model stages, changed configuration, duplicate approvals, origin/auth boundaries and directory separation. Real-provider calls require their own human-reviewed approval.

[Plan E delivery checks](PLAN-E-VERIFICATION.md) record installed-package, native desktop and Review evidence separately from real-provider/human acceptance.

[Plan E scope](../../docs/plan-e.md) · [Review UI](../../src/agents/README.md) · [Host adapter](../../backend/frag_api/services/AGENT-HOST.md) · [Architecture](../../docs/architecture/vscode-migration/architecture.html). The original failed Chat probe remains [historical](CHAT-PROBE.md).
