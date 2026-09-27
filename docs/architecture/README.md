# Architecture diagrams

The `harness/` and `rag-lab/` folders each contain two diagrams:

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
