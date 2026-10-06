# Integrated manual acceptance

Phase 8 engineering is delivered at v1.9.0 with synthetic providers and sources. Real GPT, selected KB, live FC and human semantic acceptance are human-owned follow-up work. Offline checks do not pass these gates. Keep v2.0.0 pending until actual receipts and the final versioned regression are complete.

## Prepare one local acceptance workspace

Keep captures, copied notes, Gold expectations, screenshots and acceptance records under ignored `.local-plan-b/phase-8/manual/` or `.tmp/`. Product Runs and reviewed memory stay in their normal ignored runtime database; the development ledger is separate. Do not stage these artifacts or credentials. Existing test directories need no cleanup.

Start the regular frontend/backend with `npm run dev`. Fake providers are suitable for an initial local smoke. For an intentional real-model run, configure provider, exact model and endpoint in backend-only `backend/.env`; inspect readiness and the complete destination/request preview. A test shell that disables dotenv should not be reused as the normal model runtime without restoring intentional configuration. Never copy keys or authorization headers into a report.

The caller reviews every Research, Context and Inference preview separately. A Research run may need up to three model turns followed by the two formal stages. The model may choose fewer turns; record its actual trajectory. Check current provider pricing and available budget before the approved calls. Host token/time/tool limits bound requests but do not establish the provider's bill.

## Synthetic GPT case

1. Put a small human-reviewed synthetic Markdown file in ignored `local-sources/acceptance/`. Include a date, units, a numerical ceiling, a negation and an explicit unknown. Keep one unrelated section unselected.
2. In **RAG Lab**, select **Selected local file**, choose exactly that file and the intended locators, and click **Build index**. The isolated `selected-local-v1` cache must become ready. Search for the known terms and inspect retrieved chunks, allowed parent expansion and revision. The bundled synthetic index is a separate mode.
3. Preview the fixed Context request once to verify the selected evidence and source bindings. Cancellation must send no model request. Prepare Research in **Runs** with the same explicit RAG source request. Research's tools operate on the retrieved selected evidence snapshot; the first FTS search and later `kb.search` are different retrieval steps.
4. Inspect and approve each Research turn. Observe at least one real native search and one `kb.read` CLI tool result before an accepted finish when evaluating the complete tool trajectory. Confirm call IDs, serial execution, bounded output and absence of unselected material. An early finish without the required observed tools is an incomplete trajectory for this case.
5. Inspect and separately approve Context and Inference. Check that the displayed PreparedCall is the request that was dispatched and that each approval is single-use. Save the Run ID and exported JSON/Markdown reports.
6. Compare the answer, Context compression and claim citations against the synthetic original. Review the date, units, ceiling, negation and unknown explicitly. A valid schema or citation ID alone does not pass this review. Record accept, reject or pause in **Runs**, preserving the original model output.

The Research source envelope uses the actual selected locator IDs, not the illustrative placeholders below:

```json
{
  "kind": "rag",
  "sourceRequest": {
    "datasetId": "selected-local-v1",
    "sourceSelection": {
      "relativePath": "acceptance/selected-note.md",
      "locatorIds": ["<selected-locator-id>"],
      "relevanceReason": "Explicitly selected for this acceptance case."
    },
    "query": "<review goal and searchable terms>",
    "topK": 3
  }
}
```

The `{kind, sourceRequest}` envelope above is for the HTTP Research API. In Runs, choose **Selected RAG query** and paste only the inner `sourceRequest` object into the Research source-selection textarea. Opening a saved fixed RAG Run prefills its saved selection input. Copy the actual selection from the RAG preview/request rather than guessing a locator or broadening the source scope.

## Selected KB case

Use `kb-read-route` in module-test mode and `kb-fortest` to select allowed metadata candidates. Exclude `00 Inbox`, `50 Personal`, `100 Innovation`, `90 System`, `Templates`, hidden configuration and unverified links/junctions/hardlinks. Root README, folder indexes and workflow documentation are navigation, not knowledge facts. This selection step is read-only; it does not register a product source or authorize model egress.

The current development handoff contains a metadata-only candidate list under `.local-plan-b/phase-8/`; no candidate body was used by the offline tests. Choose one eligible Markdown note yourself. Copy only that file into ignored `local-sources/acceptance/selected-note.md`, record its original vault-relative path and SHA-256, and verify the copy's bytes match. Do not copy or index the whole vault. If the original changes, record the new revision and start a fresh selected-source run.

