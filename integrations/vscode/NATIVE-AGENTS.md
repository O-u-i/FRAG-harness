# Native Agents integration evidence

## Implemented route

On 2026-10-07 the original bounded FRAG adapter connected to **VS Code 1.140.0**, commit `07f806f999227108933c2e30515b26eecc1fda74`, negotiating **AHP 0.9.0**. The maintainer accepted a local host under Remote and the right-hand Browser page. The test used the actual backend adapter, a synthetic source and Fake model providers.

| Check | Observation |
| --- | --- |
| Host discovery | FRAG appeared Online under Remote. |
| Harness and model ownership | The empty `frag-workspace` selected FRAG and the backend synthetic Context/Inference routes. |
| Native task | `chat/turnStarted` saved one durable task without evidence access or model execution. |
| Right-hand page | The new `/review` page opened beside the conversation in Browser. |
| Source selection | One synthetic local file section was explicitly selected. |
| First approval | Complete Context request and bindings were visible; approval needed explicit confirmation. |
| Second approval | Inference needed a new preview and unchecked confirmation; consent did not carry over. |
| Saved result | One existing RuntimeService run stored both attempts, validated cited output and human-review status. |
| Native result | The central conversation rendered that same run's answer/citations and completed the turn. |
| Backend restart | Native reconnect fell back to fresh version-negotiated initialization and restored saved sessions without another model request. |
| Review persistence | A synthetic pause saved one review while preserving the model original; semantic review remained undetermined. |
| Font loading | Review loaded local Archivo WOFF2 without requesting the standalone font assets. |
| Model calls | One Fake Context and one Fake Inference call; zero real-provider calls. |

Frontend, backend and Pi regressions are separate evidence from this desktop flow. Research and selected RAG have synthetic backend coverage. Real KB indexing, live FC access and paid model requests were not performed. The maintainer's reported real-model/manual verification remains a separate result.

## Protocol boundary

The pinned build's `WebSocketAgentHostContribution` creates a `RemoteAgentHostSessionsProvider`. A root snapshot advertises FRAG and actual backend route readiness; subscriptions carry native session/chat state and actions. Remote identifies the connection type: the FRAG process is on the same machine. No VSIX, proposed Chat extension API or VS Code source modification is needed.

Native identity, redacted task text and run links persist in the existing runtime database. Replay/reconnect restores state without dispatching a request. Review control binds session version, turn ID, run version, exact fingerprint and fresh one-use token. Existing flows own source/configuration revalidation, budgets, redaction, model execution and recovery. See [adapter](../../backend/frag_api/services/AGENT-HOST.md).

Only the empty virtual `file:///frag-workspace` can resolve/list. Repository files, KB files, credentials and FC records are not exposed through AHP. Source access follows FRAG's explicit selectors. Native active-client tool/customization descriptors are acknowledged as empty registrations and are neither persisted nor executed.

AHP activity conveys saved progress without appending every intermediate report to the conversation. Final output derives from the authoritative run. Stop waits for the next safe mutation boundary and cannot cancel an already dispatched HTTP request. Terminal/file-write operations are unsupported. A native terminal notification can pause Browser until dismissed.

## Reproduction

Follow [startup and navigation](README.md). The test used a separate native profile with telemetry/updates disabled and no sign-in. That profile can still discover native global customizations; Skills/Tools counts do not establish FRAG integration.

Synthetic sources, runtime databases, desktop profiles, screenshots and receipts stay under ignored `.tmp/`. Public documents contain no personal source paths, selected evidence or credentials. Reference protocol source was inspected but not copied into distributed implementation.

The earlier echo/static-page test established placement. The [proposed Chat extension test](CHAT-PROBE.md) failed with a renderer `loadSession` error and remains a historical record. Automatic Browser opening, dedicated logo/Review tabs and native customization/tool adapters are outside this delivery.

## Version-pinned sources

- [WebSocket host contribution](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/sessions/contrib/providers/remoteAgentHost/browser/webSocketAgentHost.contribution.ts): the native entry point.
- [Remote Agent Host provider specification](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/sessions/contrib/providers/remoteAgentHost/REMOTE_AGENT_HOST_SESSIONS_PROVIDER.md): connection ownership and dynamic agent discovery.
- [Agent Host protocol client](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/platform/agentHost/browser/agentHostProtocolClient.ts): handshake, subscriptions and action dispatch.
- [Protocol version registry](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/platform/agentHost/common/state/protocol/version/registry.ts): the pinned build's protocol versions.
- [Native Browser action](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/sessions/contrib/editor/browser/addTabActions.ts): the tested Browser command and keyboard binding.

Revalidate these gates on the exact installed build after a VS Code update; experimental protocol and UI interfaces may change.
