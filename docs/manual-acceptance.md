# Acceptance boundaries · 1.11.0

Local checks cover synthetic multi-file indexing, stale-source/config rejection, transactional persistence, human Memory review/version/scope enforcement, read-only legacy history and a private authenticated loopback API.

A real isolated VS Code 1.141.0 main-window Local Agent consumed `frag_search`, then `frag_read`, then produced a final answer through an offline provider: three model requests, two finalized tool Runs, no paid model/private source. Optional official FC compatibility uses mocked synthetic HTTP, not live records.

Scoped live verification also exercised a native Responses-compatible model with explicit source authorization. Ordinary chat and Search → Read → final-response continuation worked in that tested configuration; credentials stayed in native settings, source files were unchanged, and FRAG did not own a model bridge or runtime loop. Private provider/source details and execution receipts stay outside Git. See [native continuation troubleshooting](../integrations/vscode/README.md#responses-endpoints-without-reliable-server-side-continuation).

Human/live acceptance remains separate:

1. Install matching packages in your normal main-window VS Code instance; retain working native models.
2. Authorize/build a nonsecret test directory, enable tools, and ask the real model to search/read.
3. Inspect exact packs/source links/omissions in Runs and judge the final answer yourself.
4. Promote/pin Memory, revise it and confirm stale pins require reconfirmation.
5. Separately opt into live FC read-only whitelist acceptance if needed.

Offline checks do not prove provider reliability, real KB semantics, final citation support/completeness, native checkpoints or human UX approval. The scoped live result proves the tested continuation path, not long-term provider reliability or human semantic acceptance; live FC and Memory lifecycle acceptance remain separate. Old Plan B phases are not deemed complete. No commit/push/tag/public release/production installation is implied.
