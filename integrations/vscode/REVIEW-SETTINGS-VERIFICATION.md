# Review settings and navigation verification — v1.10.3

Date: 2026-10-08. Baseline: `a67976d`, initially clean working tree and staging. Scope: **FRAG_ONLY**. The maintainer approved the layered Settings workflow, read-only Back, fixed entries, expandable Memory and the named React Bits/Motion versions with their distributed notices. The narrow-rail/Memory-flyout screenshot was approved visually; this is not human acceptance of model output or a phase advance.

## Delivered behavior

- Settings stores shared application preferences within the dedicated VS Code instance, explicit project-local evidence and checklist templates. Research is a strategy setting, not execution. Saving never calls a model or builds an index. Keys, provider routes, effort, safety limits and plugin installation are not editable here.
- Normal tasks use **Context → Inference → Review**. Special configuration uses **Evidence → Research (optional) → Context → Inference → Review**, scoped to the current run by default or explicitly to the conversation. Subsequent conversation tasks reread sources and bind fresh requests; they do not reuse old Research, Context or native history.
- Settings writes and preparation compare displayed application/project/conversation revisions. The optional outer report configuration audit does not change SelectionSnapshot, SourceBinding, frozen request bodies, bindings or their digest defaults. Legacy runs remain read-only; legacy previews are not reactivated by the new page.
- Back and reached Stepper entries only view saved snapshots. They never prepare, recover, edit, roll back or resend. Step entries, Back/current stage and Output/Settings are sticky with glass blur; reports have a separate Output/Requests/Sources/Review area.
- Approval consent clears on page navigation, preview/carrier changes and report-version changes. Every Research turn, Context and Inference still requires a fresh exact approval. Blocking items and model setup have actionable explanations. Zero-hit Research cannot regain approval through recovery, and fresh-source warnings are retained.
- The adapted original LineSidebar, GlassIcons, BranchedMenu, GlideSelect and Stepper code is active, with keyboard/pointer interaction, basic motion, controlled-state adapters, scoped CSS and reduced motion. Below 800px the 192px sidebar becomes a 60px icon rail; Memory has a bounded flyout. Candidates, Reviewed and History reuse one controller; history includes retired records and read-only versions. Promotion selects Reviewed; editing returns to Candidates.
- Sources uses **Source revisions and assessments**, avoiding the literal `&` copy issue. The standalone application's layout is retained.

## Executed checks

| Layer | Result and boundary |
| --- | --- |
| Backend | **473 passed, 2 skipped** with repository-local pytest storage and dotenv disabled. Synthetic tests cover zero-model saves, revision conflicts, strict source/origin validation, shared preferences/project isolation, conversation/run overrides, fresh next-task bindings, reset checklist templates and zero-hit Research recovery rejection. The skips require separately supplied FC protocol artifacts. |
| Frontend | **67 passed**, including exact request/token boundaries, layered revision-bound clients, legacy read-only runs and actionable blocking/setup copy. |
| Native bridge source | **19 passed**. Existing one-use, saved model identity, request-shape, origin, environment and command checks remain in place. These are not new installed VSIX desktop acceptance. |
| Build and repository gates | Standalone and Review production builds, TypeScript, size, module boundaries, version synchronization, privacy and README diagram checks passed. |
| Real browser, synthetic backend | Headless installed Edge at **570×900, 960×900 and 570×500**: no horizontal overflow or page errors; sticky entries remain visible while scrolling. Keyboard GlideSelect, Memory flyout/Escape/outside-click/focus return, short-pane flyout bounds, draft retention across navigation and consent clearing passed. Outside clicks on interactive controls retain their normal focus. Back caused no mutation request. |
| Workflow/browser | Normal flow used exactly two separately approved Fake calls. Special Conversation flow used **Research → Research → Context → Inference**, with explicit approvals and actual bounded selected-source tool observations. Memory candidate creation, human-fixture promotion, edit, retirement and four read-only versions passed under reduced motion. Fake results do not establish factual support or human semantic acceptance. |
| Candidate package | ZIP/VSIX contents, versions and source bytes matched; original distributed license bytes and privacy exclusions were verified. The previous v1.10.2 package hashes remain unchanged. |
| Packaged CLI | Extracted candidate Host backend plus candidate bridge started on an owned loopback port, served Review/help, saved separate shared preferences, rejected stale CAS writes and retained preferences after owned shutdown. Empty dedicated model configuration caused **zero model discovery and zero model calls**. It reused the existing locked Python environment; it was not a fresh dependency installation or a switch of the installed Host. |

## Approved dependency boundary

React Bits source pin: `8f6effa3f407113cc75ad63c2ce52ae3c2689624`, [official MIT + Commons Clause terms](https://github.com/DavidHDev/react-bits/blob/8f6effa3f407113cc75ad63c2ce52ae3c2689624/LICENSE.md). Components are integrated into FRAG, not offered as a standalone component product.

Locked versions: **motion 12.23.21**, **framer-motion 12.23.21**, **motion-dom 12.23.21**, **motion-utils 12.23.6** and **tslib 2.8.1**. Packaging rejects other installed/locked versions and changed original license bytes. [Motion source/licenses](https://github.com/motiondivision/motion/tree/v12.23.21/packages), [motion-utils source/license](https://github.com/motiondivision/motion/tree/v12.23.6/packages/motion-utils), [tslib 0BSD terms](https://github.com/microsoft/tslib/blob/v2.8.1/LICENSE.txt). Complete notices are distributed with the Review assets and Host licenses. No Hugeicons dependency or FRAG source disclosure was introduced.

The npm audit snapshot reports **7 existing development-tool dependency findings: 2 critical, 2 high and 3 moderate**. They concern concurrently/shell-quote, browserslist/source-map-js, vitest/@vitest/mocker and baseline-browser-mapping. No finding was reported for the locked animation tuple in that snapshot. No automatic fix or dependency upgrade was performed; remediation needs separately scoped version/license review. This is not a claim that the project is security-clean.

## Candidate artifacts and remaining acceptance

Artifacts are generated under the ignored `.tmp/packages/` directory; `receipt-1.10.3.json` records SHA-256, byte size and write time. v1.10.2 artifacts and their versioned receipt are retained.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| `frag-host-1.10.3.zip` | 442361 | `b373286d4921b442094aeee3769897347b1b382cc3c71d07c690cf0aa5a989aa` |
| `frag-bridge-1.10.3.vsix` | 13906 | `94d5f5a7135097585d7707b76819eb9db5997e837d10bea5059c1030fe4a4451` |

To try the candidate, follow the [matching-component upgrade steps](README.md): stop the owned old Host, install the new Host in a separate directory, point the dedicated instance to it, install the matching VSIX and reload Agents. Preserve existing dedicated paths and model configuration. The source task did **not** perform this switch. Existing selected-model/provider compatibility, live authentication/billing and human-semantic acceptance still require the maintainer's deliberate test. No real-provider call, FC edit, commit, push, deployment, tag, source publication or phase advance was performed.

```text
Cross-repo impact: NONE
Contract change: ADDITIVE (FRAG Settings APIs and optional report envelope only)
Other repo status: NOT_TOUCHED
Required compatible version: matching FRAG Host and VSIX 1.10.3
Reason: application-local settings/navigation repair; no FC contract change
Prompt for the other repo: None
```

Proposed commit: `feat: add layered Review settings and governed navigation in v1.10.3`
