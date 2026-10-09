# FRAG Review v1.10.4

FRAG Review is the new right-hand page for VS Code Agents. The standalone FRAG GUI keeps its existing layout and fonts. Both entry points reuse the same backend services; the installed route stores its project sessions, runs and review records separately from development state.

The delivery target is desktop VS Code and its resizable Browser pane. Mobile layouts and device testing are outside scope.

v1.10.4 repairs pointer selection in the shared GlideSelect, supplies the native error type, and shows saved tasks awaiting configuration in Runs without inventing a Run. Missing saved evidence disables preview with configuration guidance. The right navigation remains a fixed 192px text sidebar in narrow desktop panes; Memory expands inline rather than using an animated icon or flyout. Native attachments remain unsupported and are never read as evidence. Install both matching packages; a checkout edit does not update an installed Host.

## Open

**Host 1.10.4 + VSIX 1.10.4 must both be installed.** Updating the extension or checkout does not update an explicit saved `frag.hostInstallation` path. The Host ships install/upgrade steps in `resources/install.md`; the checkout guide is [here](../../integrations/vscode/README.md#upgrade-to-v1104).

1. Open the dedicated **Agents** instance. Run **FRAG: Start Project Host** → select the evidence folder → **Bind project**. Skip Start if this window already owns the Host.
2. Run **FRAG: Open Review** → paste the fresh URL into the right-hand **Browser address bar** → `Enter`.
3. Leave session selection empty and open **Settings** to save explicit evidence. A conversation is not required for configuration.
4. When ready: **New / Ctrl+N → folder-name button → Remote → FRAG → Folders → your project**. Select a configured model and send text without native Context attachments.
5. In Review, choose that session and prepare **Context**, then **Inference**, with a separate exact approval for each stage.

Ports change between starts. Do not reuse an old URL or clear Remote Host registrations to upgrade. If Browser says **Paused due to Notification**, close the VS Code notification and press `Ctrl+R` if needed. Files is not the Review page.

Keep the dedicated model file, credentials and project state. The installed route needs no checkout, backend `.env` or proposed API; native file/edit/terminal operations remain unsupported. A selected model is required at Send, not provisional session creation. Start and Send do not generate a model response.

## One shared workflow

**Workspace** combines the Context features previously presented separately in Harness and RAG Lab. Choose selected files, RAG retrieval or installed plugin evidence. File sections and plugin records remain explicit selections. Building a RAG index is a separate manual action; neither opening the page nor sending a task builds it.

Normal tasks use **Context → Inference → Review** after project evidence is saved in **Settings**. Before preparation, choose saved configuration or a special configuration for **Current run** (default) or **Conversation**. Special configuration uses **Evidence → Research (optional) → Context → Inference → Review**. Later tasks in an overridden conversation skip repeated Evidence editing and start Research or Context with fresh evidence and approvals. Inspect the provider, model, endpoint, exact model API arguments and bindings; check **I reviewed this exact request**, then approve that single stage. Preparing the next stage is another explicit action. Native Send and VS Code permission settings never approve a model call.

**Runs** is scoped to the selected native session. Before preparation it displays the current saved task and configuration status; successful preparation creates the Run, without calling a model. Empty history disables the saved-run selector. Output, requests, sources and review share one report. Human revisions preserve the original output. JSON and Markdown exports use the existing runtime report. Structural/citation checks and human semantic review remain separate outcomes.

The answer renders bounded Markdown: headings, paragraphs, emphasis, inline/fenced code, lists, quotes, tables and HTTP(S) links. Citation checks and notes are collapsed review details, including a visible count of missing-information gaps. Raw HTML remains escaped text; remote images are never fetched automatically. Saved model text and exports are unchanged. This renderer is original application code with no extra dependency; it does not claim full CommonMark support or nested-list syntax.

**Settings** saves application preferences (evidence mode, topK, optional Research strategy and checklist template) in the dedicated VS Code instance's shared preferences database. Concrete file/locator and plugin scopes are project-local. Conversation overrides stay in the project runtime store. Writes use revision compare-and-swap. Settings never runs Research or rebuilds an index automatically; index building remains a separate explicit action. Model readiness and the native configuration guide are here, but keys, providers, saved effort and safety budgets are not edited by FRAG. Changes affect future preparations, never an already frozen request.

**Memory** reuses one reviewed-memory controller with expandable **Candidates**, **Reviewed** and **History** entries. History includes retired records and read-only versions. Promotion selects the reviewed record; editing creates a new candidate version. It is reviewed model context, not standing evidence or approval. Plugin installation management is absent here. VS Code owns native Customizations; its MCP, Skills, Hooks and coding-tool registrations are not imported into this carrier. FRAG evidence-plugin selection remains in Workspace.

Models and saved effort are configured through VS Code. The request preview reports saved effort and exposes the exact stable API messages/options. Final provider HTTP, internal retries and usage are unknown. [Configuration requirements](../../integrations/vscode/MODEL-CONFIGURATION.md).

### Model setup before Context

1. In the same dedicated VS Code instance, use **Manage Language Models** to configure the intended provider/model and credentials. Preserve existing configuration; do not replace it with an empty file for normal use.
2. Verify `frag.modelConfigFile` points to that instance's `User/chatLanguageModels.json`. Configure saved effort there through VS Code, not in FRAG.
3. Select the configured model in the native FRAG conversation and send the task. **Settings → Model readiness → Refresh readiness** checks the model saved on that task, not a default-provider fallback. Change the native selection and send a new task if a different model is intended.
4. Save explicit project evidence in Settings. In Workspace, open **Checklist and background memory**; set each named blocking item to **Met** and confirm **Reviewed by me** only after your review. Templates never persist reviewed status.
5. Preview Context (or optional Research). Review the exact request and check consent for that single call. Zero evidence, stale bindings and missing approvals cannot be bypassed. Readiness enumeration alone does not establish authentication, billing or output quality.

## Stop, reload and recovery

Native Send completes immediately with a task receipt. Review separately displays Choose task configuration or Waiting for approval, with zero model calls while waiting. Use Cancel task in Review to pause the workflow at the next safe host boundary; it cannot retract an already dispatched external request. Cancelled tasks show recovery steps and hide evidence/approval controls. Sending a new native task switches this page automatically and cancels the previous unfinished task, invalidating its approval. A reconnect restores completed native receipts and saved Review state without preparing or sending a model request.

Unsent text and Context descriptors remain volatile for same-process reconnects only; they are never saved to disk or read as evidence. Native attachments produce a specific removal/reselection error, rather than a text-length error.

The completed native conversation is a delivery summary. Later human review and revisions are authoritative in the Review/Runs page; the completed native message is not a live report editor. Only record semantic acceptance after your own review.

Approval tokens exist only in the running backend. A backend restart requires a newly prepared preview and a fresh approval. Stale task/session/run controls are rejected. Source revisions are revalidated by the existing flow. Unknown external outcomes never resend automatically. After completion or cancellation, send a new native task for another workflow; changing from Harness to RAG after a run has started also requires a new task.

## Files and design

```text
src/agents/
  AgentReviewApp.tsx             Entry and page composition
  components/
    Navigation.tsx              Fixed text sidebar, inline Memory, progress Stepper
    ReviewSettings.tsx          Revision-bound application/project defaults
    reactbits/                  Adapted approved component JSX, types and scoped CSS
    EvidencePicker.tsx          File, retrieval and plugin selection
    ReviewWorkflow.tsx          Shared exact-preview and approval flow
    ReviewReport.tsx            Output, requests, sources and human review
    ReviewMarkdown.tsx          Safe model text and collapsed review annotations
  styles.css                    Scoped layout and component styles
  navigation.css                Sticky entries and fixed desktop text navigation
  fonts.css                     Archivo font-face definitions
  README.md
src/api/agentClient.ts           Validated carrier/review HTTP client
shared/contracts/agents.ts      Carrier and review response contracts
public/agents/                  Font assets and distributed notices
```

The layout integrates the supplied React Bits **LineSidebar, BranchedMenu, GlideSelect and Stepper** code, retaining pointer/keyboard selection, branching paths, proximity animation and Motion indicators. GlassIcons source remains available but is not rendered by this page. Application adapters add controlled state, bounded menus, keyboard controls, reduced motion and ResizeObserver height updates. Original JSX is paired with typed application interfaces; CSS is scoped to `.review-root`. No Hugeicons package is installed. **motion 12.23.21**, **framer-motion 12.23.21**, **motion-dom 12.23.21**, **motion-utils 12.23.6** and **tslib 2.8.1** are locked, including overrides for the upstream wide ranges.

Main content owns scrolling; the page and the fixed 192px text sidebar do not become additional scroll containers. Short desktop panes use compact navigation spacing, and Memory expands inline without changing the sidebar width. Step entries, **Back to view**, **Current stage**, Output and Settings stay sticky with 12px glass blur; task titles and JSON do not. Output/Requests/Sources/Review live in a separate Run report area. Back only reads snapshots, never prepares, recovers, changes inputs or resends a call. Current-task drafts survive page navigation; approval consent does not. Styling is scoped to `.review-root` so this entry does not restyle the standalone application. The native chat/Browser split is owned by VS Code; set the divider to an approximately equal split there, not through this page.

All ordinary text uses **Archivo Variable 5.3.0**, normal style, variable weight **100–900**, with `Archivo, Arial, sans-serif` fallbacks. The three unchanged Latin, extended Latin and Vietnamese WOFF2 files match the source font package. Code uses the system monospace stack. Neither Public Sans nor Libre Bodoni is used by this page.

## Notices

The adapted supplied React Bits components are integrated into this application, not offered as a standalone component bundle. Their [MIT + Commons Clause notice](../../public/agents/REACT-BITS-LICENSE.md) is shipped under `/agents/REACT-BITS-LICENSE.md`. The authoritative license snapshot is pinned to `8f6effa3f407113cc75ad63c2ce52ae3c2689624` in the [React Bits repository](https://github.com/DavidHDev/react-bits/blob/8f6effa3f407113cc75ad63c2ce52ae3c2689624/LICENSE.md).

Archivo uses [SIL OFL 1.1](https://github.com/Omnibus-Type/Archivo/blob/master/OFL.txt). Its complete package copyright/license is shipped as `/agents/fonts/ARCHIVO-OFL.txt`. This requires retaining the font notice and font license, not disclosure of FRAG's own source. The user approved required notices for this GUI and explicitly selected this font source. See [asset provenance](../../public/agents/THIRD_PARTY_NOTICES.txt).

## Compatibility

The carrier is pinned to the verified **VS Code 1.140.0** build and **AHP 0.9.0**. It is a bounded FRAG evidence harness, not a general AHP filesystem, terminal or coding agent. Unsupported operations return protocol errors. VS Code can show a terminal-unavailable notification for the bound remote project. Recheck native discovery, session creation, message ownership, Browser placement and output rendering after a VS Code update.
