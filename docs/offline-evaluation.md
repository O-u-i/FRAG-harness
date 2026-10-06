# Offline evaluation

The unified runner reads one explicitly supplied, versioned synthetic Gold file and reports separately on retrieval, evidence assembly, scripted model artifacts, Research trajectories and deterministic host enforcement. It uses the production FTS5 index, hierarchical evidence assembly, fixed Context/Inference runner, durable Research runner, exact prepared requests, one-use approvals, output limits, citation membership and selected-source policy. It cannot select a network provider and does not load environment configuration or credentials.

From `backend`, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -m frag_api.evaluation --gold eval/synthetic-gold-v1.json
.\.venv\Scripts\python.exe -m frag_api.evaluation --gold eval/synthetic-gold-v1.json --format markdown
.\.venv\Scripts\python.exe -m frag_api.evaluation --gold eval/synthetic-research-gold-v1.json
```

`run_gold(path, work_dir=...)` returns the same typed `EvalReport` used by the CLI. The default output is stdout; the runner never writes a report automatically. Redirect only to an ignored local export when needed. Each invocation creates a fresh scratch directory below the repository's ignored `.tmp/offline-eval`; `--work-dir` overrides its parent. Scratch sources and SQLite indexes contain only the supplied synthetic fixture, are not product sessions or memory, and are never automatically deleted.

The maintained `backend/eval/synthetic-gold-v1.json` is schema version 1 and suite version 1.0.0. It embeds a synthetic Markdown source with an explicit revision and SHA-256. Cases specify a query, top-K, required retrieval `chunkId` values, required expanded `evidenceId` values, literal facts and forbidden phrases. Fact kinds distinguish negation, constraints, dates, units and other facts. All required Gold identifiers must be present; one relevant hit does not satisfy a case requiring two. The runner verifies that Gold identifiers exist in its bound source before executing cases. A changed fixture, scorer or chunk strategy requires a reviewed Gold update and version change.

`mode: "retrieval"` skips both model stages and reports them as `NOT_RUN`. Full cases run offline Fake outputs by default. Optional `sampleContext` and `sampleAnswer` are typed scripted outputs delivered through the actual fixed flow; they allow reproducible bad-artifact fixtures without network calls. Real model execution, provider sampling and LLM judges are outside this runner. Fixed cases retain a `NOT_RUN` Research trajectory; registering or testing tools does not count as a model/tool loop.

An explicit `evaluateTools: true` case also validates the production selected-source policy and exercises the registered `kb.read` CLI carrier and native `kb.search` binding on that case's synthetic candidate evidence. The read carrier starts its actual pinned child process; returned call IDs, selected rows and the native zero-hit missing-information result are checked. This offline fixture supplies trusted host-owned synthetic evidence and never opens real evidence files or product sessions. It complements the product HTTP/journal tool tests and is not a Research loop. Carrier failures produce a tool `ERROR` rather than a model-quality failure.

Schema version 1 also accepts optional `researchCases`; at least one fixed or Research case is required and IDs are unique across both groups. The separate maintained `synthetic-research-gold-v1.json` declares five trajectories: actual CLI read followed by finish, native search then CLI read, a zero-hit observation followed by recovery, application-lifecycle restart with retained history, and a sanitized tool timeout followed by a successful read. The runner version is 1.1.0. Each trajectory selects the embedded synthetic Markdown's locators explicitly, creates its own ignored SQLite Run journal and injects a bounded Fake provider into the production Research flow. It does not bypass policy or execute tool bindings directly.

Research steps declare `read`, `search` or `finish` fixture decisions and expected termination, tool sequence and outcomes. Optional malformed, unknown-tool, scope-escape and duplicate-call scripts support negative fixtures. A script cannot name executable paths, choose a provider or grant source access. Every model turn is prepared, rejected once without approval, explicitly approved for the synthetic fixture and checked against replay; the next turn includes actual durable tool results or sanitized errors. Scorers compare captured exact requests, callId pairs, selected scope, the three-turn/six-tool limits, termination and requested checkpoint recovery. A deliberately invalid model proposal may receive model-artifact `FAIL` while its correct host rejection receives `PASS`. Handled tool errors with declared recovery are observations, not automatic evaluation-runner failures.

The restart fixture closes and recreates the application Runtime/Research objects over the same SQLite file; it verifies a persisted reliable checkpoint and fresh approval without another dispatch. It is an application-lifecycle recovery test, not an operating-system crash test. Research fixtures stop at evidence collection and the Context approval boundary; the separate fixed suite and stage tests cover Context/Inference. The report's `trajectoryStatus` aggregates executed trajectory checks, while each skipped fixed-case trajectory remains explicit. Correct path membership, literal matches and hash consistency do not establish semantic support or a unique cause.

The report preserves Search IDs, rankings and scores, candidate evidence, executed PreparedCalls and returned Context/Inference artifacts. Approval tokens and credentials are excluded. It reports all checks and the earliest observed failed stage, which identifies a deviation without claiming a unique cause. Invalid source hashes, unsupported schema versions, unknown Gold IDs, duplicate keys and execution/scorer exceptions produce `ERROR`, never an inferred pass. A bad citation can produce model-artifact `FAIL` and host-enforcement `PASS` in the same case because the host correctly rejected it.

Statuses are `PASS`, `FAIL`, `ERROR`, `NOT_RUN` and `UNDETERMINED`. Overall status prioritizes `ERROR`, then `FAIL`, then the result of executed deterministic checks. A deterministic `PASS` can coexist with `NOT_RUN` stages and `UNDETERMINED` semantic review; both remain visible in counts and dedicated fields. Exit codes are 0 for deterministic `PASS`, 2 for `FAIL` and 1 for `ERROR`. JSON and Markdown contain the same canonical structured report.

Fact checks normalize case, Unicode compatibility characters and whitespace, then match bounded literal alternatives and forbidden phrases. They detect declared fixture regressions such as dropped negations, reversed constraints, wrong dates and units. They do not recognize arbitrary paraphrases, determine truth, resolve contradictions generally or establish whether a legal citation supports a claim. Human semantic review is always `UNDETERMINED` here. Synthetic approval and review fixtures do not count as real GPT or selected-KB acceptance.

The existing RAG Lab evaluation endpoint remains compatible and retains its three-case demo metrics. The unified offline runner removes that fixed case-count assumption and adds stage observations and explicit limits. It complements production stage and carrier tests; it does not replace them or qualify a model for production.

## Explicit captured Run evaluation

For a saved Run, export its JSON report from Runs and author a separate captured Gold file from reviewed source evidence. This mode scores the original saved Context and model answer, retaining human revisions separately. It never regenerates a Fake answer, invokes a provider, restores a Run, executes tools or rereads the source. Supply both files explicitly; `--work-dir` is unavailable in capture mode.

```powershell
# From backend; both inputs are private, Git-ignored acceptance artifacts.
.\.venv\Scripts\python.exe -m frag_api.evaluation --gold ../.local-plan-b/phase-8/manual/captured-gold.json --capture ../.local-plan-b/phase-8/manual/run-report.json
.\.venv\Scripts\python.exe -m frag_api.evaluation --gold ../.local-plan-b/phase-8/manual/captured-gold.json --capture ../.local-plan-b/phase-8/manual/run-report.json --format markdown
```

Captured Gold has `schemaVersion: 1`, `suiteId`, a semantic `suiteVersion`, optional `runId`, the exact `goal`, complete `sourceBindings`, distinct `expectedEvidenceIds`, `facts` and optional `requiredMissingInformation`. Copy each complete source binding from the report's selection, including identity, revision, parser version, locators, evidence IDs and assessment. Write the expected facts from the source independently of the answer. The goal and source bindings must match the supplied report exactly; a mismatch blocks model scoring and records a failure.

For example, a reviewed synthetic condition could produce the following `facts` value:

```json
[
  {"id":"no-write","kind":"negation","alternatives":["Writes are not allowed"],"forbidden":["Writes are allowed"]},
  {"id":"review-date","kind":"date","alternatives":["2026-10-05"],"forbidden":["2026-10-06"]},
  {"id":"capacity","kind":"unit","alternatives":["10 MiB"],"forbidden":["10 GiB"]}
]
```

The captured runner reports `runnerVersion: "1.2.0"` and `provider: "captured-artifacts"`. It checks internally consistent snapshot/request/output hashes, recorded stage links, original evidence and citation membership, bounded Context/Inference artifacts, declared literal facts and missing information. A recorded Research trajectory is validated against its saved tool definitions, selected observations and call IDs. Hash consistency does not authenticate a supplied report or establish that a human granted approval.

Current-source revalidation, legitimate approval and the original complete retrieval ranking remain `NOT_RUN`; this evaluator has neither live source access nor approval tokens. Human semantic review remains `UNDETERMINED`, including when a capture contains an accepted review record. An incomplete Run produces `NOT_RUN` model quality; an unknown external outcome remains `UNDETERMINED` and is never resent. Malformed inputs or inconsistent captured links produce `ERROR`. Exit code 3 identifies `NOT_RUN` or `UNDETERMINED`; codes 0, 2 and 1 retain their existing meanings.

JSON and Markdown preserve the same canonical report, including private captured evidence. Save outputs only to ignored local storage. This mode provides deterministic observations for the [manual acceptance workflow](manual-acceptance.md); real GPT, KB support, live FC and human semantic acceptance still require their own evidence.
