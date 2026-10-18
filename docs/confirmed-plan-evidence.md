# Complete confirmed-plan evidence

FRAG 1.13.3 retains a bounded whole-plan read to the existing Search → Read flow. It does not add a model loop, financial calculation or production recommendation carrier.

## Human selection and exact revisions

1. Authorize a local source and explicitly build its index in Settings.
2. Complete a native `frag_search` invocation. Review the **entire** intended Markdown/text file, not just the returned excerpt.
3. In Runs, select **Confirm entire document as a plan**. Management binds the selected document to its current SHA-256 and advances source authorization. Tools cannot confirm plans.
4. Run a fresh Search, then invoke `frag_read` with its returned IDs and `requireCompletePlan: true`.

Only UTF-8 `.md`/`.txt` documents are supported in this initial whole-plan path. Original headings, frontmatter, constraints and counterevidence are retained, subject to existing redaction. No source directory expansion, arbitrary file input, automatic indexing, confirmation inferred from metadata, or automatic plan rewriting occurs. Multiple hits from the same document produce one whole required document.

Whole-plan evidence carries server-generated `role: confirmed_plan`, `planRevision`, `windowed: false` and `requiredEvidenceIds`. Source bindings retain document identity, revision and parser version. Ordinary Read remains a bounded excerpt; an unwindowed section does not become a confirmed plan.

Changed files, scope/profile revisions or selected Memory revisions reject outstanding delivery. Refreshing an index never renews a stale plan confirmation. A human must review and reconfirm its changed revision. Settings can clear plan selections or disable a source; neither operation deletes source files or historical completed Runs.

Clearing and saving plan selections also restores the prior persisted source-configuration shape. A retained 1.13.0 core can read that disabled configuration and completed evidence history. This does not downgrade the FC service/reader or make new synthetic receipt rule versions readable by older code; see the [rollback limits](recommendation-safety.md#disabled-production-path-and-rollback).

## Capacity and economic prerequisites

The complete plan and exact selected Memory must fit the existing 16 KiB pack and any native token budget. Overflow is refusal, not an 8,000-character window, silent omission of Memory or removal of constraints. Whole monthly and economic reports retain required-evidence protection. Evidence completion rechecks these rules.

The opt-in **synthetic** complete-evidence policy requires a completed whole-plan Run bound to the selected revision and one whole official FC economic report in a completed evidence Run. Its coverage must establish recorded cash stocks, liability balances and dated obligations with no critical missing facts. The referenced FC revision, exact as-of/window and server-required IDs must match. Missing facts reject before checking/release even when a test context asserts completeness. Current safe receipts identify `recommendation-complete-evidence-v2`; older v1 receipts remain readable history, and the original Slice A policy/fixed cases remain separate and unchanged.

Official FC reader **1.9.0 / protocol 2**, API **3.9.0**, adds only explicitly whitelisted `economic-evidence:YYYY-MM-DD:YYYY-MM-DD` summaries. Gross balances, dated confirmed current-debt repayments, out-of-horizon debt and planned expenses remain distinct; personal availability, future charges and external completeness remain unknown. Other owner-session-only personal endpoints are not exposed. Three-month flows or a local virtual Markdown document cannot attest economic stocks/timing. FRAG neither opens FC SQLite nor supplies financial arithmetic. See the [exact reader contract](finance-core-plugin-handoff.md).

Question-mark icons replace instructional long text in management pages; mouse hover shows the full guidance, with basic focus/Escape support and no custom touch interaction. Errors, authorization disclosures, safety warnings and essential Run status remain visible.

The separate `month-to-date:YYYY-MM-DD` report is provisional posted Journal evidence for one exact cutoff. It remains whole required evidence, but does not become a completed three-month report, a balance sheet or a substitute for economic-stock/obligation coverage. Unrecorded days and real-world completeness stay unknown. No recommendation prerequisite or production gate is relaxed.

Slice B's model-free evidence path can be verified with virtual plans and a test sandbox through the released FC contract. That is not production recommendation completeness or human financial acceptance. A dedicated checked-only carrier, provider budget/privacy verification and subsequent native/human workflow acceptance remain prerequisites for Slice C. The real financial Run is a separate user-operated step.
