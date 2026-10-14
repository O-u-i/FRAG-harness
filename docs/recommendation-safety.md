# Model-free recommendation safety foundation

Version 1.13.0 implements a synthetic safety foundation, not a production financial/life recommendation workflow. The native Local Agent still owns general chat, models, research and final inference. Existing evidence tools and pure factual review remain available. There is no second chat, model client, Send interception, scheduler or financial calculation in FRAG.

## What exists

- `SyntheticRecommendationWorkflow` is an explicitly enabled, internal synthetic test controller. The application never constructs it; no tool or management endpoint accepts a candidate, triggers checking or releases advice.
- `PrivateCandidate` holds bounded, volatile internal bytes, excluded from representations and every persisted schema. A synthetic checker sees those bytes privately; only the exact checked bytes may return to the internal test caller, after safe diagnostic persistence and final revalidation. No model polishing or automatic resend follows checking.
- The gate refuses missing evidence/plans/constraints/financial foundations, incomplete required evidence, unknown/failed checks, changed artifacts/revisions, cancellation, interruption, deadlines and persistence failure. Cancellation can win while a private checker is running. Unknown crash causes remain unknown.
- Final context/source reads remain inside the deadline; candidate integrity and budget are checked again after those reads. The pinned FC reader guarantees whole monthly reports, not whole journal/draft records. Its bounded record summaries cannot satisfy required recommendation evidence; existing factual tools are unchanged.
- `recommendation_receipts` shares the existing database owner, not the `tool_runs` table or evidence-completion lifecycle. Fields are allowlisted identifiers, times, stages/statuses, stable reason codes, rule/revision/evidence references and numerical synthetic budget diagnostics. No draft, summary, free-text exception, transcript or human adoption is stored.
- Runs displays these receipts separately, with no recommendation body/raw draft export. A workflow ID cannot be used as evidence provenance for Memory. Completed evidence and legacy rows are preserved.

The synthetic context's plan revision and financial-foundation assertion are **test inputs**, not proof of a complete confirmed plan, assets, liabilities or future obligations. An unwindowed paragraph is not a whole plan. Objective and semantic checker outcomes are simulated; check-passed is not truth, optimality, suitability, user adoption or execution.

## Shared synthetic budget

Create the workflow before evidence work. Its initial baseline is 600 seconds, cumulative 100,000 input/50,000 counted output tokens, a 1 CNY liability target and at most two remediation rounds. All drafting/checking/specialist/retry reservations share one ledger. Reserve complete transmitted input and maximum counted output atomically before any request; required evidence and selected Memory must not be truncated to fit.

Integer micro-CNY arithmetic supports a synthetic tariff and per-request fees. Known usage reconciles conservatively; unknown/over-cap usage retains maximum reserved liability and prevents retries/release. Remediation requires new information and cannot reset quotas, enlarge scope or weaken checks. Late accounting does not authorize late delivery, and cancellation does not prove billing stopped.

These tests do **not** establish actual token counting, hidden-reasoning/output caps, pricing, fees, provider retry behavior or a hard monetary guarantee. No provider request is implemented or authorized by this component.

## Disabled production path and rollback

Management reports `available: false` / `CARRIER_UNAVAILABLE`. There is no setting that enables production recommendations. The synthetic controller defaults to disabled and does not create receipts in that state. General native chat is not intercepted or filtered; tool-only output is not a universal pre-display gate.

A future dedicated carrier requires separately named authorization and verified private buffering, request/cancellation/usage control, complete revision-bound plan/economic evidence and exact checked-only delivery. A three-month report is not a complete affordability model. FC remains the owner of new financial facts and deterministic calculations; its official reader/API pins are unchanged.

To roll back, stop the owning backend and reinstall the previously retained matching Host/VSIX. Keep private state: the new receipt table is additive, contains no drafts, and the earlier evidence backend ignores it. Do not delete databases, rebind provenance, reset Memory or replay interrupted work.

## Verification

Development cases and the fixed acceptance set are separate. Synthetic tests cover sentinel isolation across private checking, failed/cancelled/interrupted/unknown states, all exposed management/tool/Memory routes, exact artifact release, changed sources/constraints, races, failed/slow commits, recovery, shared reservations and unknown liability. Existing required-report byte/token overflow tests remain authoritative; they do not establish complete plan delivery.

Offline tests, built packages, actual native loading/invocation/continuation, provider behavior and human reasoning/fit acceptance are different receipts. Current scoped command results and unmet prerequisites are retained privately, never substituted with historical native/provider checks.
