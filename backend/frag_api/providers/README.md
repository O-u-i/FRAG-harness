# Model transports

`prepared.py` freezes and verifies one request. `llm.py` retains the existing Fake and direct Responses providers; `vscode.py` consumes the installed extension's authenticated loopback model bridge. Every transport enters the existing governed Context/Inference/Research orchestration and validators.

Direct backend calls use PreparedCall version 1 with an exact HTTP body. Installed VS Code calls use version 2 with exact stable API messages/options plus saved-configuration provenance. Provider HTTP adaptation, internal retries and usage are unknown for the latter. VS Code owns model credentials; the Host sees only a process-local bridge secret. No secrets are persisted in prepared calls or reports.

Pi execution has been removed. Its transport tag and historical replay fields remain decoder-only for saved reports; no worker, wire generator, provider or recovery path uses them. Capture scoring refuses the retired transport rather than reconstructing or certifying it.

The extension uses only node built-ins and the stable model API. A provider cannot select files, approve a call, promote memory or run native coding tools. [Configuration requirements](../../../integrations/vscode/MODEL-CONFIGURATION.md) and [Host ownership](../services/AGENT-HOST.md).
