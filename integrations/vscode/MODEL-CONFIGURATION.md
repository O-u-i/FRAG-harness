# VS Code model configuration

Plan E consumes the stable `vscode.lm` API. Configure providers in **Chat: Manage Language Models**, rather than a FRAG/Pi model page. In the default Windows Code profile the file is `%APPDATA%\Code\User\chatLanguageModels.json`. For named profiles, Insiders or portable installations, locate the actual active-profile file and set the application setting `frag.modelConfigFile`; FRAG does not guess a different profile or copy its configuration.

For a Custom Endpoint using Responses, configure the following in that provider object:

| Location | Requirement |
|---|---|
| `vendor` | `customendpoint` |
| `apiType` | `responses` |
| `apiKey` | A VS Code-managed `${input:...}` secret reference |
| `models[].id` / `name` | The actual provider model ID and display name |
| `models[].url` | The provider's supported `/responses` URL |
| `models[].maxInputTokens` / `maxOutputTokens` | Limits verified from the provider; do not invent model limits |
| `models[].supportsReasoningEffort` | Only the effort values supported by that provider/model |
| `models[].reasoningEffortFormat` | `responses` for this reasoning format |
| `settings[modelId].reasoningEffort` | Saved default, for example `high` when supported |

The settings key must match the underlying Custom Endpoint model ID. `agent-host-copilotcli`'s `thinkingLevel` belongs to a different registration. Do not use a global debugging reasoning override. FRAG does not write provider entries, extract keys, or change effort settings.

Select one model in the native FRAG composer. Research, Context and Inference all use it. A per-turn temporary effort override is rejected; the FRAG picker has no effort submenu. The review shows **Saved effort**, meaning the observed provider configuration. Provider defaults may apply when no saved value exists. That label does not prove a relay executed the requested effort.

FRAG requests output caps of 800 tokens for Research, 1,500 for Context and 2,000 for Inference. The selected provider/model must support these caps and JSON responses. Configured limits and effort values must come from that provider's actual capabilities; compatibility errors do not trigger fallback to another model or an automatic retry.

The pinned implementation checked for VS Code **1.140.0**, commit `07f806f999227108933c2e30515b26eecc1fda74`, and installed Copilot Chat **0.68.0** inherits saved per-model configuration in stable `sendRequest()`. The reviewed output-limit route is `modelOptions.max_tokens` → provider request option → Responses `max_output_tokens`. These are source/manifest checks; synthetic bridge tests verify the consumer arguments. Recheck after upgrades. Fresh human-approved calls are needed to verify a real provider's behavior.

Each preview freezes two user messages, JSON output instructions/schema, `modelOptions.max_tokens`, selected model identity and a configuration revision. The extension rechecks metadata and file bytes before calling the model, rejects duplicates and requests containing tool/effort overrides, bounds text output and cancels on timeout. The Host still performs strict JSON, schema, evidence-ID, citation and run-budget checks. Research proposals can use only FRAG's existing selected-source read tools.

The approval boundary is **model API input**, not the provider's final HTTP body. VS Code/provider code can insert instructions, adapt requests or retry internally. FRAG adds no automatic retries; supplier retries, final wire fields, actual token usage and billing remain unknown. Unknown outcomes do not resend automatically. Configuration or source changes require fresh preview/approval; legacy Pi runs cannot resume.

Authoritative references: [Custom Endpoint configuration](https://code.visualstudio.com/docs/agent-customization/language-models#_custom-endpoint-configuration-reference), [stable Language Model API](https://code.visualstudio.com/api/extension-guides/ai/language-model), [saved configuration injection](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/workbench/contrib/chat/common/languageModels.ts#L1531), [provider option mapping](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/src/vs/workbench/api/common/extHostLanguageModels.ts#L349), [provider reasoning/configuration](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/extensions/copilot/src/extension/conversation/vscode-node/languageModelAccess.ts#L834), [output override](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/extensions/copilot/src/extension/prompt/node/chatMLFetcher.ts#L161), [Responses output limit](https://github.com/microsoft/vscode/blob/07f806f999227108933c2e30515b26eecc1fda74/extensions/copilot/src/platform/endpoint/node/responsesApi.ts#L150).