Use the same RAG Lab selection/build/search/Research/Context/Inference sequence as above. Select only the necessary locators. Confirm that an unselected section and another local file cannot appear in the index, parent expansion, tools or outbound requests. Test both relevant English and Chinese terms when the selected source supports them; record zero-hit cases rather than substituting another unselected source.

Before dispatch, inspect all evidence actually included in each preview, including the source assessment's authority, freshness, relevance, provenance and read-only permission. Keep unknown values explicit; a user-provided selection reason and matching hash do not establish authority or freshness. After dispatch, review the original source beside compressed facts and every cited claim. Record missing qualifiers, contradictions, limits and uncertain provenance. Scope/hash consistency proves identity, not authority, truth or complete support.

For memory, form a candidate from a saved result or human revision. Edit and review it, promote an applicable version, then recommend and explicitly confirm it for a new run with the same current scope. Verify that it appears as background rather than current evidence or a citation. A changed file/root/locator scope, conflict, retirement or changed memory version must not silently reuse an old confirmation. Keep historical candidates and original outputs visible.

For recovery, stop the backend only at a reliably saved checkpoint and restart it with the same configured source/runtime/cache. View the saved Run and prepare a new recovery preview. The old token must fail; recovery uses a new approval. A changed source or unknown external outcome must not resend the old request automatically. The offline suite covers the unsafe-outcome cases without incurring real-model charges.

## Live Finance Core case

Use the FC-owned plugin archive and compatible versions from [the FC handoff](finance-core-plugin-handoff.md). Verify its SHA-256 against the producer artifact. Configure the backend-only read token and explicit Workspace/record allowlist, then restart FRAG and select the intended scope/records. Do not use an old frontend with the version 2 catalog.

Inspect the Released record in FC and the bounded read-only FRAG evidence side by side. Confirm Workspace isolation, record IDs, revision and FC-provided decimal/unit strings. FRAG performs no financial calculation or mutation and does not open FC SQLite. Journal actions open FC's standalone UI. This case needs its own live read and human semantic receipt; an offline adapter test is separate evidence.

## Score a saved report

Export the actual Run JSON from **Runs**. Write versioned captured Gold expectations from the original reviewed source, not from the model answer. Bind the exact goal and complete source bindings. A nonempty, distinct `expectedEvidenceIds` list is required; `runId` is optional. Keep the Gold and result files ignored.

The capture scorer performs no model call and does not regenerate artifacts:

```powershell
$env:PYTHONPATH = 'backend'
backend/.venv/Scripts/python.exe -m frag_api.evaluation --gold .local-plan-b/phase-8/manual/captured-gold.json --capture .local-plan-b/phase-8/manual/run-report.json --format json
```

See [offline evaluation](offline-evaluation.md) for the exact captured Gold schema and Markdown output option. Literal facts, required missing-information and structural checks can report PASS or FAIL. Incomplete outputs remain NOT_RUN; scorer errors remain ERROR. Capture consistency does not prove an approval was legitimate or a source is currently fresh. Human semantic support remains separately UNDETERMINED until actually reviewed.

## Record acceptance and release readiness

For each actual case, retain its Run ID, timestamp, app/provider/plugin versions, original selected-source path/hash and locators, relevant request/trajectory/result exports, deterministic checks and the human decisions. Record the observed status as `PASS`, `FAIL`, `ERROR`, `NOT_RUN` or `UNDETERMINED`, with concrete defects or missing evidence. Redact secrets and unrelated personal material before sharing a receipt.

Required follow-up evidence is:

| Gate | Needed receipt |
| --- | --- |
| Real synthetic GPT | Actual bounded Research/tool results and separately approved Context/Inference calls. |
| Selected KB | Eligible explicit source, parsing/index/retrieval/loop/stages, memory and report, plus original-source provenance. |
| Live FC | Compatible pinned producer artifact and actual Released selected read with Workspace/record isolation. |
| Human semantics | Reviewed facts, negations, dates, units, constraints, unknowns and per-claim citation support. |
| Final release candidate | Full relevant regression/privacy/plugin/browser checks after repairs; synchronized v2.0.0 artifacts only after the other gates pass. |

Accepting an offline engineering handoff, creating a Git commit or promoting a memory does not substitute for these receipts. Failed or incomplete cases stay visible. After the human provides the actual outcomes, repair within Phase 8, verify again where needed, and only then prepare the final v2.0.0 delivery. Commit and push remain manual.
