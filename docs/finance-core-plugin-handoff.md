# Optional official Finance Core reader

```text
Cross-repo impact: BOTH_REQUIRED
Contract change: ADDITIVE
Other repo status: UPDATED
Required compatible version: FC product/API 3.10.0; official reader 1.10.0 / protocol 2; FRAG 1.13.4
```

FC owns financial rules, calculations, persistence, authentication and its official reader source. FRAG owns explicit source/record authorization, complete bounded evidence, Runs and reviewed Memory. No financial writes, SQLite access, second chat or production recommendation runtime are added to FRAG. Core FRAG works without FC.

## Install and connect

1. Install the [matching FRAG Host and VSIX](../README.md#first-install). The Host bundles and prepares the exact reader at first project start. No separate reader command is needed; earlier installed versions remain for rollback. An explicit reader disable is preserved.
2. In **FC Settings → Connect FRAG**, choose one Vault, a name and a maximum readable range; create the connection and click **Copy FRAG configuration**.
3. In VS Code: `Ctrl+Shift+P` → `FRAG: Connect Finance Core`. It creates the private template once and opens **Notepad** on the exact project-state `fc.env`. Paste with `Ctrl+A`, `Ctrl+V`, `Ctrl+S`. Existing files are never overwritten by the command.
4. In **FRAG Settings → Finance Core**, click **Check connection**. Confirm Vault name/kind and permission ceiling, check at most ten accounts/items or exact dated reports, then explicitly approve and **Save authorization**. No financial index is built.

The target file is `<this extension's private project state>/fc.env`, found/opened by the command rather than by typing a machine-specific hash. **FRAG: Open Private State Folder** remains an optional inspection route. The backend validates a regular unlinked, single-link, bounded file with a private owner/ACL before reading it. It never repairs or overwrites an existing nonprivate file. No model/environment variables are loaded from it.

The state root defaults to VS Code extension global storage, not the source
checkout or FC Vault. A machine-local User Setting, `frag.privateStateRoot`, can
select another private absolute local root; FRAG still appends
`projects/<project-hash>/`. Stop/reload when changing it. Old state is not migrated
automatically. See [private-state location and safeguards](../README.md#private-state-and-location).
An existing empty `fc.env` with inherited/nonprivate permissions can fail before
Notepad opens. Inspect metadata only and obtain explicit single-file repair; do
not weaken the check, delete state or share credentials to diagnose this error.

The FC-generated four lines contain API/UI loopback addresses, the dedicated read token and a single Workspace mapping with **no selected records**. Workspace ID is included automatically. FRAG saves its narrower human selection separately; no JSON editing is needed. The file is backend-only, never a Webview input, tool result, chat attachment, log or Git file. The private editor uses Notepad rather than a native chat-context editor. User-prepared acceptance files using `FC_API_URL`, `FC_WORKSPACE_ID`, `FC_ACCESS_TOKEN` are separate inputs, not this configuration, and are not copied automatically.

## Permission ceiling and compatibility

FC's `readGrant` supports **all**, **living**, **investment** or **selected** accounts/data items inside exactly one Vault. Dynamic ranges include later supported financial items in that Vault; selected items stay exact. This is financial read authorization, never other Vaults, owner/management data, raw backups or writes. Report items name their whole-Journal/whole-Vault aggregate scope explicitly. A custom account scope is not a date restriction.

FRAG's checked subset must fit the live FC catalog. A broader token does not authorize FRAG to automatically deliver every item. Connection checking fetches health, token-self claims, Workspace metadata and catalog names only; no financial item/report is prefetched. Rechecking, even when it fails, pauses the previous FC source and invalidates pending deliveries before looking at new credentials. Save fresh human authorization to resume. Editing `fc.env` also invalidates the loaded reader until rechecked/restarted. Changing a credential is not a financial-evidence identity.

Only official **reader 1.10.0 / API 3.10.0 / protocol 2**, minimum Host **1.13.4**, is accepted. Archive SHA-256: `99379f5e7cb384eae4d767d861df1a807b8fe83c14a77f9762a58ffebe6caa1c`. Installed three-file digest: `31233f7e5cdfabd9644a93f5562916bb4adf12ef7d289512e76490841939665c`. Exact archive/file bytes are checked before execution and reads; no floating latest. Official `ui.js` is inert integrity-checked compatibility content, not a mounted FRAG page.

Legacy tokens keep their prior capabilities and do not gain the new personal reader routes. New scoped tokens have a distinct prefix rejected by older FC versions, so a downgrade cannot silently ignore their restriction. The new connection check requires a dedicated single-Vault `ledger:read` grant, not a write-capable sandbox token or an owner session. Old env-based selected-report integration remains compatible at its existing explicit boundary, not a new permission grant.

## Read contract and approval scope

`operation: list` discovers human-selected IDs only. Item names come from the FC-authorized catalog, not detail reads. Report labels are derived from the whitelist without fetching every report. `operation: read` accepts one listed Workspace and selected listed IDs. Package, supplier configuration and record revisions are revalidated before finalized delivery; a changed report or whitelist rejects an outstanding pack.

- `monthly-review:YYYY-MM` reads `/api/v3/workspaces/{workspaceId}/reports/monthly-review?month=YYYY-MM`. The concrete anchor must be completed in the Asia/Shanghai calendar; the report includes the anchor and prior two months.
- `month-to-date:YYYY-MM-DD` reads only `/api/v3/workspaces/{workspaceId}/reports/month-to-date?asOf=YYYY-MM-DD`. It covers that month's first day through the exact nonfuture date, inclusive. Its single-period summary is explicitly partial and posted-Journal-only; unrecorded days and external completeness remain unknown. No invented preceding months, whole-month comparisons or balance-derived spending. Posted opening equity entries can move cash without creating income. Living observations, valuations and forecasts are not Journal activity. The full report is required evidence and never replaces economic-stock/obligation prerequisites.
- `economic-evidence:YYYY-MM-DD:YYYY-MM-DD` reads only `/api/v3/workspaces/{workspaceId}/reports/economic-evidence?asOf=...&through=...`. Dates and the 1–366 day horizon are checked before HTTP. A new window requires explicit whitelist authorization. Discovery derives labels without fetching every report.
- Economic summaries preserve gross per-segment/currency cash and debt stocks, actual observation dates, planned outflows, confirmed current-balance repayment dates, out-of-horizon debt amounts/counts and explicit coverage/missing facts. Forecasts are not debt maturities; historical missing dates remain unknown. Future charges, external completeness and personal disposable availability are not assessed. No account IDs/names, agreement text, sources or notes enter the summary. FC alone calculates these values and owns recording/confirmation/storage.
- Only posted ledger entries contribute. Cash is netted per entry/currency to exclude internal cash transfers. Recognized income/expenses use valuation amounts in the entry's balancing currency. Currencies are never implicitly converted or merged.
- Reversals affect their own month and expose signed adjustments already included in totals. Account roles use current Master data, not historical role snapshots. Unassignable posted dates block all totals. Real-world completeness stays unknown, even after reconciliation passes.
- The summary omits account names/IDs, Journal descriptions, references and posting memos. The adapter validates its strict summary shape and does not truncate it. `requiredEvidenceIds` protects the report in backend byte fitting, extension token fitting and completion; insufficient capacity rejects delivery.
- `entry:<approved-id>` and `draft:<approved-id>` remain optional explicit detail selections. Their whitelist is separate authorization to disclose those records; a monthly report does not authorize expansion to them. Legacy bounded record formatting is unchanged.

There is no FC SQLite access, financial recalculation in FRAG, mutation, imported Dashboard, provider credential access, automatic retry, wildcard month, scheduler or autonomous Memory update. FC's own UI authenticates and owns all writes.

- `finance-item:<kind>:<opaque-id>` reads exactly `/reader/items/{itemId}` for a checked account, asset, cash-flow plan, agreement or transfer-observation item. FC authorizes membership inside the read transaction. The safe projection excludes notes, source text and other-side postings; account posting lines are not balanced whole Journal entries. It remains whole required evidence. Selection-only coverage is not complete economic evidence or recommendation permission.

## First real Vault Run

This is a **user-operated factual check**, not authorization for a developer to read real reports or start Slice C. First complete the new connection steps above in the same VS Code project/instance/profile. Confirm the real Vault, exact period and intended native provider before financial data leaves the local evidence boundary.

1. In FRAG's subset, select **Month to date · Journal** and enter the explicitly approved cutoff date, then approve and save. Do not choose a completed-month report for a partial month.
2. In native Chat, enable `frag_fc_read`. Ask: **Use #frag_fc_read with operation "list" only. Do not read financial records.** Verify the intended Workspace and exact report ID.
3. Explicitly ask to read **that one listed report**, with factual cash movement versus income/expense interpretation, separate currencies and coverage limits only. No financial/life action advice or additional reads.
4. `Ctrl+Shift+P` → `FRAG: Open Runs`. Expand the **read** Run → **Full returned text**. Check `completed`, exact cutoff, all currencies and coverage. **Advanced · complete audit JSON** retains `requiredEvidenceIds`. A completed discovery alone is not a successful financial read. Judge the native answer separately.

Stop on a wrong Vault/range, version mismatch, denied permission, stale revision or capacity failure. Do not widen permissions, call owner routes, invent dates/zero values or bypass the official reader. Disable the source and save to stop reads; completed Runs remain immutable. Successful factual review is not automatic Slice C or recommendation approval.

## Verification boundary and rollback

Default development is synthetic, through the public FC HTTP contract, official reader and private FRAG management/tool APIs. Test tokens with write scope belong only to explicitly isolated FC HTTP acceptance, never the reader. Real-token identity/permission checks do not authorize a financial report or Run. Automatic regression, isolated loopback integration, native-window checks, provider behavior and human financial-semantic acceptance remain distinct.

Missing-data refusal alone is not full Slice B acceptance. Whole confirmed-plan plus FC recorded-scope economic evidence still has to pass positively; selection-only item facts cannot replace it. The dedicated production recommendation carrier remains unavailable.

To disable FC, uncheck **Enable this source** and save. For a reviewed downgrade, also clear the FC subset while the current backend owns the state, stop it and use the retained matching Host/VSIX. Do not delete databases, rebind provenance, replay Runs or let an older reader ignore new grant restrictions. No commit, push, release, production install or real-data migration is implied by the build.
