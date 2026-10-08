# FRAG Review v1.10.3

FRAG Review is the new right-hand page for VS Code Agents. The standalone FRAG GUI keeps its existing layout and fonts. Both entry points reuse the same backend services; the installed route stores its project sessions, runs and review records separately from development state.

The delivery target is desktop VS Code and its resizable Browser pane. Mobile layouts and device testing are outside scope.

## Open

Install the matching Host ZIP and VSIX, enable the extension for the Agents window, reload, and run **FRAG: Start Project Host**. Choose a separate evidence folder. A native session is not required to start the Host or open Review.

### Configure before creating or opening a session

1. In the dedicated **Agents** window, run **FRAG: Start Project Host** and **Bind project** from the welcome screen; skip Start if this window already owns the running Host. A bound evidence project is still required.
2. Run **FRAG: Open Review**. It copies the running Host's `/review` URL and attempts to open a right-hand Browser tab; it does not create a session or navigate the Browser automatically.
3. Paste the URL into the **Browser address bar** and press `Enter`. If Files/Changes is visible instead, open Browser using the right pane's `+` menu. Do not paste into the composer or Files search, and do not reuse an old Host port.
4. Leave **Select a native session** empty and open **Settings** in the right navigation (Settings icon in a narrow pane). Save application preferences and explicit project evidence. Model readiness is Not checked until a native task has a saved model selection. No New, conversation selection or Send is required here.
5. Create a conversation only when ready for a task, or run **FRAG: Stop Project Host** after configuration only. Start may enumerate configured models but does not generate a model response. Opening Review and saving Settings do not run model stages or automatically build an index.

### Find the current address and unblock Browser

The installed Host uses a dynamic port, not a fixed README port. In the dedicated **Agents** window, run `Ctrl+Shift+P` → **FRAG: Open Review** to copy the current complete URL, then paste it into the Browser address bar. Its format is `http://127.0.0.1:<current-port>/review`; `<current-port>` is a placeholder, not text to enter. Read the actual port from the freshly pasted URL. Repeat Open Review after a Host restart; Browser history and old session links can point to a stopped Host. If the command says **Run FRAG: Start Project Host first**, start and bind the intended project, then retry.

If Browser shows **Paused due to Notification / Dismiss the notification to continue using the browser**, dismiss the VS Code notification using its close button (including **FRAG Review URL copied...**). Keep the current URL and press `Ctrl+R` in Browser if the page does not resume. This pause is not evidence of a port error or a session requirement. The current copied-URL notification says to select a FRAG session, but that selection is needed only for task review: leave it empty and open **Settings** for advance configuration.

The native Files view is not FRAG Review. FRAG deliberately rejects terminals/native coding tools; a terminal-unavailable notification is not a Review opening failure. Use Open Review rather than Run Task or a terminal.

### Enter a task when ready

In **New / Ctrl+N**, use the folder-name button above the composer: **Remote → FRAG → Folders → your project**. Choose a configured model and send a task. Then select the matching saved session in Review to prepare and separately approve its model stages. Session selection is required for task/run controls, not for the Settings entry above.

[Installation and exact picker steps](../../integrations/vscode/README.md). The installed route needs no source checkout, backend `.env`, proposed extension API or VS Code modification. The advertised directory is the bound project; native file/edit/terminal operations remain unsupported.

v1.10.3 permits an unbound native provisional session, but Send must explicitly select a currently available configured model before a task is saved. Send performs zero model calls; Review owns each later preview and approval. Missing selection, stale model IDs and catalog lookup failures have separate messages. Install matching v1.10.3 Host and VSIX packages to apply this repair; editing the checkout does not update an installed Host.

The native model manager can show the same model under its supplier and **Frag**. Frag is the running Host's bridge entry over the dedicated instance's bound `chatLanguageModels.json`, not another provider configuration. Stopping the Host withdraws that entry; supplier credentials and saved project state remain. [Configuration and model identity](../../integrations/vscode/MODEL-CONFIGURATION.md).

## One shared workflow

**Workspace** combines the Context features previously presented separately in Harness and RAG Lab. Choose selected files, RAG retrieval or installed plugin evidence. File sections and plugin records remain explicit selections. Building a RAG index is a separate manual action; neither opening the page nor sending a task builds it.

