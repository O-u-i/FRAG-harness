# FRAG Review

FRAG Review is the new right-hand page for VS Code Agents. The standalone FRAG GUI keeps its existing layout and fonts. Both entry points reuse the same backend services; the installed route stores its project sessions, runs and review records separately from development state.

The delivery target is desktop VS Code and its resizable Browser pane. Mobile layouts and device testing are outside scope.

## Open

Install the matching Host ZIP and VSIX, enable the extension for the Agents window, reload, and run **FRAG: Start Project Host**. Choose a separate evidence folder. In **New / Ctrl+N**, use the folder-name button above the composer: **Remote → FRAG → Folders → your project**. Send a task, run **FRAG: Open Review**, and paste the copied URL into the native right-hand Browser address bar.

[Installation and exact picker steps](../../integrations/vscode/README.md). The installed route needs no source checkout, backend `.env`, proposed extension API or VS Code modification. The advertised directory is the bound project; native file/edit/terminal operations remain unsupported.

## One shared workflow

**Workspace** combines the Context features previously presented separately in Harness and RAG Lab. Choose selected files, RAG retrieval or installed plugin evidence. File sections and plugin records remain explicit selections. Building a RAG index is a separate manual action; neither opening the page nor sending a task builds it.

The same steps show **Evidence → Context → Inference → Review**. Optional Research runs before Context and still requires approval for each model turn. Inspect the provider, model, endpoint, exact model API arguments and bindings; check **I reviewed this exact request**, then approve that single stage. Preparing the next stage is another explicit action. Native Send and VS Code permission settings never approve a model call.

**Runs** is scoped to the selected native session. Output, requests, sources and review share one report. Human revisions preserve the original output. JSON and Markdown exports use the existing runtime report. Structural/citation checks and human semantic review remain separate outcomes.

The answer renders bounded Markdown: headings, paragraphs, emphasis, inline/fenced code, lists, quotes, tables and HTTP(S) links. Citation checks and notes are collapsed review details, including a visible count of missing-information gaps. Raw HTML remains escaped text; remote images are never fetched automatically. Saved model text and exports are unchanged. This renderer is original application code with no extra dependency; it does not claim full CommonMark support or nested-list syntax.

**Memory** reuses FRAG's reviewed memory service. Navigation sits on the right; adapted Glass Icons use `colorful={false}` with gray transparent faces. Models and Plugins management are absent here. VS Code owns native Customizations; its MCP, Skills, Hooks and coding-tool registrations are not imported into this carrier. FRAG evidence-plugin selection remains in Workspace.

Models and saved effort are configured through VS Code. The request preview reports saved effort and exposes the exact stable API messages/options. Final provider HTTP, internal retries and usage are unknown. [Configuration requirements](../../integrations/vscode/MODEL-CONFIGURATION.md).

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
    ReviewMarkdown.tsx          Safe model text and collapsed review annotations
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

The carrier is pinned to the verified **VS Code 1.140.0** build and **AHP 0.9.0**. It is a bounded FRAG evidence harness, not a general AHP filesystem, terminal or coding agent. Unsupported operations return protocol errors. VS Code can show a terminal-unavailable notification for the bound remote project. Recheck native discovery, session creation, message ownership, Browser placement and output rendering after a VS Code update.
