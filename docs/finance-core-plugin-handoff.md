# Optional official Finance Core reader

Cross-repo impact: NONE
Contract change: NONE
Other repo status: NOT_TOUCHED
Required compatible version: FC API 3.1.1; official reader 1.1.0 / protocol 2.

Only `finance-core-frag-plugin-v1.1.0.zip` is installable, SHA-256 `a96d5d2c4c8e4c8a7232db4be825925d37fb80052e74f6eab450744c62ccfacb`. Manifest/file bytes are checked before execution and before/after reads. Generic discovery, protocol-1 runners and plugin UI mounting are removed. Official UI bytes remain integrity-checked archive content, not an active FRAG page.

Stop the project backend. From its installed backend directory run `.venv/Scripts/python.exe -m frag_api.fc_reader --archive <official-archive> --state-dir <private-project-state>`. **FRAG: Open Private State Folder** locates the target. Installation grants no record access.

Configure only in the private state directory's `fc.env`:

```dotenv
FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788
FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174
FINANCE_CORE_PLUGIN_READ_TOKEN=<backend-only-read-token>
FINANCE_CORE_PLUGIN_RECORDS_JSON={"<approved-workspace>":["entry:<approved-id>"]}
```

Use valid real identifiers; placeholders are not runnable configuration. At most ten records are whitelisted. Restart, then explicitly enable finance-core in Settings. Configure `frag.financeCoreUI` separately for the standalone UI.

`operation: list` discovers configured IDs only; `operation: read` accepts one listed Workspace and records. Package/config/record revisions are revalidated before bounded delivery. No SQLite access, finance calculation, mutation, imported Dashboard or automatic retry. FC retains all domain rules, authentication, storage and writes. No FC source/HTTP contract changes are required. Synthetic tests use mocked HTTP, not live financial data.
