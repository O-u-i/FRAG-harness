# FRAG Evidence Tools 1.13.4

Registers `frag_search`, `frag_read`, `frag_fc_read` for the **main VS Code window's native Local Agent**, plus Settings/Runs/Memory Webview. It owns a loopback evidence backend, not a model bridge or Agent loop.

Install matching `frag-host-1.13.4.zip` and `frag-bridge-1.13.4.vsix`. Set `frag.hostInstallation` only for a custom location; keep native model credentials/configuration in VS Code. Open one trusted local folder, authorize sources in **FRAG: Open Settings**, explicitly Build / Refresh, then enable tools in native chat.

No composer filling, Send interception, AHP registration or final-answer capture. Source data is not authority. Native tool policy is not replaced by FRAG directory approvals. Runs record finalized FRAG results only; legacy records are read-only, never replayed. Installed `resources/install.md` contains upgrade/troubleshooting instructions.

Private state defaults to VS Code extension storage at `projects/<project-hash>/`.
**FRAG: Open Private State Folder** opens that exact directory. Set
`frag.privateStateRoot` in machine-local User Settings for a custom absolute
private local root, separate from source and Host. Stop the backend and reload
after changing; no existing state is moved or deleted. An empty root starts new
approvals/history. Keep state and `fc.env` out of Git/shared/cloud-synced folders;
FC Vaults and native model credentials stay in their respective applications.

Recommendation safety is model-free and synthetic only. Runs may show separate allowlisted workflow receipts, never draft bodies or human decisions. Production recommendations are unavailable; the foundation does not filter native chat or establish a provider budget guarantee.
