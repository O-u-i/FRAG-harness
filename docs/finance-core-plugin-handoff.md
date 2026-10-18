# Optional official Finance Core reader

```text
Cross-repo impact: BOTH_REQUIRED
Contract change: ADDITIVE
Other repo status: UPDATED
Required compatible version: FC product/API 3.9.0; official reader 1.9.0 / protocol 2; FRAG 1.13.3
```

FC owns the adapter source and deterministic financial reports. This BOTH task exact-pins official reader 1.9.0 / API 3.9.0 after FC contract/synthetic tests and official artifact verification. It adds a provisional month-to-date summary while preserving Monthly Review v1, economic evidence and GET-only behavior. Other personal-finance, dated Living, activity/opening and debt-detail/write endpoints are not available through the reader; existing owner-only routes remain owner-only. No recommendation runtime or financial calculation in FRAG is included. This note is not publication, production installation or standing cross-repository authorization.

Only `finance-core-frag-plugin-v1.9.0.zip` is installable, SHA-256 `f7f53aa42fc6ff213ffee77291ad6b490ee2ae68a97123c057e494e76a30ce2a`. The installed three-file package digest is `9188219f3ccb712e62bec2ad268f22cb3f0db3966b6dff82a357d1b68fa20bef`; minimum Host is 1.13.3. Manifest/file bytes are checked before execution and before/after reads. Earlier archives remain unchanged historical artifacts; they are not compatible with this reader. Official UI bytes are integrity-checked archive content, not an active FRAG page. Core FRAG runs without FC.

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
- `month-to-date:YYYY-MM-DD` reads only `/api/v3/workspaces/{workspaceId}/reports/month-to-date?asOf=YYYY-MM-DD`. It covers that month's first day through the exact nonfuture date, inclusive. Its single-period summary is explicitly partial and posted-Journal-only; unrecorded days and external completeness remain unknown. No invented preceding months, whole-month comparisons or balance-derived spending. Posted opening equity entries can move cash without creating income. Living observations, valuations and forecasts are not Journal activity. The full report is required evidence and never replaces economic-stock/obligation prerequisites.
- `economic-evidence:YYYY-MM-DD:YYYY-MM-DD` reads only `/api/v3/workspaces/{workspaceId}/reports/economic-evidence?asOf=...&through=...`. Dates and the 1–366 day horizon are checked before HTTP. A new window requires explicit whitelist authorization. Discovery derives labels without fetching every report.
- Economic summaries preserve gross per-segment/currency cash and debt stocks, actual observation dates, planned outflows, confirmed current-balance repayment dates, out-of-horizon debt amounts/counts and explicit coverage/missing facts. Forecasts are not debt maturities; historical missing dates remain unknown. Future charges, external completeness and personal disposable availability are not assessed. No account IDs/names, agreement text, sources or notes enter the summary. FC alone calculates these values and owns recording/confirmation/storage.
- Only posted ledger entries contribute. Cash is netted per entry/currency to exclude internal cash transfers. Recognized income/expenses use valuation amounts in the entry's balancing currency. Currencies are never implicitly converted or merged.
- Reversals affect their own month and expose signed adjustments already included in totals. Account roles use current Master data, not historical role snapshots. Unassignable posted dates block all totals. Real-world completeness stays unknown, even after reconciliation passes.
- The summary omits account names/IDs, Journal descriptions, references and posting memos. The adapter validates its strict summary shape and does not truncate it. `requiredEvidenceIds` protects the report in backend byte fitting, extension token fitting and completion; insufficient capacity rejects delivery.
- `entry:<approved-id>` and `draft:<approved-id>` remain optional explicit detail selections. Their whitelist is separate authorization to disclose those records; a monthly report does not authorize expansion to them. Legacy bounded record formatting is unchanged.

There is no FC SQLite access, financial recalculation in FRAG, mutation, imported Dashboard, provider credential access, automatic retry, wildcard month, scheduler or autonomous Memory update. FC's own UI authenticates and owns all writes.

## First real Vault Run

**Prerequisites:** manually install matching FRAG 1.13.3 Host/VSIX; FC must serve API 3.9.0. Retain the same VS Code instance/profile/project. Confirm the source and selected native provider before disclosing real summaries. The following is a user-operated factual check, not permission for a developer to execute a real Run or enter Slice C.

