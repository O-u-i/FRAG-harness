# FRAG in VS Code Agents: compatibility probe

Plan D targets a FRAG-owned session in the VS Code Agents window, with a right-hand review surface. The existing FRAG workspace and its governed backend remain the functional baseline. This directory contains an original offline development extension, not a released FRAG integration or a packaged VSIX.

## Verified result

The native-session gate **failed** on 2026-10-07 with VS Code **1.140.0**, commit `07f806f999227108933c2e30515b26eecc1fda74`, and probe extension **0.0.1**. This result applies to this build and the proposed Chat session extension route; it does not establish that every future Agents integration route is impossible.

| Gate | Observed result |
| --- | --- |
| Extension activation and command registration | Passed in the actual Agents window. |
| Proposed session controller and content provider registration | Passed without a registration exception. |
| FRAG entry in the native session-type picker | Failed: the picker offered Copilot and Claude, without FRAG. |
| Native FRAG session creation | Failed in the renderer: `Cannot read properties of null (reading 'loadSession')`. |
| FRAG content provider and message handler invocation | Neither was invoked: both counters remained zero. |
| FRAG backend, model requests and selected evidence | Not exercised by this probe. |
| Right-hand review GUI and native Customizations integration | Not implemented; the carrier decision remains open. |

The extension's generated `workbench.action.chat.openNewChatSessionInPlace.frag-offline` command returned without rejecting its promise. The renderer logged the failure internally. A returned command, successful registration, or an empty extension error list is therefore insufficient acceptance evidence.

The installed workbench separates the shared Chat session service from the Agents window's native provider registry. The proposed extension API accepted the probe in the shared service; the tested route did not establish a bridge to the native registry. That source-based explanation agrees with the observed picker and renderer failure. See the [migration boundary diagram](../../docs/architecture/vscode-migration/architecture.html) and [editable source](../../docs/architecture/vscode-migration/architecture.json).

## Reproduce the offline gate

Use the matching VS Code build and a separate development profile. From the FRAG repository root, adjust only the VS Code executable path:

```powershell
$codeExe = 'C:\Path\To\Microsoft VS Code\Code.exe'
$repoRoot = (Get-Location).Path
$probeRoot = Join-Path $repoRoot ('.tmp/vscode-plan-d-' + [guid]::NewGuid().ToString('N'))
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

In that development window:

1. Run **FRAG: Inspect Offline Compatibility** from the Command Palette. Inspect the FRAG compatibility output and the local receipt.
2. Inspect the native session-type picker for a FRAG entry.
3. Run **FRAG: Try Native Session Registration**. Check the actual session surface and the renderer log under the profile's `logs/` directory.
4. Inspect the receipt again. Provider invocation, native session rendering and handler ownership must be observed together before declaring the carrier usable. Do not send a message to a different native harness as a substitute for a FRAG session.

The probe imports only Node built-ins and VS Code's host API. Its handler returns a constant offline response and never invokes a model, FRAG HTTP endpoint or evidence reader. The native VS Code application can still discover global agent customizations or its own project state; a separate user-data directory does not prove complete isolation of the native host. No sign-in or model conversation was performed in the recorded test.

Raw receipts, screenshots, profiles and renderer logs belong under Git-ignored `.tmp/`. The receipt retains `nativeAgentsAcceptance: UNVERIFIED`: the extension cannot certify a renderer outcome from a command promise. The separate test record combines the receipt with the observed UI and renderer log.

## Interface ownership after a carrier passes

| Surface | Intended owner and boundary |
| --- | --- |
| Central session | FRAG must receive the user's message through its own handler and execute its existing governed workflow. Merely selecting a custom model or adding a Copilot custom agent does not prove this ownership. |
| Right-hand review | A FRAG-designed review surface should inspect the same saved run, exact request, approval state and structured report as the backend. Its placement in the native right-hand pane is unverified. |
| Customizations | VS Code owns the native navigation. FRAG skills, MCP, plugins and policies require explicit adapters; they are not transferred by session registration. |
| Existing FRAG GUI | Retained. The supplied component references concern the prospective review surface only. |

Line Sidebar, Glass Icons, Stepper, Branched Menu and Glide Select are optional design references. Their code has not been copied into this probe; no component dependency has been installed. Attribution, applicable license terms, missing styles, keyboard behavior and the final composition must be checked when an actual review surface is implemented. Longer feature explanations belong in feature documentation; the review surface still needs the request and approval facts required for a decision.

The next carrier choice requires a maintainer decision: investigate the Agents window's native integration route, use the ordinary editor Chat surface, or use a Copilot-driven wrapper with a different execution boundary. No fallback has been implemented, and the existing backend approval rules have not changed.

## Authoritative API references

- [Agents window configuration](https://code.visualstudio.com/docs/agents/run/agents-window-configuration): extension opt-in and native window settings.
- [Chat extension guide](https://code.visualstudio.com/api/extension-guides/ai/chat): Chat participants; this alone does not demonstrate a custom native Agents harness.
- [Using proposed APIs](https://code.visualstudio.com/api/advanced-topics/using-proposed-api): experimental APIs and development enablement.
- [Version-pinned Chat session API declaration](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vscode-dts/vscode.proposed.chatSessionsProvider.d.ts): the tested controller and content provider interfaces.

Re-run the native gate after any VS Code or API change. Packaging, installation, review-page placement and publication are separate future checks.
