# Host HTTP CLI

The CLI operates the running FastAPI application. Session history, source policy,
approvals and tool execution have the same owner as the browser. The CLI does not
open the runtime database, load `.env`, start an application or read evidence files.
Start the backend separately, then run these commands from `backend` with its Python
environment:

```powershell
.venv/Scripts/python.exe -X utf8 -m frag_api.cli health
.venv/Scripts/python.exe -X utf8 -m frag_api.cli capabilities
.venv/Scripts/python.exe -X utf8 -m frag_api.cli sources
```

The default host is `http://127.0.0.1:8787`. A different numeric loopback address or
port can be supplied using `--base-url` before the command. Public hosts, DNS names,
HTTPS, URL credentials, path prefixes, query strings and fragments are rejected.
Proxy environment variables and redirects are disabled. Ordinary operations have
a ten-second HTTP timeout; an explicitly approved model stage allows up to 125
seconds for the host's bounded model call and response. No operation retries.

## Inputs and commands

Commands with a body accept `--input request.json` or one bounded JSON object from
stdin. A request file must be an explicitly named JSON file; credential and database
files are not accepted. Each HTTP request is limited to 16 KiB. Responses and the
registered host process output are limited to 1 MiB. Malformed data, errors,
redirects and timeouts produce a safe error code, without printing server errors,
request echoes or connection details.

| Command | Input and behavior |
| --- | --- |
| `health`, `capabilities`, `sources` | Read host readiness, actual registrations or available local file metadata. |
| `source-inspect` | `{"relativePath":"evidence.md"}` returns selectable locators through the host. |
| `sessions` | List the latest Sessions. |
| `session-create` | `{"title":"Evidence review"}` creates a Session. |
| `runs [--session-id ID]` | List Runs, optionally within one Session. |
| `report --run-id ID [--format json\|markdown]` | Read the canonical report or its deterministic Markdown rendering. |
| `preview --kind harness\|rag` | An explicit Harness or RAG source request creates a Run and exact Context preview. |
| `recovery-preview --run-id ID` | `{"sourceRequest":{...}}` revalidates the explicit selection and prepares a fresh checkpoint approval. |
| `reopen --run-id ID` | `{"sourceRequest":{...}}` starts a linked new Run. |
| `review --run-id ID` | The existing review contract: target, decision, checklist and note. |
| `revision --run-id ID` | `{"result":{...},"note":"..."}` creates a separately reviewed human revision. |
| `tool-execute --run-id ID` | `{"sourceRequest":{...},"call":{"callId":"read-1","name":"kb.read","arguments":{...}}}` executes a selected read tool. |
| `execute-context --kind harness\|rag [--run-id ID] --approve` | Prepare and interactively approve only Context; supplying a Run ID resumes its Context checkpoint. |
| `execute-inference --kind harness\|rag --run-id ID --approve` | Revalidate the explicit source request and interactively approve only Inference. |
| `json` | Execute a declared structured host operation from stdin; model-execution commands are excluded. |

Harness requests contain `goal` and explicitly selected `fileSelections` or the
existing allowed plugin selection. RAG requests contain the synthetic `datasetId`,
`query` and `topK`. Both use the existing task contract and optional Session/parent
Run fields. Inspection, previews and read tools do not send model requests.

Recovery reads the selected Run's report and refreshes only the host-owned
`sessionId` and `parentRunId` in the explicit source request. This supports selections
retained from a parent after Reopen. Source contents, locators, goal and task remain
the caller's selection and are revalidated by the host. Changed source revisions,
configuration or request contracts reject continuation.

## Separate model approvals

Prepare one JSON file containing the exact selected source request. Keep private
request files in an ignored local directory. In a terminal, run:

```powershell
.venv/Scripts/python.exe -X utf8 -m frag_api.cli execute-context --kind harness --input ../.local-runtime/selected-request.json --approve
```

The CLI obtains a fresh server preview and prints its complete `PreparedCall`,
including the destination, messages, output schema, version bindings and limits.
It requires typing `APPROVE` followed by the full displayed fingerprint. Cancellation
sends no model request. A pipe, noninteractive process or missing `--approve` cannot
execute a model stage. `--approve` alone is insufficient.

Context executes once and returns a Run ID. Its automatically prepared Inference
token is unused and redacted from CLI execution output. Start Inference explicitly:

```powershell
.venv/Scripts/python.exe -X utf8 -m frag_api.cli execute-inference --kind harness --run-id RUN_ID --input ../.local-runtime/selected-request.json --approve
```

This obtains another fresh preview after source revalidation and requires another
exact confirmation. The CLI never automatically executes the next stage. A timeout
or interruption requires inspecting Run history; an unknown external outcome is
never automatically resent. History reads and reviews do not authorize model calls.

Preview commands expose a short-lived, one-use approval token on stdout because
they return the host's preview contract. Treat this output as volatile: do not commit
it, record it as reusable approval or redirect it into public artifacts. The CLI does
not save approval output automatically. Run reports do not contain reusable tokens.

## Selected tools and the registered entry

Obtain a source binding from the Run preview. A tool argument must carry that
binding's exact `identity`, `revision` and explicitly selected `locatorIds`.
`kb.search` also takes `query` and an optional bounded `limit`; `kb.read` takes the
selected `evidenceIds`. The host verifies the Run's selection and current revision,
then runs native search or the actual controlled read process. This operation does
not require a model approval and cannot extend source scope. Tool calls have unique
`callId` values; the stored result is bound to the same ID. FC records are excluded
from these KB tools. Registration does not grant authorization.

The `frag.host` CLI registration has a fixed Python executable, backend working
directory and `-X utf8 -m frag_api.cli --base-url PINNED_URL json` arguments. It uses
the existing controlled process carrier with a ten-second deadline, sanitized
environment and 1 MiB output cap. Caller payloads never become shell commands or
process arguments. Only the declared operating-system environment fields are
inherited; provider keys, proxies and `PYTHONPATH` are excluded.

The structured stdin contract is `HostCLIRequest`; stdout is `HostCLIResponse`:

```json
{"command":"runs","sessionId":"SESSION_ID","payload":{}}
```

```json
{"command":"runs","result":[]}
```

The registered URL is pinned outside the request schema. Caller URL overrides,
unknown fields, path escapes and executable model commands fail validation. This
entry is a user-operated host interface; it is not exposed as a Research model tool.
Semantic acceptance remains human review; CLI or Fake-provider success does not
establish that evidence supports a real-world claim.
