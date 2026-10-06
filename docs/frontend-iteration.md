# Frontend iteration without changing governed behavior

This document prepares a later visual iteration of Harness, RAG Lab, Runs, Memory and Plugins in a light, clear professional style. An introductory landing page is outside this scope. Navigation, typography, exact colors, component references and assets remain design decisions under discussion; implementation of the visual redesign awaits a confirmed brief. Phase 8 keeps the existing React/Vite application and backend contracts while adding explicitly selected local-source retrieval to RAG Lab.

## Existing ownership

| Surface | Current owner | Observable journey to preserve |
| --- | --- | --- |
| Application shell | `src/App.tsx`, `src/styles.css` | Harness, RAG Lab, Runs, Memory and Plugins remain reachable; backend availability is visible. |
| Source review | `src/features/harness/HarnessPanel.tsx` | Select a file and locators or a plugin scope and records; inspect the exact request; separately approve Context and Inference. |
| Retrieval | `src/components/analysis/RagLab.tsx` | Explicitly build an index, search, inspect evidence and separately approve both model stages. The bundled synthetic dataset remains available. |
| History and Research | `src/features/runtime/RuntimePanel.tsx` | Inspect persisted Runs; continue each Research turn with a new preview; review, revise, recover or export a structured report. |
| Reviewed memory | `src/features/memory/MemoryPanel.tsx`, `MemoryPicker.tsx` | Create and edit a candidate, review and promote it, then explicitly confirm an applicable version for a new request. |
| Optional plugins | `src/features/plugins/PluginPanel.tsx` | Verify a pinned archive; inspect activation state; disable immediately; obtain manual removal instructions. |
| Exact request display | `src/components/common/PreparedCallPreview.tsx` | Display destination, model, request JSON and source/version bindings before an approval action. |

API clients under `src/api/` validate responses against `shared/contracts/`. Backend code owns authorization, execution, budgets, persistence and source validation. Page navigation currently mounts one page at a time. A transient selection or displayed approval is not durable state; saved Runs remain available through the Runs page.

## Visual starting point

The current interface uses Public Sans for controls and body text, and Libre Bodoni for display headings. Both families are local assets under `src/assets/fonts/`; their existing notices and publication decisions remain in force. A later font or dependency change requires its own license review.

The current application tokens in `src/styles/tokens.css` describe the existing dark baseline: canvas `#0a0a0a`, surface `#111111`, card `#171717`, raised surface `#222222`, primary text `#f5f5f5` and accent `#EFEEE7`. The later design will use a separately confirmed light palette. Preserve visible keyboard focus and the reduced-motion rule. Update coherent tokens when their visual role changes; add a token only for an actual recurring distinction.

The distinctive interaction is evidence review: source selection, exact request, approval and resulting report. Make that sequence easier to inspect before adding decoration. Preserve plain labels for actions and explicit missing, unknown, failed and unreviewed states. Structural validation and human semantic review must remain separately visible, including in a monochrome interface.

## Functional constraints for a later redesign

- Changing source kind, file, locators, plugin scope, query, checklist or confirmed memory invalidates the displayed preview. Late responses from an earlier selection cannot restore it.
- File discovery is not permission to parse, index or send every file. Index only explicitly selected locators after the build action. Keep synthetic and selected-source index identities distinct.
- A preview, search, memory recommendation, page change or index build makes no model call. Each displayed model request needs its own one-use approval. Cancelling confirmation makes no call.
- Research has serial host-validated tools and bounded turns; it stops for a new approval before each model request. Finance Core remains on the fixed read-only path.
- A new input creates a linked Run. A human revision preserves the original model output. Recovery revalidates sources and obtains a new approval; an unknown outcome cannot be resent automatically.
- Memory is reviewed background, not current evidence or permission. Source and Workspace isolation, version checks, conflict exclusion and explicit confirmation remain backend controls.
- Preserve retrieval `chunkId`, Context `evidenceId` and Inference `evidenceIds`. A correct identifier, source hash or valid schema does not establish factual support.
- Page, JSON and Markdown use the backend's structured report. Do not reconstruct a different report from rendered HTML.
- Credentials, private evidence and reusable approval tokens must not enter frontend storage, analytics, public assets or public fixtures. Finance mutations remain in Finance Core's standalone UI.

## Small iteration sequence

1. Refine the shell and existing spacing/type tokens. Check all five pages at desktop and narrow widths, keyboard focus, long IDs, empty states and backend failure before changing feature composition.
2. Refine source selection and request review together. Preserve all source limits, asynchronous selection guards and separate approval controls; check cancelled approvals and selection changes against real backend state.
3. Refine Runs, Memory and Plugins. Preserve current record ownership, review/revision distinctions, checkpoint rules, confirmed memory versions and immediate plugin disable behavior.

Keep each change within the current feature and its shared components. Split a component only when it has a distinct responsibility or actual reuse. Do not introduce a second routing/state framework, generic form factory or a new universal design system merely to prepare a later redesign.

Research and recovery currently accept explicit source-selection JSON. That is a usable advanced path, but a later source form can improve it. Such a form must produce the same validated request and preserve selection/version invalidation; it is a separate interaction change, not a reason to weaken the current backend contract.

## Verification and handoff

Run relevant frontend tests, TypeScript typecheck, architecture/privacy/version checks and a production build. For changes to user journeys, use a synthetic-only local backend and the real browser/API path: explicit source selection, index/search, exact preview, cancelled approval, separate approved stages, bounded Research with actual native/CLI tools, durable history, review, memory and report exports.

Inspect representative desktop and narrow screenshots rather than treating DOM containment as visual acceptance. Check visible keyboard focus, readable request JSON, labelled controls, selection limits and page/section overflow. Existing small text and compact controls deserve deliberate review during the later visual pass; offline functional checks do not establish full accessibility conformance or real-device acceptance.

Record deterministic tests, synthetic browser observations, visual review, real model calls, real KB support, live FC integration and human semantic acceptance separately. A Fake/scripted model can verify the host path; it cannot approve factual or financial correctness. Keep synthetic browser artifacts, source snapshots, exported reports and runtime databases Git-ignored. No frontend iteration publishes or deploys the project implicitly.
