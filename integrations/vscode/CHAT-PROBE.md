# Historical Chat extension probe

This records the earlier unsuccessful extension test. The implemented AHP route is described in [README](README.md).

# FRAG in VS Code Agents: compatibility investigation

Plan D targets a FRAG-owned session in the VS Code Agents window, with a right-hand review surface. The existing FRAG workspace and its governed backend remain the functional baseline. A local **AHP 0.9.0 host passed native discovery, session creation and offline message/reply checks** on VS Code 1.140.0. A local HTTP fixture also loaded in the native right-hand Browser tab. See [native integration findings](NATIVE-AGENTS.md) for the tested route and remaining adapter work.

This directory contains the earlier original offline Chat extension probe, not a released FRAG integration or a packaged VSIX. That extension route failed independently of the successful AHP investigation.

## Earlier Chat extension result

The native-session gate **failed** on 2026-10-07 with VS Code **1.140.0**, commit `07f806f999227108933c2e30515b26eecc1fda74`, and probe extension **0.0.1**. This result applies to this build and the proposed Chat session extension route; it does not establish that every future Agents integration route is impossible.

| Gate | Observed result |
| --- | --- |
| Extension activation and command registration | Passed in the actual Agents window. |
| Proposed session controller and content provider registration | Passed without a registration exception. |
| FRAG entry in the native session-type picker | Failed: the picker offered Copilot and Claude, without FRAG. |
| Native FRAG session creation | Failed in the renderer: `Cannot read properties of null (reading 'loadSession')`. |
| FRAG content provider and message handler invocation | Neither was invoked: both counters remained zero. |
| FRAG backend, model requests and selected evidence | Not exercised by this probe. |
| Right-hand review GUI and native Customizations integration | Not implemented by this extension. A later AHP/Browser test verified carrier and page placement only. |

The extension's generated `workbench.action.chat.openNewChatSessionInPlace.frag-offline` command returned without rejecting its promise. The renderer logged the failure internally. A returned command, successful registration, or an empty extension error list is therefore insufficient acceptance evidence.

The installed workbench separates the shared Chat session service from the Agents window's native provider registry. The proposed extension API accepted the probe in the shared service; the tested route did not establish a bridge to the native registry. That source-based explanation agrees with the observed picker and renderer failure. See the [migration boundary diagram](../../docs/architecture/vscode-migration/architecture.html) and [editable source](../../docs/architecture/vscode-migration/architecture.json).

## Reproduce the offline gate

Use the matching VS Code build and a separate development profile. From the FRAG repository root, adjust only the VS Code executable path:

```powershell
$codeExe = 'C:\Path\To\Microsoft VS Code\Code.exe'
$repoRoot = (Get-Location).Path
$probeRoot = pwsh -NoProfile -File ./scripts/maintain-tmp.ps1 -NewRun vscode-chat-probe
$userData = Join-Path $probeRoot 'user-data'
$extensions = Join-Path $probeRoot 'extensions'
$workspace = Join-Path $probeRoot 'workspace'
$settingsDir = Join-Path $userData 'User'
New-Item -ItemType Directory -Force -Path $settingsDir, $extensions, $workspace | Out-Null
@'
{
  "telemetry.telemetryLevel": "off",
  "update.mode": "none",
  "extensions.autoCheckUpdates": false,
  "extensions.autoUpdate": false,
  "workbench.enableExperiments": false,
  "security.workspace.trust.enabled": false,
  "workbench.startupEditor": "none",
  "chat.agentHost.allowSignedOutWhenUsable": true,
  "workbench.browser.enableChatTools": false,
  "extensions.supportAgentsWindow": { "frag-local.frag-agents-probe": true }
}
'@ | Set-Content -LiteralPath (Join-Path $settingsDir 'settings.json') -Encoding utf8
$env:FRAG_VSCODE_PROBE_RECEIPT = Join-Path $probeRoot 'extension-receipt.json'
Remove-Item Env:ELECTRON_RUN_AS_NODE -ErrorAction SilentlyContinue
$launchArgs = @(
  '--agents', '--new-window',
  '--user-data-dir', ('"' + $userData + '"'),
  '--extensions-dir', ('"' + $extensions + '"'),
  ('--extensionDevelopmentPath="' + (Join-Path $repoRoot 'integrations/vscode') + '"'),
  '--enable-proposed-api=frag-local.frag-agents-probe',
  '--disable-extension=GitHub.copilot-chat', '--disable-extension=GitHub.copilot',
  ('"' + $workspace + '"')
)
Start-Process -FilePath $codeExe -ArgumentList $launchArgs -WindowStyle Hidden
```

After closing the development window and confirming its processes have stopped, close the task with `pwsh -NoProfile -File ./scripts/maintain-tmp.ps1 -CloseRun $probeRoot`. This profile is not marked disposable; retain its evidence before any cleanup.

In that development window:

1. Run **FRAG: Inspect Offline Compatibility** from the Command Palette. Inspect the FRAG compatibility output and the local receipt.
2. Inspect the native session-type picker for a FRAG entry.
3. Run **FRAG: Try Native Session Registration**. Check the actual session surface and the renderer log under the profile's `logs/` directory.
4. Inspect the receipt again. Provider invocation, native session rendering and handler ownership must be observed together before declaring the carrier usable. Do not send a message to a different native harness as a substitute for a FRAG session.

The probe imports only Node built-ins and VS Code's host API. Its handler returns a constant offline response and never invokes a model, FRAG HTTP endpoint or evidence reader. The native VS Code application can still discover global agent customizations or its own project state; a separate user-data directory does not prove complete isolation of the native host. No sign-in or model conversation was performed in the recorded test.

Raw receipts, screenshots, profiles and renderer logs belong under Git-ignored `.tmp/`. The receipt retains `nativeAgentsAcceptance: UNVERIFIED`: the extension cannot certify a renderer outcome from a command promise. The separate test record combines the receipt with the observed UI and renderer log.

## Authoritative API references

- [Agents window configuration](https://code.visualstudio.com/docs/agents/run/agents-window-configuration): extension opt-in and native window settings.
- [Chat extension guide](https://code.visualstudio.com/api/extension-guides/ai/chat): Chat participants; this alone does not demonstrate a custom native Agents harness.
- [Using proposed APIs](https://code.visualstudio.com/api/advanced-topics/using-proposed-api): experimental APIs and development enablement.
- [Version-pinned Chat session API declaration](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vscode-dts/vscode.proposed.chatSessionsProvider.d.ts): the tested controller and content provider interfaces.

Re-run the native gate after any VS Code or API change. Packaging, installation, review-page placement and publication are separate future checks.
