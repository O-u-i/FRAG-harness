# Plan E verification — v1.10.0

## Installation and lifecycle repair — 2026-10-08

Repair baseline: `fix/v5-learning`, HEAD `38600e445bcf32591cbf6c3251ca721dab5215ad`, equal to `feat/v5-learning`. The tracked working tree and staging area were initially clean. This is an IMPLEMENT_APPROVED FRAG_ONLY repair; no branch switch, phase advance, version increment, Finance Core modification, commit or push occurred. `.local-plan-e/state.json` remains at `LOCAL_DELIVERED_PENDING_NEW_BRIDGE_HUMAN_ACCEPTANCE`.

The desktop baseline was Windows x64, VS Code **1.140.0**, commit `07f806f999227108933c2e30515b26eecc1fda74`. A first-party diagnostic extension in an isolated instance reproduced the ordinary extension host's exact unregistered `chat.remoteAgentHosts` write error. `inspect()` can return an object for an unregistered key; its native default must exist. In ordinary VS Code only `chat.remoteAgentHostsEnabled` was registered among the three required settings; Agents registered all three. These are executing-host measurements, not deductions from the settings UI.

`--agents --profile FRAG-Isolated` opened the internal **Agents** profile and shared the isolated instance's Default settings, model file and extension list. The VSIX installed only into the named profile was absent in Agents despite the application opt-in. Installation into the isolated Default extension list, opt-in and reload made all four FRAG commands discoverable. **Extensions: Show Installed Extensions** was unavailable in Agents. The same-instance native **Open Agents** button was exercised successfully. No user normal Profile, existing Host installation or real model configuration was modified.

| Repair evidence | Executed result and limit |
|---|---|
| Extension/model bridge regressions | **19 passed** through `activate()` and registered commands. Covers unregistered settings, all partial writes including write-before-rejection, failed Host/bridge/settings cleanup, bridge-only cleanup retry, concurrent/repeated Start/Stop/deactivate, stale and other registrations, pending notifications, explicit profile paths, empty catalogs, bounded discovery and zero model calls on lifecycle paths. Existing synthetic generation tests remain separate. |
| Backend synthetic suite | **452 passed, 2 skipped**, with a new repository-local pytest base directory. The skips require separately supplied FC-owned protocol 1/2 release archives; no live FC test was performed. Picker tests reject siblings, content reads, traversal, authorities and parent session roots while permitting only virtual ancestry derived from the bound path. |
| Frontend/build | **60 passed**. Standalone and Agents builds, TypeScript, module boundaries, repository safety, version synchronization and diagrams passed. No frontend feature or third-party dependency was added or upgraded. Existing source-size warnings remain below the repository limit. |
| Final packages | Final VSIX installed by the real VS Code CLI into isolated directories. Its four code/README files match packaged bytes; the manifest matches after excluding VS Code's injected `__metadata`. All **90** installed Host payload files match the final Host ZIP. Unchanged locked backend versions initialized **55** production packages in a new installation. Rules, secrets, tests, databases and personal data are excluded from both packages. |
| Actual command chain | New empty user-data/extensions directories → real VSIX installation → ordinary-window **FRAG: Enable in Agents Window** → native **Open Agents** → four commands in the Agents palette → native model JSON command creating the dedicated `[]` file → explicit synthetic-folder selection by **FRAG: Start Project Host** → native registration and AHP connection → **Remote / FRAG / Folders / OK** → trust the intended synthetic root → **FRAG** composer → repeated **FRAG: Stop Project Host**. No acceptance script called `launchHost()` directly. |
| Native folder acceptance | Captured real WebSocket traffic showed VS Code resolving the bound root's parents before accepting it. Root-only responses rejected that step. The repaired Host supplies virtual ancestry containing only the next component of the selected path, without enumerating the actual filesystem. Native folder acceptance then succeeded. |
| Owned Stop | Stop removed the owned name/address entry, closed its bridge and terminated its Windows Python launcher/child. Health became unreachable; no test Host process remained. Repeated Start while owned launched no replacement, and repeated Stop was harmless. |
| Models and semantic acceptance | Dedicated model JSON stayed `[]`; native FRAG showed **Models**, with no configured model. Runtime contained **0 runs and 0 agent sessions**. Native Send and real-provider generation were not performed; **zero real model calls**. Provider credentials, authentication, output, billing and human semantic acceptance remain unverified. |

The model-free desktop run still displayed signed-out Copilot notices. When the native window tried to create a terminal after folder trust, FRAG correctly returned its unsupported-terminal error; the native window displayed that notice. This does not grant coding capabilities and is not a Host startup failure. Only the stated Windows/VS Code build was desktop-tested. Model configuration must be completed by the human inside the dedicated instance before separately approved generation testing.

Final artifacts are in ignored `.tmp/plan-e-fix-20261008-01/packages-delivery/`:

- `frag-bridge-1.10.0.vsix` — SHA-256 `ca36752bbf3277d875b0b0702e90e8f891f6d84a8846a26f61a055e6f2bbe1fd`.
- `frag-host-1.10.0.zip` — SHA-256 `9f2806846af48d82646b6c1d7d8b7423d75aa95e5a2dd39334746a57c865f163`.

