# Plan E verification — v1.10.2

## Review layout follow-up — 2026-10-08

The maintainer authorized four additional GUI repairs while retaining v1.10.2. This extends the uncommitted composer/Review repair below. Main content now scrolls inside the viewport with a stable native scrollbar gutter; the right sidebar stays fixed. Workspace, Runs and Memory share one page navigation, with labels before their right-side lines or glass icon. The single-item Background disclosure was removed: Memory is reviewed model context, not a settings category. Evidence/checklist headings use `and`. A baseline browser inspection confirmed that the previous ampersand was U+0026 and Archivo was loaded; no malformed entity or encoding corruption was found.

| Verification | Executed result and limit |
|---|---|
| Page layout | Built Review tested in Edge at **570×900 and 960×900**. Workspace → Runs → Memory → Workspace retained identical main/sidebar rectangles and content widths, with a **15 px** gutter on every page and no document overflow. At **570×500**, overflowing Memory scrolled only the main region; sidebar bounds stayed fixed and keyboard focus scrolled its target into view. |
| Navigation and visual | All three entries occupy one named navigation, exactly one page is current, and label bounds precede their marks. Keyboard activation, visible focus, decorative icon semantics and reduced-motion behavior passed. Screenshots of all three pages at both widths were inspected; Archivo loaded, no page errors or external requests. |
| Workflow regression | Repeated the real local HTTP/WebSocket flow with Counting Fake: draft → task save → waiting → evidence → preview → single-use Context approval → separately approved Inference. Zero calls through preview; exactly Context and Inference afterward. Approval replay returned 409. Cancellation, replacement, refresh and reconnect passed. No real provider was called. |
| Tests and builds | **62 frontend, 29 focused backend and 19 bridge tests passed**. TypeScript, architecture/module/privacy/version/diagram checks, Review and standalone production builds passed. The prior full backend result remains **466 passed, 2 skipped**; it was not rerun for this CSS/navigation follow-up. No backend or dependency was changed by this follow-up. |
| Packages | Fresh **v1.10.2** Host ZIP and VSIX replaced the earlier local artifacts. All **90 file-backed Host payloads and 5 VSIX inputs** matched the checkout/build; duplicate, private/rule/test/database/source-map paths were rejected. Extracted Host smoke passed with zero runs/generation calls. The user's installed v1.10.1 Host was not replaced or restarted. |

Current artifacts are `.tmp/packages/frag-host-1.10.2.zip` (SHA-256 `cd1dfca7fc859cd1d1d8affe5783f55dcd4bf061e73cf3ac6bb40756f1f35e91`) and `.tmp/packages/frag-bridge-1.10.2.vsix` (SHA-256 `505bde98447beadbd4b813ce88846590cba62c9b5d0c3ba2191a93998e22f3d2`). Receipts and runnable browser checks are under ignored `.tmp/v1102-ui-20261008-01/`. Use a new Host installation directory, select it through `frag.hostInstallation`, and restart the project Host to apply the package. Existing installations are not overwritten by the installer. The VSIX source inputs are unchanged by this GUI follow-up.

Scope: **FRAG_ONLY**; cross-repo impact **NONE**, GUI contract change **NONE**, other repo **NOT_TOUCHED**. The earlier additive cancellation endpoint remains documented below. No commit, push, release or phase acceptance occurred. Actual VS Code desktop composer evidence below predates this GUI follow-up; these new layout checks use Edge, not a newly installed user Agents window.

Proposed commit: `fix: repair native task state and stabilize Review UI in v1.10.2`

## Composer and Review state repair — 2026-10-08

Baseline HEAD: `4bfb391`; tracked worktree and staging were clean. The maintainer authorized the listed bugs, related omissions and v1.10.2. Scope: FRAG_ONLY. Dependencies and distributed third-party notices are unchanged. No personal configuration, credentials or Finance Core files were changed; no commit, push, phase advance or real-provider request occurred.

