# Optional Pi worker third-party notices

This backend worker contains a selected, unmodified set of 29 published JavaScript
files from `@earendil-works/pi-ai@1.0.0`, pinned to official source commit
`a13d35a742c6ef8462812a28fbe1d8c8b7431c32`. It is not the complete Pi npm package.
The exact selection, original file hashes, archive integrity and dependency pins
are recorded in `../vendor/pi-ai/selection-manifest.json`.

The included third-party runtime packages are exactly `openai@7.19.0` and
`partial-json@0.1.7`. Optional peers and other Pi providers are excluded from this
package. Original licenses are preserved verbatim:

| Component | License | Original document |
| --- | --- | --- |
| Selected Pi files; copyright Mario Zechner | MIT | `../vendor/pi-ai/LICENSE` |
| OpenAI SDK; copyright OpenAI | Apache-2.0 | `openai/LICENSE` |
| OpenAI's embedded partial-json-parser; copyright Promplate Dev Team | MIT | `openai/src/_vendor/partial-json-parser/LICENSE` |
| OpenAI's embedded zod-to-json-schema; copyright Stefan Terdell | ISC | `openai/src/_vendor/zod-to-json-schema/LICENSE` |
| OpenAI's embedded internal/qs; copyright Nathan LaFreniere and contributors | BSD-3-Clause | `openai/src/internal/qs/LICENSE.md` |
| partial-json; copyright Promplate Dev Team | MIT | `partial-json/LICENSE` |

Keep these original documents with distributed copies of the covered backend
files and dependencies. The licenses themselves state the applicable copyright,
permission, redistribution, disclaimer and non-endorsement conditions. No
third-party `NOTICE` file was present in the reviewed exact archives.

This file summarizes provenance and document locations; it does not replace any
original license, claim endorsement, authorize another dependency/version or
establish operational provider acceptance. The worker and its dependencies are
backend-only and are not part of frontend assets.
