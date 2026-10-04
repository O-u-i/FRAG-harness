# Optional Pi Responses adapter

FRAG's Python host owns approval, evidence selection, tool policy, budgets and durable history. The optional backend Node worker adapts **one** frozen model request using Pi. It cannot execute tools, select new sources, approve another request or promote memory. Fake and native providers remain available without this worker installed.

## Reviewed package

This is a selection of 29 unchanged published JavaScript modules from `@earendil-works/pi-ai@1.0.0`, pinned to commit `a13d35a742c6ef8462812a28fbe1d8c8b7431c32`. It uses exactly `openai@7.19.0` and `partial-json@0.1.7`; the full Pi package, optional peers and other provider SDKs are excluded. The selection manifest records original byte hashes, package archive integrities, source provenance and omissions.

The original Pi MIT, OpenAI Apache-2.0, embedded MIT/ISC/BSD and partial-json MIT documents are preserved under `backend/pi-worker/vendor/pi-ai/LICENSE` and `backend/pi-worker/licenses`. Preserve these original documents and `THIRD_PARTY_NOTICES.md` with any distribution containing the adapter. No vendored implementation is modified. This approval does not cover newly introduced packages or versions.

From a fresh checkout, install only the reviewed worker dependencies:

```powershell
npm.cmd ci --prefix backend/pi-worker --ignore-scripts --omit=optional --omit=peer --no-audit --no-fund
npm.cmd run check:pi
npm.cmd run test:pi
```

Use Node 22.19.0 or later. The integrity gate checks all selected modules, original notices, exact dependency identities and installed SDK byte trees. New dependency entries, changed bytes or missing notices fail the gate. Installing the worker does not send a model request. Root frontend dependencies are independent.

## Request and response contract

Each `pi-responses-v1` PreparedCall binds the endpoint, frozen canonical request body, adapter/commit/protocol version, strict output schema, tool definitions, selected revisions, budget and timeout. Pi's payload hook receives that body; a final SDK fetch guard validates method, URL and serialized request and forwards the frozen body bytes. Requests use `store:false`, streaming, zero retries and redirects disabled. The default endpoint is `https://api.openai.com/v1/responses`; each backend stage may explicitly configure a canonical HTTPS `/v1/` base. Authentication in URLs, query routing, fragments, explicit ports and URL normalization are rejected. Configuration changes invalidate the previous preview. A configurable route does not establish a relay's model or protocol compatibility.

Credentials travel from the backend to a fixed Node process through bounded stdin, separately from PreparedCall. The child receives an environment allowlist without proxy, provider, OAuth, credential-discovery or Node injection variables. Standard output contains bounded dispatch/result protocol records; errors contain safe codes. No reusable approval token or authentication header belongs in history.

Streaming deltas never execute tools. Only a completed response with matching completed output items can yield calls. The worker returns original argument strings; Python rejects incomplete JSON, duplicate properties, nonfinite values, undeclared fields and scope violations before execution. Refusal, truncation and unknown outcomes are distinct failure paths. Unknown external outcomes stop the Run and never resend automatically.

Research exposes `kb_read` and `kb_search` with closed, required-field wire schemas. Host registration remains `kb.read` and `kb.search`. Raw upstream IDs map to deterministic host IDs. Output and typed native replay metadata are saved atomically with digests. A later approved turn preserves the prior ordered output items and then pairs actual results with their upstream `call_id`; restore validates this correspondence before preparing a request. The model finishes by selecting observed evidence IDs and missing information, then separately approved Context and Inference produce the answer.

The adapter supports `gpt-4.1`, `gpt-4.1-mini`, `gpt-4.1-nano`, their `2025-04-14` snapshots and the exact `gpt-6.1-sol` ID. Sol freezes `reasoning.effort:"low"` and `include:["reasoning.encrypted_content"]`. Research replay version 2 preserves completed raw reasoning, assistant phase and function-call items in their original order, including optional-field absence and encrypted content. Version 1 remains available for existing GPT-4.1 history. Commentary is preserved for continuation and excluded from final structured JSON. Unknown output types, incomplete items and changed terminal metadata fail validation; only missing encrypted content may be filled from the completed terminal response. Continuation requires encrypted reasoning content. The formal stages start separately approved requests from selected evidence rather than using reasoning as evidence.

Sol supports `low` reasoning and Responses tool calling; `none` and `minimal` are unsupported. Reasoning tokens consume the existing output cap and are charged once in the reported output-token usage. The Research/Context/Inference caps remain 800/1500/2000, with a 120-second timeout and zero retries; an incomplete response stops the Run. [Sol model documentation](https://developers.openai.com/api/docs/models/gpt-6.1-sol), [reasoning documentation](https://developers.openai.com/api/docs/guides/reasoning) and [function calling documentation](https://developers.openai.com/api/docs/guides/function-calling) define the model and replay requirements. These official capabilities do not verify a relay's implementation or prices.

## Backend configuration and acceptance

Configure only the ignored `backend/.env`; never put a key in request JSON, frontend configuration or a command argument. Start with this template and replace the key locally:

```dotenv
FRAG_CONTEXT_LLM_PROVIDER=openai
FRAG_CONTEXT_LLM_MODEL=gpt-4.1-mini
FRAG_CONTEXT_LLM_ADAPTER=pi
FRAG_INFERENCE_LLM_PROVIDER=openai
FRAG_INFERENCE_LLM_MODEL=gpt-4.1-mini
FRAG_INFERENCE_LLM_ADAPTER=pi
FRAG_RESEARCH_LLM_PROVIDER=openai
FRAG_RESEARCH_LLM_MODEL=gpt-4.1-mini
FRAG_RESEARCH_LLM_ADAPTER=pi
FRAG_LLM_TIMEOUT_SECONDS=120
OPENAI_API_KEY=<configure-locally>
```

Restart the backend after changing configuration. Readiness checks report only booleans and safe codes. Previewing a source does not send a request. Use the existing Harness fixed or Research flow, or the host CLI's `execute-context` / `execute-research` commands. Each CLI execution needs `--approve`, an interactive terminal and the exact displayed request fingerprint. Each Research invocation executes just the currently approved stage; the following turn requires new approval.

For Sol, replace all three configured model values with `gpt-6.1-sol`. For a relay, set `FRAG_CONTEXT_LLM_BASE_URL`, `FRAG_INFERENCE_LLM_BASE_URL` and `FRAG_RESEARCH_LLM_BASE_URL` to its documented HTTPS `/v1/` base. Before live acceptance, verify that the selected relay model supports Responses streaming, strict schemas, native calls and encrypted reasoning replay. Verify the key's billing group and that group's prices separately; official OpenAI prices do not determine relay charges. Each fresh preview shows the actual model, complete destination, limits and body before any spending is approved.

After configuring the backend environment, check readiness from the repository root:

```powershell
uv run --offline --project backend --cache-dir .tmp/uv-cache python -m frag_api.providers.pi_readiness
```

Phase 5 adapter acceptance uses synthetic evidence: validate the Pi wire, a native read through the real CLI carrier, result feedback, finish, Context, Inference, durable report and human semantic review. A separately selected human-operated KB check can use Harness's local-file workflow with exact outbound approval. RAG Lab keeps its bundled synthetic identity. The development ledger records actual results and explicitly marks pending live runs. Offline scripted successes demonstrate host behavior; they do not establish real GPT performance or evidence support. Complete selected-KB integrated acceptance belongs to Phase 8.