Private command/window snapshots, native WebSocket diagnostics, screenshots, connection/Stop receipts and package comparisons are retained under ignored `.tmp/plan-e-fix-20261008-01/`. Earlier failed probe profiles, stale registrations, installations and package iterations were retained without deletion. The previous `.tmp/plan-e-final/launch-smoke.cjs` and `stop-smoke.cjs` exercised launch helpers directly; their old results do **not** establish extension-command or real settings-write acceptance. The final repair uses the actual command chain above.

Proposed commit: `fix: isolate VS Code Agents setup and harden FRAG host lifecycle`

Cross-repo impact: **NONE**. Other repo status: **NOT_TOUCHED**. No FC compatible-version change is required. Model-free desktop acceptance does not advance Plan E or replace human semantic acceptance.

Pinned implementation references: [Agents profile resource sharing](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/platform/userDataProfile/common/userDataProfile.ts#L24), [Agents profile selection](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/platform/windows/electron-main/windowsMainService.ts#L1724), [Agents-only Remote Host registration](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/sessions/contrib/providers/remoteAgentHost/browser/remoteAgentHost.contribution.ts#L22). The diagnosis also checked the installed desktop bundle and executing extension hosts.

## Historical delivery record

The following original delivery evidence is retained for provenance. It predates the repair and must be read with the command-boundary limitation above.

Checked on 2026-10-08 against baseline commit `80fa8c2`. Scope is FRAG_ONLY. Finance Core was not modified. Nothing was staged, committed, pushed, tagged or released.

| Evidence | Result and limit |
|---|---|
| Backend synthetic suite | 451 passed, 2 skipped. Skips require separately supplied FC-owned protocol artifacts. No live FC or personal KB access. |
| Frontend suite | 60 passed, including escaped model HTML, rejected active links, bounded quotes and collapsed annotations. |
| Node model bridge | 6 passed: exact API arguments, saved effort, one-use dispatch, changed configuration, origin/auth rejection and unknown outcomes. |
| Build gates | TypeScript, standalone production build, dedicated Review build, version sync, module boundaries, source size, repository safety and README diagrams passed. |
| Installed artifacts | Host ZIP initialized 55 unchanged locked production packages; actual VSIX installed in an isolated VS Code profile. Source rules, `.env`, tests and private runtime data are excluded. |
| Installed runtime | Two synthetic project folders advertised independently; each listed only its own evidence and retained separate sessions/state. Native Send caused zero model calls. Two distinct approvals produced Context and Inference through the packaged bridge with a synthetic stable-API consumer. Duplicate approval was rejected. |
| Owned lifecycle | Packaged Stop terminated its Windows venv launcher/Python tree and made that Host unreachable. All processes created for these isolated tests were closed; unrelated processes were not targeted. |
| Native desktop | VS Code 1.140.0 / AHP 0.9.0 discovered the project Remote Host, loaded its saved session, displayed Synthetic Native and rendered the same saved result once. The signed-out test profile also displayed native sign-in and terminal-unavailable notices; this is not full human acceptance of a fresh signed-in workflow. |
| Review desktop | Installed Review checked at 570×900 and 960×900, representing the resizable desktop Browser pane. Right navigation, Archivo, rendered Markdown and collapsed citation/notes sections were inspected; no horizontal overflow or external resource requests. Keyboard report navigation passed. No mobile acceptance is claimed. |
| Architecture | Showcase validation: all 9 checks passed, 0 composition errors/warnings. Final light HTML passed browser containment at 1440×900, 1600×1000, 1920×1080 and 2048×1320. HTML and canonical SVG were visually inspected; source/HTML/SVG component consistency is checked. |
| Privacy/Git | Rules, `.env`, ledgers, packages, databases, profiles and screenshots remain ignored; staged list is empty. Retired Pi files are explicit working-tree deletions awaiting the maintainer's reviewed commit. No existing sensitive/rule file was automatically untracked. |

The maintainer's previously reported real-model/manual acceptance belongs to the existing runtime. These checks made **zero paid model calls** and do not certify supplier HTTP arguments, internal retries, usage, billing, reasoning execution or human semantic correctness. The new bridge needs its own fresh human-approved real-provider review. Native MCP/Skills/Hooks/tool imports remain deferred.

One failed diagnostic installation was retained rather than deleted or overwritten. Installation rejects unknown parameters and existing targets; choose a new `-InstallPath`, then set `frag.hostInstallation` accordingly. The successful final installation was tested separately.

Private receipts, package SHA-256 values, project databases, profiles and screenshots are under ignored `.tmp/` and `.local-plan-e/`. The diagram's deterministic delivery receipt and final light-byte/browser evidence are separate records. Rebuilding packages can change archive hashes; compare against that build's receipt.

Proposed commit: `feat: deliver installed VS Code FRAG host and native model bridge`

Cross-repo impact: NONE. Contract change: ADDITIVE native API request schema; Pi execution is retired. Other repo status: NOT_TOUCHED. No new FC compatible version is required because its released read-only contract is unchanged.
