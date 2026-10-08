# FRAG Local Host v1.10.0

Private local VSIX for the native VS Code Agents window. Install the matching Host bundle first; this extension does not download or bundle a model runtime.

1. Install the VSIX with **Extensions: Install from VSIX**.
2. Run **FRAG: Enable in Agents Window** in regular VS Code, then reload the Agents window.
3. Run **FRAG: Start Project Host**, explicitly choose your evidence project folder.
4. In Agents, click **New / Ctrl+N**, then the folder-name button above the composer: **Remote → FRAG · project ID → Folders → your project**. Select a model and send your task.
5. Run **FRAG: Open Review**. Paste the copied URL into the right-hand Browser address bar and choose your FRAG session. Select excerpts and approve each stage separately.

FRAG is a selected-evidence conversation agent. It has no native edit, terminal, coding-tool, MCP, Skills or Hooks bridge. Native Customizations remains VS Code's surface; it does not automatically grant FRAG those capabilities.

Model setup belongs to **Chat: Manage Language Models**. The default Windows profile stores it in `%APPDATA%\Code\User\chatLanguageModels.json`. For another profile, set `frag.modelConfigFile` to that profile's actual file. FRAG reads it locally only to bind changes and report a saved `settings[modelId].reasoningEffort`; keys and URLs are never copied to Host storage. There is no FRAG effort override picker. An ambiguous registration fails closed.

The stable `vscode.lm` API receives exactly the previewed user messages and `modelOptions.max_tokens`. VS Code/provider code may add HTTP fields or retry internally. Final HTTP body, provider retries, usage and relay-side effort execution remain unknown. Configuration changes require a new preview. FRAG performs zero automatic retries.

One extension instance owns one bound Host. Starting another project stops its own previous Host; **FRAG: Stop Project Host** removes only its registered address. Closing its VS Code window also stops that owned process. Separate project state lives under this extension's local global storage, keyed by canonical project path. Never place it in project Git.

Optional application settings: `frag.hostInstallation` for the initialized v1.10.0 directory and `frag.modelConfigFile` for the active profile. No backend `.env` or Pi configuration is used by this route. Use a local trusted Windows folder. Recheck Agents discovery and model settings after VS Code updates.
