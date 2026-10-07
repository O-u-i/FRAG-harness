# Native Agent Host adapter

`agent_host.py` implements an original, bounded AHP 0.9.0 facade. `agent_review.py` binds explicit review actions to the existing Harness/RAG/Research flows. No provider SDK or new orchestration framework is introduced.

Enable it with `FRAG_AGENT_HOST_ENABLED=1`; the launcher binds Uvicorn to `127.0.0.1:8787`. `/api/agents/ahp` requires a loopback client and loopback Host, and accepts only the native Electron origin or no Origin. Review mutations reject foreign origins. Credentials stay in backend settings and never enter protocol snapshots.

The empty `file:///frag-workspace` is a native navigation anchor, not a filesystem bridge. Only that directory can resolve/list. Reads outside it, terminals, file writes and tool execution are unsupported. Active-client descriptors are acknowledged with empty tool/customization registrations and are not persisted or executed.

`agent_sessions` stores only native identity, redacted task text, carrier state/version and run links inside the existing runtime database. It does not store model request/output duplicates. Run snapshots, attempts, budgets, validation and review remain owned by `RuntimeService`. Native turn IDs are durable replay keys. Reconnect uses fresh snapshots, never event replay or model dispatch. After a process restart, an unknown client receives AHP NotFound and the native client performs a new version-negotiated initialize with its existing subscriptions.

Preparing evidence binds the current native task, session and parent run. The process-only pending record binds carrier version, turn ID, run version, source request and exact preview. Execution requires those bindings plus the matching fresh one-use token; the local pending entry is consumed before dispatch. The existing flow revalidates sources and consumes its own approval. A following stage receives a fresh carrier preview/approval only on explicit request. The existing fixed flow may retain an earlier prepared Inference attempt; it is a preparation record, not another model call. Restart clears pending approvals; unknown outcomes remain governed by existing runtime recovery.

The adapter serializes review mutations locally. Stop waits for that safe boundary and records a pause. It cannot cancel an in-flight external HTTP call. Native status/output observation derives from saved reports and performs no model or evidence operation.

See [review page](../../../src/agents/README.md) and [native compatibility evidence](../../../integrations/vscode/NATIVE-AGENTS.md). Finance Core source and contracts are unchanged.
