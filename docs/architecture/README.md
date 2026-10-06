# Architecture diagrams

The fixed `harness/` and `rag-lab/` paths each have data-flow and lifecycle diagrams:

| Area | Data flow | Lifecycle |
| --- | --- | --- |
| Harness | [Interactive view](harness/dataflow.html) · [SVG](harness/dataflow.svg) · [Source](harness/dataflow.json) | [Interactive view](harness/lifecycle.html) · [SVG](harness/lifecycle.svg) · [Source](harness/lifecycle.json) |
| RAG Lab | [Interactive view](rag-lab/dataflow.html) · [SVG](rag-lab/dataflow.svg) · [Source](rag-lab/dataflow.json) | [Interactive view](rag-lab/lifecycle.html) · [SVG](rag-lab/lifecycle.svg) · [Source](rag-lab/lifecycle.json) |

| File | Purpose |
| --- | --- |
| `dataflow.json`, `lifecycle.json` and `workflow.json` | Editable Archify specifications. |
| `dataflow.html`, `lifecycle.html` and `workflow.html` | Checked, light-only interactive standalone viewers. |
| `dataflow.svg`, `lifecycle.svg` and `workflow.svg` | Light-only exports embedded in the repository README. |

The HTML and SVG files are review artifacts, not application runtime assets. Generate HTML with the project-local Archify skill, then apply `node scripts/light-architecture.mjs` to preserve the repository's light-only output policy. The script leaves the skill package and authored graph specifications unchanged. Validate the JSON specifications with Archify showcase quality, then check and inspect the final light-only HTML and SVG. Record the original delivery digest and final light-only artifact digest separately. Local browser screenshots and receipts are ignored by Git.

New diagram previews, screenshots and exports must remain light-only. Archify 2.17's stock `visual-check` generates dark screenshots, so use a scoped light-only browser check for this repository and record that coverage explicitly. Do not generate dark variants for acceptance or keep existing dark image files.

Research has an additional [workflow viewer](research/workflow.html), [SVG](research/workflow.svg), and [editable source](research/workflow.json). Reviewed memory has a [workflow viewer](memory/workflow.html), [SVG](memory/workflow.svg), and [editable source](memory/workflow.json), covering human promotion, scoped recommendations, confirmation and request-version checks. Read-only plugins have a [workflow viewer](plugins/workflow.html), [SVG](plugins/workflow.svg), and [editable source](plugins/workflow.json), covering independent activation, the shared KB/FC evidence contract and approved stages. RAG Lab now covers either the bundled synthetic index or an explicitly selected file/locator scope with an isolated cache. The root README also includes Mermaid recovery, memory lifecycle, plugin and integrated acceptance flows. These describe implemented host behavior at v1.9.0; real GPT, selected KB, live FC and human semantic acceptance remain pending.

The interactive viewers contain Archify 2.17 code. Distribute them with [ARCHIFY-LICENSE.txt](ARCHIFY-LICENSE.txt), including when sharing a viewer outside this repository. No additional visible UI attribution or FRAG source disclosure is required by that MIT license.
