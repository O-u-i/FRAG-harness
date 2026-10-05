# Architecture diagrams

The fixed `harness/` and `rag-lab/` paths each have data-flow and lifecycle diagrams:

| Area | Data flow | Lifecycle |
| --- | --- | --- |
| Harness | [Interactive view](harness/dataflow.html) · [SVG](harness/dataflow.svg) · [Source](harness/dataflow.json) | [Interactive view](harness/lifecycle.html) · [SVG](harness/lifecycle.svg) · [Source](harness/lifecycle.json) |
| RAG Lab | [Interactive view](rag-lab/dataflow.html) · [SVG](rag-lab/dataflow.svg) · [Source](rag-lab/dataflow.json) | [Interactive view](rag-lab/lifecycle.html) · [SVG](rag-lab/lifecycle.svg) · [Source](rag-lab/lifecycle.json) |

| File | Purpose |
| --- | --- |
| `dataflow.json` and `lifecycle.json` | Editable Archify specifications. |
| `dataflow.html` and `lifecycle.html` | Checked, interactive standalone viewers. |
| `dataflow.svg` and `lifecycle.svg` | Canonical, dual-theme exports embedded in the repository README. |

The HTML and SVG files are review artifacts, not application runtime assets. Generate HTML with the project-local Archify skill and export SVG from the HTML viewer. Validate the JSON specifications with Archify showcase quality, then inspect the delivered HTML and exported SVG. Local browser screenshots and visual-check receipts are ignored by Git.

Research has an additional [workflow viewer](research/workflow.html), [SVG](research/workflow.svg), and [editable source](research/workflow.json). The root README also includes a Mermaid recovery flow. These describe implemented host behavior at v1.6.0; live GPT and human semantic acceptance remain pending.

The interactive viewers contain Archify 2.17 code. Distribute them with [ARCHIFY-LICENSE.txt](ARCHIFY-LICENSE.txt), including when sharing a viewer outside this repository. No additional visible UI attribution or FRAG source disclosure is required by that MIT license.
