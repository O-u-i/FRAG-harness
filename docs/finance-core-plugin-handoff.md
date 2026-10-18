# Optional official Finance Core reader

```text
Cross-repo impact: BOTH_REQUIRED
Contract change: ADDITIVE
Other repo status: UPDATED
Required compatible version: FC product/API 3.8.0; official reader 1.8.0 / protocol 2; FRAG 1.13.2
```

FC owns the adapter source and deterministic financial reports. This BOTH task exact-pins official reader 1.8.0 / API 3.8.0 after FC contract/synthetic tests and official artifact verification. It adds a bounded economic summary to the exact whitelist while preserving Monthly Review v1 and GET-only behavior. Other personal-finance, dated Living, activity/opening and debt-detail/write endpoints are not available through the reader; existing owner-only routes remain owner-only. No recommendation runtime or financial calculation in FRAG is included. This note is not publication, production installation or standing cross-repository authorization.

Only `finance-core-frag-plugin-v1.8.0.zip` is installable, SHA-256 `444ac989e16e3fdaf6d4c0be392da6506492423cfece7b29d70518311c71c9a8`. The installed three-file package digest is `7fb0de95e326b5fb156f267d13ef00367deee91a0ab33f4b948180e93873c089`; minimum Host is 1.13.2. Manifest/file bytes are checked before execution and before/after reads. Earlier archives remain unchanged historical artifacts; they are not compatible with this reader. Official UI bytes are integrity-checked archive content, not an active FRAG page. Core FRAG runs without FC.

## Private configuration

Stop the target project backend before installing. From its installed backend directory run `.venv/Scripts/python.exe -m frag_api.fc_reader --archive <official-archive> --state-dir <private-project-state>`. **FRAG: Open Private State Folder** locates the target. Installation grants no source or record access.

Configure only in the private state directory's `fc.env`:

```dotenv
FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788
FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174
FINANCE_CORE_PLUGIN_READ_TOKEN=<backend-only-ledger-read-token>
FINANCE_CORE_PLUGIN_RECORDS_JSON={"<approved-workspace>":["monthly-review:2025-03"]}
```

Use valid real Workspace IDs; placeholders are not runnable configuration. At most ten exact IDs are whitelisted across Workspaces. Restart, then explicitly enable finance-core in Settings. Configure `frag.financeCoreUI` separately for the standalone UI. Credentials never enter Webview inputs, packs, browser storage, logs or Git.

## Read contract and approval scope

`operation: list` discovers configured IDs only. Report labels are derived from the whitelist without fetching every report. `operation: read` accepts one listed Workspace and selected listed IDs. Package, supplier configuration and record revisions are revalidated before finalized delivery; a changed report or whitelist rejects an outstanding pack.

- `monthly-review:YYYY-MM` reads `/api/v3/workspaces/{workspaceId}/reports/monthly-review?month=YYYY-MM`. The concrete anchor must be completed in the Asia/Shanghai calendar; the report includes the anchor and prior two months.
- `economic-evidence:YYYY-MM-DD:YYYY-MM-DD` reads only `/api/v3/workspaces/{workspaceId}/reports/economic-evidence?asOf=...&through=...`. Dates and the 1–366 day horizon are checked before HTTP. A new window requires explicit whitelist authorization. Discovery derives labels without fetching every report.
- Economic summaries preserve gross per-segment/currency cash and debt stocks, actual observation dates, planned outflows, confirmed current-balance repayment dates, out-of-horizon debt amounts/counts and explicit coverage/missing facts. Forecasts are not debt maturities; historical missing dates remain unknown. Future charges, external completeness and personal disposable availability are not assessed. No account IDs/names, agreement text, sources or notes enter the summary. FC alone calculates these values and owns recording/confirmation/storage.
- Only posted ledger entries contribute. Cash is netted per entry/currency to exclude internal cash transfers. Recognized income/expenses use valuation amounts in the entry's balancing currency. Currencies are never implicitly converted or merged.
- Reversals affect their own month and expose signed adjustments already included in totals. Account roles use current Master data, not historical role snapshots. Unassignable posted dates block all totals. Real-world completeness stays unknown, even after reconciliation passes.
- The summary omits account names/IDs, Journal descriptions, references and posting memos. The adapter validates its strict summary shape and does not truncate it. `requiredEvidenceIds` protects the report in backend byte fitting, extension token fitting and completion; insufficient capacity rejects delivery.
- `entry:<approved-id>` and `draft:<approved-id>` remain optional explicit detail selections. Their whitelist is separate authorization to disclose those records; a monthly report does not authorize expansion to them. Legacy bounded record formatting is unchanged.

There is no FC SQLite access, financial recalculation in FRAG, mutation, imported Dashboard, provider credential access, automatic retry, wildcard month, scheduler or autonomous Memory update. FC's own UI authenticates and owns all writes.

## Verification boundary

Default tests use synthetic sources and mocked HTTP. Local acceptance explicitly reads the user-prepared acceptance-input files in an isolated backend program; they are not Host `fc.env`, are not copied to Webview/configuration/Git and are never printed. Test-token writes are only FC isolated HTTP checks against the verified sandbox; the official reader remains GET-only. Real-token identity/permissions/schema checks do not authorize financial reports or a real Run. Local contract, isolated loopback integration, browser, native invocation, paid-provider behavior and human financial-semantic acceptance must be reported separately. Passing missing-data refusal alone is not complete Slice B acceptance; positive whole-plan plus FC recorded-scope evidence is also required.
