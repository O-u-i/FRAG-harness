# Governed runtime contracts

`GET /api/harness/capabilities` lists executable registrations separately from planned capabilities. The current runtime registers the fixed Context → Inference runner. `CLIRegistry` and `ToolRegistry` are implemented registration interfaces; the product does not yet install a CLI carrier or expose model tools. Research is planned and cannot be selected as an active runner.

## Prepared requests and approval

Preview constructs a frozen `PreparedCall` with canonical JSON strings for `body` and `binding`. JSON objects returned by its accessors are copies. The binding includes selected source identities, revisions and locators, the user task and checklist, the fixed loop definition, host/policy/redaction/prompt/output-contract versions and the second stage's provider route. Selected memory and tool versions are empty in the fixed workflow.

The body contains the final model, instructions, input, output limit, disabled provider storage and tool definitions. OpenAI also receives the exact strict JSON schema displayed in the body. Ollama receives its output schema in the displayed input, as before. The destination and transport are explicit. Credentials are resolved by the backend at dispatch and never appear in the prepared spec. SDK environment routing and HTTP redirects cannot replace the approved destination; automatic retries are disabled.

The host stores its own prepared snapshot with a short-lived, one-use token. Run accepts source selection plus fingerprints and approval; it rejects caller-supplied request bodies or prepared specs. It revalidates current source and configuration bindings, consumes the token and dispatches the stored call. Context returns a separately prepared Inference call. That call requires a new approval and is revalidated again. The registries remain in memory: restarting invalidates all tokens and does not resume calls.

SDK transport tests compare the actual JSON body and destination to the preview for both stages. This proves structural request equality, not identical SDK whitespace or headers, real-provider availability, output faithfulness or human semantic approval.

## Source scope and task checks

`SourceIdentity` separates local file, bundled synthetic and FC record identities. A source binding includes namespace, resource ID, optional FC Workspace, revision, parser version, selected locator IDs and allowed Context evidence IDs. Local root namespaces are opaque hashes; hashing and extraction use the same captured bytes. Markdown locators preserve preamble and fenced examples. SQLite retrieval reads the index revision, matching chunks and parent contents in one read transaction.

`HostPolicy` checks registered tools against a separate allowed-tool set and selected source bindings. Registration never expands permission. A valid tool schema cannot grant another file, locator, root, revision or Workspace. This release exposes no FC model tool; FC remains bounded released HTTP evidence reading.

`TaskContract` supports only the versioned `evidence-review-v1` template, with up to 20 uniquely identified checklist items. A blocking item permits approval only when `status` is `met` and `reviewed` is true. Nonblocking pending/missing/unknown items remain in task metadata. Checklist review currently enters through the API; editing, review history and report controls are pending session work. No model response can change this host-owned checklist.

Authority, freshness, relevance and provenance use known/unknown metadata. A user's selection reason is identified as such. A parser hash or valid citation ID does not demonstrate factual truth, completeness or support. Output validation rejects missing, foreign or duplicate Context IDs, invalid output structure and references outside the compressed evidence. Semantic review remains required.

## Limits and failures

Input estimation covers the complete request JSON, including instructions, schema and tools. The existing 6,000-token budget reserves 25%, allowing an estimated 4,500 input tokens per stage. Context and Inference output limits remain 1,500 and 2,000. These input estimates use UTF-8 byte length, not a model-specific tokenizer.

The default cumulative run limit is 30,000 input-plus-output tokens. Each call reserves estimated input plus its output ceiling before dispatch; completed calls charge reported usage, falling back to the reservation for unknown components. The budget carries across both stages. The future Research contract retains three model turns, six serial tools, ten seconds per tool, 16 KiB results and an 800-token loop output cap. A declared future limit is not proof that a Research runner exists.

Refusal, incomplete output and unknown transport outcomes have separate sanitized API errors. Invalid output remains `INVALID_LLM_OUTPUT`. A timeout or connection failure is `LLM_OUTCOME_UNKNOWN`; neither the host nor provider automatically resends it. Redaction covers goal/query, selected evidence, checklist payloads and subsequent model inputs, including known configured model keys and common secret/email patterns. It cannot identify every private value. Persisted outcomes, safe checkpoints and reports are pending session implementation.