Normal tasks use **Context → Inference → Review** after project evidence is saved in **Settings**. Before preparation, choose saved configuration or a special configuration for **Current run** (default) or **Conversation**. Special configuration uses **Evidence → Research (optional) → Context → Inference → Review**. Later tasks in an overridden conversation skip repeated Evidence editing and start Research or Context with fresh evidence and approvals. Inspect the provider, model, endpoint, exact model API arguments and bindings; check **I reviewed this exact request**, then approve that single stage. Preparing the next stage is another explicit action. Native Send and VS Code permission settings never approve a model call.

**Runs** is scoped to the selected native session. Output, requests, sources and review share one report. Human revisions preserve the original output. JSON and Markdown exports use the existing runtime report. Structural/citation checks and human semantic review remain separate outcomes.

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
    Navigation.tsx              Line Sidebar, Glass Icons, progress Stepper
    ReviewSettings.tsx          Revision-bound application/project defaults
    reactbits/                  Adapted approved component JSX, types and scoped CSS
    EvidencePicker.tsx          File, retrieval and plugin selection
    ReviewWorkflow.tsx          Shared exact-preview and approval flow
    ReviewReport.tsx            Output, requests, sources and human review
    ReviewMarkdown.tsx          Safe model text and collapsed review annotations
  styles.css                    Scoped layout and component styles
  navigation.css                Sticky entries, responsive rail and Memory flyout
  fonts.css                     Archivo font-face definitions
  README.md
src/api/agentClient.ts           Validated carrier/review HTTP client
shared/contracts/agents.ts      Carrier and review response contracts
public/agents/                  Font assets and distributed notices
```

The layout integrates the supplied React Bits **LineSidebar, GlassIcons, BranchedMenu, GlideSelect and Stepper** code, retaining the pointer/keyboard selection, branching paths, proximity animation, glass layers and Motion indicators. Application adapters add controlled state, bounded menus, keyboard controls, reduced motion and ResizeObserver height updates. Original JSX is paired with typed application interfaces; CSS is scoped to `.review-root`. Hugeicons demo dependencies are replaced by local SVG paths; no Hugeicons package is installed. **motion 12.23.21**, **framer-motion 12.23.21**, **motion-dom 12.23.21**, **motion-utils 12.23.6** and **tslib 2.8.1** are locked, including overrides for the upstream wide ranges.

Main content owns scrolling. Step entries, **Back to view**, **Current stage**, Output and Settings stay sticky with 12px glass blur; task titles and JSON do not. Output/Requests/Sources/Review live in a separate Run report area. Back only reads snapshots, never prepares, recovers, changes inputs or resends a call. At widths below 800px the 192px sidebar becomes a 60px icon rail with a Memory flyout (up to 264px), Escape/outside-click closing and focus return. Current-task drafts survive page navigation; approval consent does not. Styling is scoped to `.review-root` so this entry does not restyle the standalone application.

All ordinary text uses **Archivo Variable 5.3.0**, normal style, variable weight **100–900**, with `Archivo, Arial, sans-serif` fallbacks. The three unchanged Latin, extended Latin and Vietnamese WOFF2 files match the source font package. Code uses the system monospace stack. Neither Public Sans nor Libre Bodoni is used by this page.

## Notices

The adapted supplied React Bits components are integrated into this application, not offered as a standalone component bundle. Their [MIT + Commons Clause notice](../../public/agents/REACT-BITS-LICENSE.md) is shipped under `/agents/REACT-BITS-LICENSE.md`. The authoritative license snapshot is pinned to `8f6effa3f407113cc75ad63c2ce52ae3c2689624` in the [React Bits repository](https://github.com/DavidHDev/react-bits/blob/8f6effa3f407113cc75ad63c2ce52ae3c2689624/LICENSE.md).

Archivo uses [SIL OFL 1.1](https://github.com/Omnibus-Type/Archivo/blob/master/OFL.txt). Its complete package copyright/license is shipped as `/agents/fonts/ARCHIVO-OFL.txt`. This requires retaining the font notice and font license, not disclosure of FRAG's own source. The user approved required notices for this GUI and explicitly selected this font source. See [asset provenance](../../public/agents/THIRD_PARTY_NOTICES.txt).

## Compatibility

The carrier is pinned to the verified **VS Code 1.140.0** build and **AHP 0.9.0**. It is a bounded FRAG evidence harness, not a general AHP filesystem, terminal or coding agent. Unsupported operations return protocol errors. VS Code can show a terminal-unavailable notification for the bound remote project. Recheck native discovery, session creation, message ownership, Browser placement and output rendering after a VS Code update.