Native Send now completes a saved-task receipt immediately. Review owns the separate pending workflow and explicitly shows evidence/approval waiting, cancellation and restart instructions. Cancel task or a replacement native task invalidates the old carrier controls and consumes its underlying stage token. Draft edits echo unchanged, remain volatile across same-process reconnects, and never enter SQLite; successful Send or explicit clear removes them. Attachment descriptors are never dereferenced. Length, attachment, malformed-message, model and session/turn failures have distinct errors. The earlier legal-length task's precise original failure is still unconfirmed; it is not attributed to length by this repair.

| Verification | Executed result and limit |
|---|---|
| Backend | **466 passed, 2 skipped**, synthetic providers/sources, dotenv disabled and a fresh repository-local pytest base directory. The skips require separately supplied FC protocol artifacts. **29 focused Host/composer/bridge tests** cover drafting, no attachment reads, cancellation/replacement, Context/Inference/Research token revocation, failures and reconnect. |
| Frontend and bridge | **62 frontend / 19 bridge passed**. Cancelled tasks hide evidence/approval controls; existing one-use, source, model and origin bindings remain enforced. |
| Browser flow | Real local HTTP/WebSocket and built Review with Counting Fake: draft → save → wait → selected file/locator → preview → one-use Context approval → separately approved Inference. Calls remained zero through preview, then exactly one per stage; replay returned 409. Cancellation, automatic replacement, fresh consent and refresh/reconnect passed. No external Review requests or page errors. |
| Native desktop | Actual installed **VS Code 1.141.0**, in a new isolated user-data/extensions directory with a synthetic local Remote Host. Continuous typing, paste, Context Changes chip addition/removal preserved input. Native Send saved one task, completed its reply, showed no visible Reasoning and no active Stop button, with zero additional model calls. This checks native AHP/composer behavior, not an installed VSIX lifecycle or provider authentication. |
| Builds and visual | Review and standalone production builds, TypeScript, architecture/module/privacy/version/diagram checks passed. Review cancellation, restarted evidence selection and waiting screenshots were inspected at **570×900 and 960×900**; no horizontal overflow. Native completion was also visually inspected. |
| Packages | v1.10.2 Host ZIP and VSIX built from a fresh Review output directory. All **73 backend/package inputs and 5 VSIX source inputs** matched the current checkout; duplicate paths and private/rule/test/runtime inclusions were rejected. The extracted Host independently saved a synthetic model-bound task with a completed native snapshot, zero runs and zero generation calls. This did not reinstall dependencies or modify the user's installed Host. |

