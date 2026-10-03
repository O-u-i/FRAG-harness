# Offline synthetic evaluation

The unified runner reads one explicitly supplied, versioned synthetic Gold file and reports separately on retrieval, evidence assembly, scripted model artifacts and deterministic host enforcement. It uses the production FTS5 index, hierarchical evidence assembly, fixed Context/Inference runner, exact prepared requests, one-use approvals, output limits, citation membership and selected-source policy. It cannot select a network provider and does not load environment configuration or credentials.

From `backend`, using the existing environment:

```powershell
.\.venv\Scripts\python.exe -m frag_api.evaluation --gold eval/synthetic-gold-v1.json
.\.venv\Scripts\python.exe -m frag_api.evaluation --gold eval/synthetic-gold-v1.json --format markdown
```

`run_gold(path, work_dir=...)` returns the same typed `EvalReport` used by the CLI. The default output is stdout; the runner never writes a report automatically. Redirect only to an ignored local export when needed. Each invocation creates a fresh scratch directory below the repository's ignored `.tmp/offline-eval`; `--work-dir` overrides its parent. Scratch sources and SQLite indexes contain only the supplied synthetic fixture, are not product sessions or memory, and are never automatically deleted.

The maintained `backend/eval/synthetic-gold-v1.json` is schema version 1 and suite version 1.0.0. It embeds a synthetic Markdown source with an explicit revision and SHA-256. Cases specify a query, top-K, required retrieval `chunkId` values, required expanded `evidenceId` values, literal facts and forbidden phrases. Fact kinds distinguish negation, constraints, dates, units and other facts. All required Gold identifiers must be present; one relevant hit does not satisfy a case requiring two. The runner verifies that Gold identifiers exist in its bound source before executing cases. A changed fixture, scorer or chunk strategy requires a reviewed Gold update and version change.

`mode: "retrieval"` skips both model stages and reports them as `NOT_RUN`. Full cases run offline Fake outputs by default. Optional `sampleContext` and `sampleAnswer` are typed scripted outputs delivered through the actual fixed flow; they allow reproducible bad-artifact fixtures without network calls. Real model execution, provider sampling and LLM judges are outside this runner. Research trajectory remains `NOT_RUN` until Phase 4.

An explicit `evaluateTools: true` case also validates the production selected-source policy and exercises the registered `kb.read` CLI carrier and native `kb.search` binding on that case's synthetic candidate evidence. The read carrier starts its actual pinned child process; returned call IDs, selected rows and the native zero-hit missing-information result are checked. This offline fixture supplies trusted host-owned synthetic evidence and never opens real evidence files or product sessions. It complements the product HTTP/journal tool tests and is not a Research loop. Carrier failures produce a tool `ERROR` rather than a model-quality failure.

The report preserves Search IDs, rankings and scores, candidate evidence, executed PreparedCalls and returned Context/Inference artifacts. Approval tokens and credentials are excluded. It reports all checks and the earliest observed failed stage, which identifies a deviation without claiming a unique cause. Invalid source hashes, unsupported schema versions, unknown Gold IDs, duplicate keys and execution/scorer exceptions produce `ERROR`, never an inferred pass. A bad citation can produce model-artifact `FAIL` and host-enforcement `PASS` in the same case because the host correctly rejected it.

Statuses are `PASS`, `FAIL`, `ERROR`, `NOT_RUN` and `UNDETERMINED`. Overall status prioritizes `ERROR`, then `FAIL`, then the result of executed deterministic checks. A deterministic `PASS` can coexist with `NOT_RUN` stages and `UNDETERMINED` semantic review; both remain visible in counts and dedicated fields. Exit codes are 0 for deterministic `PASS`, 2 for `FAIL` and 1 for `ERROR`. JSON and Markdown contain the same canonical structured report.

Fact checks normalize case, Unicode compatibility characters and whitespace, then match bounded literal alternatives and forbidden phrases. They detect declared fixture regressions such as dropped negations, reversed constraints, wrong dates and units. They do not recognize arbitrary paraphrases, determine truth, resolve contradictions generally or establish whether a legal citation supports a claim. Human semantic review is always `UNDETERMINED` here. Synthetic approval and review fixtures do not count as real GPT or selected-KB acceptance.

The existing RAG Lab evaluation endpoint remains compatible and retains its three-case demo metrics. The unified offline runner removes that fixed case-count assumption and adds stage observations and explicit limits. It complements production stage and carrier tests; it does not replace them or qualify a model for production.