### 1. Install the reader locally

In the target VS Code window, `Ctrl+Shift+P` → `FRAG: Open Private State Folder`. Copy that folder's address, then run `FRAG: Stop Evidence Backend`. Obtain exactly `finance-core-frag-plugin-v1.9.0.zip` from FC's `docs/release/` folder; do not use an older archive.

Open **PowerShell 7**, from any directory:

```powershell
$ErrorActionPreference = 'Stop'
$State = Read-Host 'Private state folder full path, without quotes'
$Archive = Read-Host 'Full path to finance-core-frag-plugin-v1.9.0.zip, without quotes'
Set-Location -LiteralPath (Join-Path $env:LOCALAPPDATA 'FRAG\host\1.13.3\backend')
.\.venv\Scripts\python.exe -X utf8 -m frag_api.fc_reader --archive $Archive --state-dir $State
if ($LASTEXITCODE -ne 0) { throw 'Reader installation failed; stop here.' }
```

Expected: `FC reader installed`. No financial report has been read.

### 2. Create private configuration

In **that private state folder**, manually create **`fc.env`**, not `fc.env.txt`. If one already exists, stop and review it; do not overwrite it or copy acceptance-input files over it.

```dotenv
FINANCE_CORE_PLUGIN_API_URL=http://127.0.0.1:8788
FINANCE_CORE_PLUGIN_UI_URL=http://127.0.0.1:5174
FINANCE_CORE_PLUGIN_READ_TOKEN=<real-vault-ledger-read-token>
FINANCE_CORE_PLUGIN_RECORDS_JSON={"<real-workspace-id>":["month-to-date:2026-08-18"]}
```

Replace the placeholders and example date **locally** with the explicitly approved values. Use only the real Vault's `ledger:read` token, not the sandbox write token. Acceptance keys `FC_API_URL`, `FC_WORKSPACE_ID`, `FC_ACCESS_TOKEN` are not Host configuration keys and are not automatically loaded. Never paste either file, token or authentication headers into chat or Webview inputs.

### 3. Enable and discover, then read

1. `Ctrl+Shift+P` → `FRAG: Open Settings` → `Finance Core whitelist`.
2. Keep `Enable this source` checked; review the approval checkbox and click `Save authorization`. FC needs **no local index build**. `Reader: available` means the package loaded, not that token/API access has passed.
3. In native Chat, select the intended model and enable `frag_fc_read`. Approval allows the selected summary to reach that provider.
4. First ask: **Use #frag_fc_read with operation "list" only. Do not read financial records.** Check that only the intended Workspace and exact record ID appear.
5. Then explicitly ask to read **that one listed record** using operation `read`. Request only factual cash-movement versus income/expense interpretation, separate currencies and coverage limits; no spending/investment action advice or additional records.
6. `Ctrl+Shift+P` → `FRAG: Open Runs`. Expand the **read** Run, then **Full returned text**; the short preview alone is abbreviated. Check status `completed`, the exact cutoff, all currencies and coverage; **Advanced · complete audit JSON** retains `requiredEvidenceIds`. A completed discovery Run alone is not financial-read success. Judge the native answer separately.

If API/reader versions, Workspace, dates, revisions or capacity fail, stop. Do not widen permissions, substitute a completed month, call owner-only endpoints or treat missing data as zero. Disable `finance-core` and save authorization to stop optional reads; existing Runs remain immutable. This report does not enable production recommendations or automatically authorize Slice C.

## Verification boundary

Default tests use synthetic sources and mocked HTTP. Local acceptance explicitly reads the user-prepared acceptance-input files in an isolated backend program; they are not Host `fc.env`, are not copied to Webview/configuration/Git and are never printed. Test-token writes are only FC isolated HTTP checks against the verified sandbox; the official reader remains GET-only. Real-token identity/permissions/schema checks do not authorize financial reports or a real Run. Local contract, isolated loopback integration, browser, native invocation, paid-provider behavior and human financial-semantic acceptance must be reported separately. Passing missing-data refusal alone is not complete Slice B acceptance; positive whole-plan plus FC recorded-scope evidence is also required.