The native lifecycle decision was checked against the [VS Code 1.141.0 chat reducer](https://github.com/microsoft/vscode/blob/2a59476c9bfcb90b3ddc372c36762471b7dfad1c/src/vs/platform/agentHost/common/state/protocol/channels-chat/reducer.ts): completing the native turn ends its activity, while draft actions apply the supplied draft. Live progress/output and human review belong to Review; native reconnect snapshots derive saved output from the same runtime report. No later response is sent into a completed native turn.

Private receipts are under ignored `.tmp/v1102-repair-20261008-01/`. Install matching **v1.10.2 Host ZIP and VSIX**, update `frag.hostInstallation`, reload Agents and restart the project Host to apply these changes to an existing installation. The running user Host was not updated. Unsent drafts do not survive a Host process restart. Real-model, live FC, selected personal KB and human semantic acceptance were not run by this repair. Historical evidence below retains its own versions.

Proposed commit: `fix: preserve native drafts and separate Review task state in v1.10.2`

Cross-repo impact: **NONE**. Contract change: **ADDITIVE** cancellation endpoint; AHP remains 0.9.0 and saved Review contracts retain their format. Other repo status: **NOT_TOUCHED**. No FC compatible-version change is required.

## Native model binding repair — 2026-10-08

Baseline HEAD: `d024f78`; tracked working tree and staging were clean. The maintainer explicitly authorized the repair, v1.10.1 synchronization and related README updates. Scope: FRAG_ONLY. No dependency was added or upgraded; the maintainer's model configuration and credentials, FC files and phase acceptance were not changed. No commit or push was made. Synthetic configuration was created only in an isolated test profile.

The original failure was reproduced by synthetic AHP requests: native provisional `createSession` without `model` returned `Choose an available configured VS Code model.` The v1.10.1 Host accepts an unbound provisional session and validates an explicit current model on `chat/turnStarted`. Review can read that empty session, while preparing or executing a request requires a saved task. Missing selection, an unavailable model and catalog failure have separate errors; task persistence never dispatches a model. Explicit invalid creation models, effort overrides, stale approval bindings and model changes on a replayed turn remain rejected.

| Verification | Executed result and limit |
|---|---|
| Backend | **453 passed, 2 skipped**; repository-local fresh pytest base directory, dotenv disabled, synthetic sources/providers. Skips require separately supplied FC protocol release artifacts. Includes fixed and Research generation after model-free provisional creation, two-stage approvals, changed configuration, rejected selections and idempotent replay. |
| Frontend and bridge | **60 frontend / 19 bridge passed**. Existing exact-input, effort provenance, approval, origin/auth and lifecycle checks retained. |
| Builds and versions | Standalone and Review production builds, TypeScript, source size, module boundaries, safety, versions and README/diagram checks passed. Default Host paths, launcher health checks, VSIX, public version surfaces and native diagram title use 1.10.1. |
| Installed packages | Final Host ZIP initialized **55 unchanged locked production packages** in a new ignored test installation. Matching VSIX installed through the actual VS Code CLI into separate test user-data/extensions directories. Package payloads and installed bytes were compared; private rules, configuration, sources, tests and runtime data are excluded. The final installed backend independently passed unbound Review read, rejected preparation without a task, rejected Send without a model, and saved Send with an explicit model, with zero runs or generation calls. |
| Native desktop | The actual installed desktop was **VS Code 1.141.0**, commit `2a59476c9bfcb90b3ddc372c36762471b7dfad1c`. The extension's real Start command bound the explicitly selected test folder; Remote/Folders/OK selected FRAG and the synthetic model. Actual WebSocket capture confirmed `createSession` omitted `model`; native Send supplied the advertised bridge ID and displayed **Task saved**. One saved task, zero runs and zero real-provider calls. No evidence was selected or sent to a provider. |
| Visual | Installed Review at **570×900 and 960×900** showed the task and 1.10.1 title/footer, Archivo, no horizontal overflow, page errors, alerts or external requests. The unchanged native architecture diagram with its 1.10.1 title was inspected at 1440×1000. Native Task saved, Review and light diagram screenshots were inspected. |
| Stop | Actual **FRAG: Stop Project Host** removed its owned registration, made health unreachable and retained the test provider configuration. The isolated test window was closed; test profiles/state/installations were retained without deletion. |

This desktop check establishes provisional creation and native task persistence on 1.141.0, not real-provider authentication, generation, billing, saved effort execution or full upgrade compatibility. The original 1.140.0 model-API source review and historical receipts below retain their own versions and boundaries. The maintainer's ordinary and dedicated model files were not modified. Applying the repair to an existing user installation still requires matching 1.10.1 Host and VSIX packages, an updated `frag.hostInstallation` and an Agents reload.

Private receipts and new packages: ignored `.tmp/v1101-repair-20261008-01/`. [Model identity and binding](MODEL-CONFIGURATION.md) explains the supplier/Frag double listing. No automatic deletion, provider replacement, fallback, retry or semantic acceptance was added.

Proposed commit: `fix: bind native VS Code task models after provisional creation in v1.10.1`

Cross-repo impact: **NONE**. Contract change: **ADDITIVE** acceptance of unbound provisional creation; explicit model selection remains required on native Send. Other repo status: **NOT_TOUCHED**. No FC compatible-version change is required.

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
