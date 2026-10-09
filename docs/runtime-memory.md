# Reviewed runtime Memory

Memory is human-reviewed background, never current evidence, source permission or a native chat snapshot.

Write a candidate yourself against a completed FRAG evidence Run; scope derives from its actual bindings. The dropdown shows only the latest four eligible Runs. Search an exact Run ID to select older evidence, including records outside the latest-200 overview. Failed/cancelled Runs and discovery-only results cannot support candidates.

Edit/review content, provenance and scope, then explicitly promote with a checkbox and note. **Content version** starts at 1 and increases only when text or scope changes. Promotion, conflict changes and retirement preserve that content version but append an immutable **audit revision**. Saving unchanged text/scope is a no-op and does not demote an active record. Prior text and review history remain intact.

Settings pins at most three active, nonconflicted, applicable exact audit revisions per source. The existing API/database `version` field remains the audit revision for backwards-compatible stale-review and pin validation; `contentVersion` is the content version. Source identity and revisions are checked again at delivery. Stale/inapplicable pins reject delivery until human reconfirmation. General scope requires an explicit human revision choice. No automatic extraction/promotion exists because FRAG cannot observe the native final answer.

Conflict resolution requires both current audit revisions, review and a note. Historical content versions are derived from immutable text/scope history without rewriting stored rows or existing pins. Legacy Memory stays readable and read-only, and is not offered for new pins in Settings; provenance is never rewritten to native identities. Memory appears only when FRAG tools run. Nothing is promoted into shared Mei canonical storage.

Human-triggered FTS5 search can suggest at most three active, nonconflicted records applicable to a selected completed Run. Suggestions never select, promote or include Memory automatically.
