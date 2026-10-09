# Architecture artifacts

One current [native evidence workflow](native-tools/workflow.html), [editable JSON](native-tools/workflow.json), and [README SVG](native-tools/workflow.svg) replaces the old two-stage, Research, standalone GUI and AHP diagrams.

Native Local Agent chooses tools. FRAG validates scope, redacts/budgets evidence, revalidates source/Memory revisions and records only tool output. Model inference/research/checkpoints belong to the native host; no final-answer observation is implied.

Use project-local Archify showcase validation/delivery, then preserve light-only output with `scripts/light-architecture.mjs`. Export SVG from the actual viewer, not an HTML substring. `npm run check:diagrams` binds README Mermaid topology and artifacts. Delivery, final light-only digest, browser containment and perceptual review are separate evidence layers; temporary captures stay ignored.

The viewer contains Archify 2.17 code. Distribute [ARCHIFY-LICENSE.txt](ARCHIFY-LICENSE.txt) with it; the previously approved notice remains intact. Archify is development documentation tooling, not runtime.
