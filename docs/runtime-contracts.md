# Governed runtime contracts

`GET /api/harness/capabilities` lists executable registrations separately from planned capabilities. The runtime registers the fixed Context → Inference runner, optional Research → Context → Inference runner, `frag.host` HTTP CLI, `kb.read.cli` carrier, native `kb.search` and CLI-backed `kb.read`. Tool arguments and private carrier input schemas are separately declared; the carrier receives only trusted selected snapshots after host authorization. Fixed model requests contain no model tools. Research accepts complete typed model proposals, validates them and feeds actual observations into the next separately approved turn. The VS Code route uses this same structured contract without importing native coding tools.

## Prepared requests and approval

Preview constructs a frozen `PreparedCall` with canonical JSON strings for `body` and `binding`. JSON objects returned by its accessors are copies. The binding includes selected source identities, revisions and locators, the user task and checklist, the fixed loop definition, host/policy/redaction/prompt/output-contract versions and the second stage's provider route. Selected memory and tool versions are empty in the fixed workflow.

The body contains the final model, instructions, input, output limit, disabled provider storage and tool definitions. OpenAI also receives the exact strict JSON schema displayed in the body. Ollama receives its output schema in the displayed input, as before. The destination and transport are explicit. Credentials are resolved by the backend at dispatch and never appear in the prepared spec. SDK environment routing and HTTP redirects cannot replace the approved destination; automatic retries are disabled.

The host stores its own prepared snapshot with a short-lived, one-use token. Run accepts source selection plus fingerprints and approval; it rejects caller-supplied request bodies or prepared specs. It revalidates current source and configuration bindings, consumes the token and dispatches the stored call. Context returns a separately prepared Inference call. That call requires a new approval and is revalidated again. The registries remain in memory: restarting invalidates all tokens and does not automatically resume calls. The separate runtime store saves redacted selected snapshots, request specifications, outputs and review records. Explicit recovery creates a new preview and token after source/configuration revalidation.

SDK transport tests compare the actual JSON body and destination to the preview for both stages. This proves structural request equality, not identical SDK whitespace or headers, real-provider availability, output faithfulness or human semantic approval.

## Source scope and task checks

`SourceIdentity` separates local file, bundled synthetic and FC record identities. A source binding includes namespace, resource ID, optional FC Workspace, revision, parser version, selected locator IDs and allowed Context evidence IDs. Local root namespaces are opaque hashes; hashing and extraction use the same captured bytes. Markdown locators preserve preamble and fenced examples. SQLite retrieval reads the index revision, matching chunks and parent contents in one read transaction.

`HostPolicy` checks registered tools against a separate allowed-tool set and selected source bindings. Registration never expands permission. A valid tool schema cannot grant another file, locator, root, revision or Workspace. This release exposes no FC model tool; FC remains bounded released HTTP evidence reading.

`TaskContract` supports only the versioned `evidence-review-v1` template, with up to 20 uniquely identified checklist items. A blocking item permits approval only when `status` is `met` and `reviewed` is true. Nonblocking pending/missing/unknown items remain in task metadata. Harness and RAG Lab expose checklist editing; Runs preserves checklist shape while recording reviewed statuses and decisions. Input changes create linked runs. Blocking review gaps pause acceptance and continuation. Reviews and human revisions preserve the original request and model output. No model response can change this host-owned checklist.

Authority, freshness, relevance and provenance use known/unknown metadata. A user's selection reason is identified as such. A parser hash or valid citation ID does not demonstrate factual truth, completeness or support. Output validation rejects missing, foreign or duplicate Context IDs, invalid output structure and references outside the compressed evidence. Semantic review remains required.

## Limits and failures

Input estimation covers the complete request JSON, including instructions, schema and tools. The existing 6,000-token budget reserves 25%, allowing an estimated 4,500 input tokens per stage. Context and Inference output limits remain 1,500 and 2,000. These input estimates use UTF-8 byte length, not a model-specific tokenizer.

The default cumulative run limit is 30,000 input-plus-output tokens. Each call reserves estimated input plus its output ceiling before dispatch; completed calls charge reported usage, falling back to the reservation for unknown components. The budget carries across Research, Context and Inference. Research allows three model turns, six serial tools, ten seconds per tool, 16 KiB results and an 800-token output cap per loop model request. Exhaustion stops the loop visibly; no extra model call is sent to manufacture a finish.

Research freezes its registered tool schemas/versions, selected source manifest and
durable trajectory into the prepared request. The initial request contains source
metadata and allowed IDs without the selected evidence bodies. Later turns include
actual call-bound observations. A finish decision selects only observed allowed
evidence; the resulting Context preview contains that subset and recorded missing
information. Each checkpoint requires a new preview and single-use approval. See
[Research loop](research-loop.md) for the typed proposals, source revalidation,
pause/recovery and exact HTTP contracts.

Refusal, incomplete output and unknown transport outcomes have separate sanitized API errors. Invalid output remains `INVALID_LLM_OUTPUT`. A timeout or connection failure is `LLM_OUTCOME_UNKNOWN`; neither the host nor provider automatically resends it. Redaction covers goal/query, selected evidence, checklist payloads, model responses and subsequent model inputs, including known configured model keys and common secret/email patterns. It cannot identify every private value. The application lifecycle owner persists outcomes and checkpoints in a separate SQLite runtime database. Known responses complete deterministic validation after restart; unknown dispatch outcomes do not resume. Runs, JSON and Markdown use the same structured report. See [sessions and recovery](runtime-sessions.md).
