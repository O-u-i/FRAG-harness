# FRAG Review v1.10.4 repair verification

Scope: FRAG_ONLY. This is a local repair and matching candidate-package handoff, not an installed desktop switch, provider acceptance or Phase 8 acceptance. Earlier v1.10.3 evidence remains in [its historical report](REVIEW-SETTINGS-VERIFICATION.md).

## Changes

- Shared GlideSelect preserves combobox focus through pointer selection and measures the live list position instead of double-counting scroll offsets. Keyboard selection, Escape and selected-value behavior remain intact.
- Native notification send errors include `errorType: invalidRequest`. Text-only submission works; nonempty native attachments remain rejected without reading their contents. The original failing desktop attachment descriptors were not captured, so this does not claim a verified pure-text false-positive repair.
- Runs displays the current task before its first successful preview, with its waiting/cancelled state and a Workspace action. It does not invent an execution record. Saved Run/report refreshes remain bound to the selected native session.
- Missing saved evidence disables preview with explicit configuration guidance. Backend contracts, source binding and one-use approvals remain authoritative.
- The right sidebar is fixed at 192px with text entries and inline Memory. The icon rail/flyout is not rendered. Only main content owns page scrolling; bounded lists and JSON can still scroll locally. The native chat/Browser split remains a VS Code divider, not a webpage-controlled layout.
- Version surfaces and matching Host/VSIX use v1.10.4. No dependency version or license handling changed; existing approved notices are retained.

## Executed checks

| Layer | Result and boundary |
| --- | --- |
| Frontend | 70 tests passed. Waiting/cancelled task history, fixed navigation and missing-source guidance have focused regressions. |
| Backend | Final full rerun: 474 passed, 2 skipped. Focused composer/settings: 21 passed. First full run had one SQLite raw-file equality failure in the existing hardlink guard test; the entire selected-RAG suite then passed 24 tests and the full rerun passed without changing that guard or test. The original failure is retained in the local receipt; its cause is not claimed resolved. |
| Bridge | 19 synthetic command/model-bridge tests passed. No real provider dispatch occurred. |
| Build/gates | TypeScript, standalone/Review builds, version, privacy, module boundaries, source-size and README diagram checks passed. |
| Browser / candidate Host | Installed Chrome headless against extracted candidate backend/assets and synthetic sources: real mouse selection for both evidence modes and result counts, the last entry of a scrolled 30-file list, keyboard/Escape, draft retention, revision-bound settings saves, successful exact Context preview, pending-task/real-Run display and consent clearing passed. No stage was approved or dispatched. |
| Layout | 570/760/799/800/960px-wide desktop panes at 900px height and 760×500: Memory hover/open retained 192px text navigation, visible entries/footer, no document or main horizontal overflow and no sidebar scrollbar. This does not claim mobile or full native VS Code acceptance. |
| Package | Matching versions, allowlisted contents, source/asset bytes, original distributed notices and privacy exclusions verified. Existing v1.10.3 packages retained. |

Candidate artifacts are in ignored `.tmp/packages/`: `frag-host-1.10.4.zip`, `frag-bridge-1.10.4.vsix` and `receipt-1.10.4.json` (write time, size and SHA-256). Build experiments and browser evidence use a timestamped `.tmp/runs/` directory; packaging explicitly used the fresh task-local Review build, not the older fixed build cache.

## Installation-documentation follow-up

Read-only inspection found a selected VSIX at 1.10.4, an explicit Host path still pointing to 1.10.3 and no installed 1.10.4 Host. The launcher requires matching versions; clearing Remote addresses cannot repair that mismatch. Installed settings, model contents, credentials and program directories were not changed.

- Setup now separates upgrade, first installation and daily start. Upgrade explicitly updates `frag.hostInstallation` after installing the Host; an already-matching VSIX need not be reinstalled.
- Current installation examples are version-checked. All 17 focused checks passed, including stale ZIP, VSIX and single/doubled-backslash Host paths in each guide; historical report labels remain permitted.
- The candidate packages were refreshed with the updated READMEs. The Host also ships `resources/install.md`. Archive comparison verified identical runtime, frontend asset and license bytes; only documentation changed. Existing historical packages were retained.
- Architecture/privacy/version/diagram gates and `git diff --check` passed again. This documentation-only follow-up did not repeat provider or desktop acceptance.

## Remaining manual acceptance

Use the [matching-component upgrade procedure](README.md#upgrade-to-v1104) to install the current Host into the dedicated instance and update its explicit path; install the VSIX only if it is not already 1.10.4. Preserve the old Host, existing project state, model configuration and credentials. The installed Host was not replaced during this task. Recheck native text-only Send and any implicit Context entries in that composer, installed mouse interactions and the desired even pane split. External authentication/billing, supplier HTTP behavior and human semantic acceptance remain separate. No commit, push, tag, publication, FC edit or phase advance was performed.

Proposed commit: `fix: repair Review interactions and stabilize navigation in v1.10.4`
