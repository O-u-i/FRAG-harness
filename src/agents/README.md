# FRAG Review

FRAG Review is the new right-hand page for VS Code Agents. The standalone FRAG GUI keeps its existing layout and fonts. Both entry points use the same backend, durable sessions, runs and human review records.

## Open

Run `npm run agents` from the repository root. Merge the generated, ignored `.local-runtime/vscode/connection.settings.json` entries into the native Agents settings, preserving any other hosts. Select **Remote → FRAG → Folders → frag-workspace**, then send a task of 3–500 characters. Open **Sessions: Browser** (`Ctrl+Shift+B` on the verified Windows build) and enter the review URL shown by FRAG, or use `http://127.0.0.1:8787/review` to select a native session.

This route needs no VSIX, proposed extension API or VS Code source modification. Start the host before selecting its folder. The empty virtual workspace does not expose the repository, personal files or terminal commands.

## One shared workflow

**Workspace** combines the Context features previously presented separately in Harness and RAG Lab. Choose selected files, RAG retrieval or installed plugin evidence. File sections and plugin records remain explicit selections. Building a RAG index is a separate manual action; neither opening the page nor sending a task builds it.

The same steps show **Evidence → Context → Inference → Review**. Optional Research runs before Context and still requires approval for each model turn. Inspect the provider, model, endpoint, full request body and bindings; check **I reviewed this exact request**, then approve that single stage. Preparing the next stage is another explicit action. Native Send and VS Code permission settings never approve a model call.

**Runs** is scoped to the selected native session. Output, requests, sources and review share one report. Human revisions preserve the original output. JSON and Markdown exports use the existing runtime report. Structural/citation checks and human semantic review remain separate outcomes.

**Customizations** groups Memory, Plugins and model-route readiness. These reuse FRAG's existing services with the new page styling. Native VS Code skills, MCP, hooks and client tool descriptions are not automatically imported or executed; this carrier has no native coding-tool or terminal bridge. The native shell may still discover global customizations on its own.

## Stop, reload and recovery

The central native turn waits for review and displays saved run progress. Its Stop action pauses the run at the next safe host boundary; it cannot retract an already dispatched external request. A reconnect restores carrier metadata and derives its answer from the same runtime report, without preparing or sending a model request.

The completed native conversation is a delivery summary. Later human review and revisions are authoritative in the Review/Runs page; the completed native message is not a live report editor. Only record semantic acceptance after your own review.

Approval tokens exist only in the running backend. A backend restart requires a newly prepared preview and a fresh approval. Stale task/session/run controls are rejected. Source revisions are revalidated by the existing flow. Unknown external outcomes never resend automatically. After completion or cancellation, send a new native task for another workflow; changing from Harness to RAG after a run has started also requires a new task.

## Files and design

```text
src/agents/
  AgentReviewApp.tsx             Entry and page composition
  components/
    Navigation.tsx              Line Sidebar, Glass Icons, progress Stepper
    EvidencePicker.tsx          File, retrieval and plugin selection
    ReviewWorkflow.tsx          Shared exact-preview and approval flow
    ReviewReport.tsx            Output, requests, sources and human review
  styles.css                    Scoped layout and component styles
  fonts.css                     Archivo font-face definitions
  README.md
src/api/agentClient.ts           Validated carrier/review HTTP client
shared/contracts/agents.ts      Carrier and review response contracts
public/agents/                  Font assets and distributed notices
```

The layout uses the supplied component references: adapted LineSidebar and GlassIcons, an original dependency-free progress Stepper, branched Customizations and native select controls styled for compact selection. The supplied animation and Hugeicons packages are not installed. Styling is scoped to `.review-root` so this entry does not restyle the standalone application.

All ordinary text uses **Archivo Variable 5.3.0**, normal style, variable weight **100–900**, with `Archivo, Arial, sans-serif` fallbacks. The three unchanged Latin, extended Latin and Vietnamese WOFF2 files match the source font package. Code uses the system monospace stack. Neither Public Sans nor Libre Bodoni is used by this page.

## Notices

The adapted supplied React Bits components are integrated into this application, not offered as a standalone component bundle. Their [MIT + Commons Clause notice](../../public/agents/REACT-BITS-LICENSE.md) is shipped under `/agents/REACT-BITS-LICENSE.md`. The authoritative license snapshot is pinned to `63a008de65732d73010bd219d25d15c47739bb31` in the [React Bits repository](https://github.com/DavidHDev/react-bits/blob/63a008de65732d73010bd219d25d15c47739bb31/LICENSE.md).

Archivo uses [SIL OFL 1.1](https://github.com/Omnibus-Type/Archivo/blob/master/OFL.txt). Its complete package copyright/license is shipped as `/agents/fonts/ARCHIVO-OFL.txt`. This requires retaining the font notice and font license, not disclosure of FRAG's own source. The user approved required notices for this GUI and explicitly selected this font source. See [asset provenance](../../public/agents/THIRD_PARTY_NOTICES.txt).

## Compatibility

The carrier is pinned to the verified **VS Code 1.140.0** build and **AHP 0.9.0**. It is a bounded FRAG evidence harness, not a general AHP filesystem, terminal or coding agent. Unsupported operations return protocol errors. VS Code can show a terminal-unavailable notification for the virtual remote workspace. Recheck native discovery, session creation, message ownership, Browser placement and output rendering after a VS Code update.
