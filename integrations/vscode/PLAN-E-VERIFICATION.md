# Plan E verification — v1.10.0

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
