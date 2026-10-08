# Plan E: installed FRAG in native VS Code Agents

Target: **v1.10.1**. Scope: **FRAG_ONLY**. Finance Core source, storage, contracts and release remain untouched. Commits, pushes, tags and releases belong to the maintainer.

| Decision | Implementation boundary |
|---|---|
| Role | Selected-evidence conversation; no native edit, terminal or coding-tool bridge |
| Entry | Private local VSIX manages a loopback Host under Remote; review uses the right-hand Browser |
| Installation | Program bundle independent of the source checkout |
| Project | Explicit folder binding; advertise that root only |
| State | Local extension storage keyed by canonical project path; separate runtime/RAG/plugin directories |
| Models | Stable `vscode.lm`; same selected model for all stages |
| Reasoning | Saved VS Code model default; no temporary FRAG effort override |
| Approval | Exact model API arguments, fresh one-use approval for every stage |
| UI | Right navigation, grayscale transparent Glass Icons, Archivo; Workspace/Runs/Memory |
| Platform | Desktop VS Code and resizable review pane; no mobile-specific design or device acceptance |
| Shared workflow | Harness/RAG evidence, Context, Inference and review share existing services |
| Pi retirement | No executable worker/adapter/dependencies; historical reports readable only |
| Customizations | Native surfaces retained; MCP/Skills/Hooks/tool import deferred |

Delivery includes the Host ZIP, VSIX, installation instructions, model configuration requirements, UI and architecture documentation, synthetic bridge/host/security checks, and review evidence. The packages use existing locked dependencies and approved component/font notices. No installer framework or orchestration runtime is added. Python and locked backend wheels are initialized separately.

Acceptance separates source/manifest reasoning compatibility, synthetic consumer calls, installed-package startup, real native discovery/UI behavior and human real-provider review. The maintainer's prior runtime real-model acceptance is recorded separately; it does not establish new bridge wire behavior. Supplier HTTP body, retries, billing and relay-side reasoning execution remain unknown at this boundary.

Review and runtime reports remain authoritative. Restart discards approvals, source/configuration changes reject continuation, unknown outcomes never resend, and no model can expand selected file/locator scope or promote memory. Private settings, project rules, generated directories and linked paths are excluded from installed project evidence.

See [installation](../integrations/vscode/README.md), [model configuration](../integrations/vscode/MODEL-CONFIGURATION.md), [review UI](../src/agents/README.md) and [architecture](architecture/vscode-migration/architecture.html).

[Delivery checks and acceptance limits](../integrations/vscode/PLAN-E-VERIFICATION.md).
