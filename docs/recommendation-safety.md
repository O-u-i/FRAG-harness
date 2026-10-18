# Model-free recommendation safety foundation

Version 1.13.0 introduced the synthetic safety foundation. Version 1.13.2 combines whole confirmed-plan and FC economic evidence with an opt-in complete-evidence synthetic policy, not a production financial/life recommendation workflow. The native Local Agent still owns general chat, models, research and final inference. Existing evidence tools and pure factual review remain available. There is no second chat, model client, Send interception, scheduler or financial calculation in FRAG.

## What exists

- `SyntheticRecommendationWorkflow` is an explicitly enabled, internal synthetic test controller. The application never constructs it; no tool or management endpoint accepts a candidate, triggers checking or releases advice.
- `PrivateCandidate` holds bounded, volatile internal bytes, excluded from representations and every persisted schema. A synthetic checker sees those bytes privately; only the exact checked bytes may return to the internal test caller, after safe diagnostic persistence and final revalidation. No model polishing or automatic resend follows checking.
- The gate refuses missing evidence/plans/constraints/financial foundations, incomplete required evidence, unknown/failed checks, changed artifacts/revisions, cancellation, interruption, deadlines and persistence failure. Cancellation can win while a private checker is running. Unknown crash causes remain unknown.
- Final context/source reads remain inside the deadline; candidate integrity and budget are checked again after those reads. The pinned FC reader guarantees whole monthly/economic reports, not whole journal/draft records. Its bounded record summaries cannot satisfy required recommendation evidence; existing factual tools are unchanged.
- `recommendation_receipts` shares the existing database owner, not the `tool_runs` table or evidence-completion lifecycle. Fields are allowlisted identifiers, times, stages/statuses, stable reason codes, rule/revision/evidence references and numerical synthetic budget diagnostics. No draft, summary, free-text exception, transcript or human adoption is stored.
- Runs displays these receipts separately, with no recommendation body/raw draft export. A workflow ID cannot be used as evidence provenance for Memory. Completed evidence and legacy rows are preserved.

The original Slice A context's plan revision and financial-foundation assertion remain **test inputs**, not proof of a complete confirmed plan, assets, liabilities or future obligations. An unwindowed paragraph is not a whole plan. Objective and semantic checker outcomes are simulated; check-passed is not truth, optimality, suitability, user adoption or execution.

## Slice B complete-evidence policy

[Whole-plan delivery](confirmed-plan-evidence.md) reuses human source authorization and completed Search results. Human confirmation pins an entire UTF-8 Markdown/text document revision; `frag_read` with `requireCompletePlan: true` returns it as server-required evidence or refuses. Index refresh is not reconfirmation. Whole plans, monthly/economic reports and selected Memory cannot be trimmed to fit.

Synthetic controllers may opt into `require_complete_evidence=True`, identified by `recommendation-complete-evidence-v2` receipts. A plan digest or Search excerpt alone fails. Missing cash stocks, liability balances or dated obligations fails. A monthly flow report or local virtual text cannot act as economic-stock/timing evidence. The gate requires one completed whole official economic report, matching its window/revision/required IDs and checking FC coverage directly; test assertions cannot erase FC gaps. Recorded-scope coverage is not personal disposable availability or future-charge/external completeness. Earlier `recommendation-complete-evidence-v1` receipts remain readable historical synthetic records, not proof of the stronger official-FC policy. Existing Slice A tests are retained unchanged; neither policy is instantiated as a production controller.

## Shared synthetic budget

Create the workflow before evidence work. Its initial baseline is 600 seconds, cumulative 100,000 input/50,000 counted output tokens, a 1 CNY liability target and at most two remediation rounds. All drafting/checking/specialist/retry reservations share one ledger. Reserve complete transmitted input and maximum counted output atomically before any request; required evidence and selected Memory must not be truncated to fit.

Integer micro-CNY arithmetic supports a synthetic tariff and per-request fees. Known usage reconciles conservatively; unknown/over-cap usage retains maximum reserved liability and prevents retries/release. Remediation requires new information and cannot reset quotas, enlarge scope or weaken checks. Late accounting does not authorize late delivery, and cancellation does not prove billing stopped.

These tests do **not** establish actual token counting, hidden-reasoning/output caps, pricing, fees, provider retry behavior or a hard monetary guarantee. No provider request is implemented or authorized by this component.

## Disabled production path and rollback

Management reports `available: false` / `CARRIER_UNAVAILABLE`. There is no setting that enables production recommendations. The synthetic controller defaults to disabled and does not create receipts in that state. General native chat is not intercepted or filtered; tool-only output is not a universal pre-display gate.

A future dedicated carrier requires separately named authorization and verified private buffering, request/cancellation/usage control, complete revision-bound plan/economic evidence and exact checked-only delivery. A three-month report is not a complete affordability model. FC remains the owner of new financial facts and deterministic calculations. This line exact-pins official reader 1.8.0 / API 3.8.0 for explicitly approved monthly/economic windows, without owner access or financial writes.

To disable the new plan path, clear confirmed plans in Settings and save the authorization; ordinary Search/Read remain available. Before a reviewed downgrade, clear these selections while the current backend still owns the state, then stop it and use a retained matching Host/VSIX. A retained 1.13.0 core is checked against that disabled source configuration and completed Run history, with no database deletion or provenance rebinding. Its older FC pin does not support API 3.8.0; keep that optional reader disabled rather than bypassing version checks. State containing `recommendation-complete-evidence-v1` or `recommendation-complete-evidence-v2` synthetic receipts is not in-place downgrade compatible with the older receipt schema; leave that development state intact and use current-version feature disable or a separately reviewed migration. Never rewrite receipts, reset Memory or replay interrupted work to force a downgrade.

## Verification

Development cases and the unchanged Slice A fixed acceptance set are separate. Synthetic tests cover sentinel isolation across private checking, failed/cancelled/interrupted/unknown states, all exposed management/tool/Memory routes, exact artifact release, changed sources/constraints, races, failed/slow commits, recovery, shared reservations and unknown liability. Slice B cases additionally verify whole-document delivery, explicit confirmation, stale confirmation, required plan/Memory overflow and missing economic facts. Required-report byte/token overflow protections remain authoritative.

Offline tests, built packages, actual native loading/invocation/continuation, provider behavior and human reasoning/fit acceptance are different receipts. Current scoped command results and unmet prerequisites are retained privately, never substituted with historical native/provider checks.
