# Governed KB Research

Research is an optional bounded evidence-collection runner registered beside the fixed Context/Inference runner. The application lifecycle owns both runners, the runtime SQLite journal and the tool registries. Finance Core is excluded from Research; its released read-only fixed workflow remains available.

Research sends a selected source manifest, locator descriptions, tool input contracts and an output schema on its first model turn. It does not send the selected excerpt bodies until the model proposes a complete allowed call and the host executes a real tool. `kb.search` searches the selected snapshot with the native executor; `kb.read` starts the fixed isolated Python CLI carrier. This does not grant access to an unselected file, locator, source revision or Workspace.

The host protocol is a structured `ResearchDecision`: either `continue` with complete `toolCalls`, or `finish` with observed `evidenceIds` and `missingInformation`. These are model proposals evaluated by host policy. The optional [Pi adapter](pi-adapter.md) normalizes completed native calls into this contract and replays the actual results; streaming fragments never execute. Fake/scripted acceptance validates the real host/tool path. Synthetic live GPT and human semantic review remain Phase 5 gates.

## One approval, one model dispatch

Start with `POST /api/runtime/research/preview`, passing `{kind, sourceRequest}`. Continue or restore with `POST /api/runtime/runs/{runId}/research/preview`, passing the same original explicit `{sourceRequest}`. The response is a `ResearchPreview` with `stage`, complete immutable `preparedCall`, `fingerprint`, a short-lived `approvalToken`, turn number and limits. The canonical report persists request specifications, not reusable tokens.

Approve exactly that request through `POST /api/runtime/runs/{runId}/research/execute` with `{sourceRequest, fingerprint, approvalToken, approved: true}`. The host revalidates the complete typed selection before rereading sources, checks revisions/configuration/trajectory, consumes the token once and runs one LangGraph dispatch. A valid `continue` proposal can execute allowed read tools serially; observations are durably paired to their owning `callId`. The response is the canonical `RunReport`. It never sends the next model request or issues its approval automatically.

The next explicit preview includes previous decisions and actual successful or failed tool observations. A finish can select only evidence returned by completed authorized tool calls. The next request is Context over that subset; the original selection remains preserved in the report. Context and Inference each require their own fresh preview and approval through the same Research endpoints. Known Research gaps are carried in both formal requests and cannot disappear from validated formal results.

Default limits are three Research model turns, six total serial tool calls, 10 seconds per tool, 16 KiB per structured tool result, 800 output tokens per Research turn, 120 seconds per model call and zero automatic retries. Context/Inference retain 1,500/2,000 output-token limits. The cumulative Run budget is 30,000 tokens; unavailable usage uses conservative request estimates. The complete wire request also retains the existing 6,000-token input budget and 25% reserve. Exhaustion stops the Run visibly.

## Recovery and human control

The report has nullable `research` history; old fixed records remain readable. Malformed complete proposals and forbidden arguments are rejected before result persistence. Well-formed results are saved before the remaining checkpoint checks, so a reliably saved result can be validated on restart without resending it. Startup never executes pending tools or sends another model request. Explicit source reselection/resume may finish unexecuted authorized tools or reuse completed observations, then produce a new preview. An interrupted dispatch becomes `outcome_unknown` and cannot resume automatically.

Source, parser, provider route, tool/CLI contract or loop configuration changes reject continuation. Saved observations must still match the actual proposal's source, locator and evidence subset, tool version/carrier and call identity. A newer human pause or rejection survives an in-flight return. Concurrent previews use atomic attempt/turn ownership and reject stale preparation. Input changes use a linked new Research Run through the existing Reopen endpoint; the old Run is retained.

Page, JSON and Markdown report views use the same structured record. Structural checks and citation membership do not establish factual support. Human semantic review remains separate; real provider and selected KB acceptance belong to their later phases.
