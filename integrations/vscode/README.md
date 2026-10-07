# FRAG in VS Code Agents

Plan D connects the existing governed FRAG runtime to the native Agents window through an opt-in loopback **AHP 0.9.0** host. The accepted entry is **Remote → FRAG**, with a new FRAG-designed page in the right-hand **Browser** tab. The standalone application keeps its existing GUI.

## Start and connect

```powershell
npm run agents
```

The command builds the frontend, starts the backend on `127.0.0.1:8787`, and writes ignored `.local-runtime/vscode/connection.settings.json`. Merge its entries into Agents settings while preserving other hosts. It does not edit VS Code settings automatically, install an extension, or change VS Code source. Existing backend configuration and credentials remain in `backend/.env`.

1. In the workspace picker above the native composer, choose **Remote**, the online **FRAG** host, then **Folders → frag-workspace**. Confirm the harness is FRAG and the model label shows the backend Context/Inference routes.
2. Send a task of 3–500 characters. Native Send saves a task; it does not select evidence or call a model.
3. Open **Sessions: Browser** (`Ctrl+Shift+B` on the verified Windows build). Enter the session review URL in the native reply, or `http://127.0.0.1:8787/review` and choose the session.
4. Select evidence, preview the full request, confirm it, and approve Context. Explicitly prepare and approve Inference next. Optional Research requires its own approval for each model turn.
5. Review the saved output in the Browser page. The native conversation receives the same run's result, citations and separate structural/human-review status.

Keep the terminal running while connected; `Ctrl+C` stops the host. Native Stop pauses at the next safe host boundary and cannot retract an external request already sent. Restart or source changes require fresh preview and approval. Unknown outcomes never resend automatically.

## UI and ownership

The new page merges Harness/RAG evidence and Context controls into **Workspace → Evidence → Context → Inference → Review**. **Runs** displays one report with Output, Requests, Sources and Review tabs. **Customizations** groups Memory, Plugins and model readiness. The layout adapts the supplied Line Sidebar and Glass Icons references, with a dependency-free Stepper and compact selects. Ordinary text uses **Archivo Variable 5.3.0**, with system monospace for code. Component structure, font provenance and distributed notices are documented in [FRAG Review](../../src/agents/README.md).

VS Code owns the native conversation and Browser tab; FRAG owns evidence selection, durable runs, exact requests, approvals and human review. This route needs no VSIX. Browser opening and choosing the review URL are manual; a dedicated title-bar logo button and separate native Review tab are outside this delivery.

Registering a session does not transfer native skills, MCP, hooks or tool descriptors. The adapter has no native coding-tool, terminal or filesystem bridge. Its empty virtual workspace is a navigation anchor; evidence stays under explicit FRAG selection. Native global Customizations counts describe VS Code, not FRAG adoption.

## Verified compatibility and limits

The implemented route was exercised in **VS Code 1.140.0**, commit `07f806f999227108933c2e30515b26eecc1fda74`, with synthetic local evidence and Fake providers. Native task → right-hand source selection → separate Context/Inference approvals → saved run → native result was observed. Exactly two Fake calls completed the fixed flow; real model calls were zero. This does not repeat or extend the maintainer's reported real-model acceptance of the existing runtime.

Backend regression covers selected files, RAG, bounded Research, stale controls, source changes, duplicate messages, restart, unknown outcomes, cancellation and malformed protocol input. This bounded carrier is not a general AHP coding agent. VS Code can display an unsupported-terminal notification; dismiss it to resume Browser. Recheck discovery, session creation, Browser placement and result rendering after VS Code updates.

See [native evidence and pinned references](NATIVE-AGENTS.md), [backend adapter](../../backend/frag_api/services/AGENT-HOST.md), and [architecture diagram](../../docs/architecture/vscode-migration/architecture.html).

This directory's `extension.cjs` and manifest retain the earlier original offline Chat extension probe. That route failed independently and is not the implemented carrier. See [historical probe](CHAT-PROBE.md).
