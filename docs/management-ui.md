# Management UI

FRAG 1.14.0 keeps management in the native VS Code Webview: **Settings**,
**Runs** and **Memory**. Open **FRAG: Open Settings** from the Command Palette.
The native Local Agent still owns chat and model requests; FRAG returns only
explicitly authorized evidence.

## Appearance and navigation

Use the header's theme button for a dark/light switch, or **Appearance and
preferences** for these presentation-only options:

| Option | Choices |
| --- | --- |
| Theme | Follow system, Dracula dark, Living light |
| Density | Compact or Comfortable |
| Interface motion | Enable or disable transitions; system reduced-motion also applies |
| Visible Runs | 25, 50, 100 or 200 of the latest returned Runs |
| Show developer JSON | Show the raw last local-operation result |

Preferences persist locally through VS Code. Reset appearance restores the
defaults; it does not reset sources, Runs or Memory. Living light uses the FC
Living palette; Dracula dark adapts the OSS palette for readable UI text.
Neither theme changes financial meaning or safety policy.

The magnifier expands Search; Escape closes it and clears the query. Runs can
be filtered by status, Run ID, tool or source. Finance Core offers item-type
filters, **Selected only**, grouped items and collapsible connection steps.
Filtering never selects, deselects or authorizes an item. Review the selection
count and report dates before saving. Reports cover their named aggregate
scope, not merely checked accounts.

Sources, exclusions, confirmed plans and reviewed Memory still require explicit
authorization. Editing that configuration resets its approval checkbox. Index
build/refresh remains a separate manual action. Errors, authorization
disclosures and important evidence limitations remain visible; longer guidance
and advanced detail can be expanded when needed.

## A/B acceptance workspace

Open **FRAG: Open Acceptance Workspace**, or expand **A/B acceptance** in
Settings. This is a guide and synthetic-file helper, not a test runner or a
pass/fail certificate. It neither enables recommendations nor filters native
chat.

The panel displays the exact local paths before anything is created:

| Setting | Workspace location |
| --- | --- |
| Default | `<project-private-state>/acceptance/` |
| Custom `frag.acceptanceRoot` | `<acceptance-container>/projects/<project-hash>/acceptance/` |

**Prepare virtual files** explicitly creates `README.md` and
`sources/synthetic-plan.md`. Existing plan edits are preserved; unrelated or
unsafe paths are refused. **Choose location…** selects a machine-local
container separate from the project, Host and private state. Changing it never
moves or deletes old files. Keep real plans, finance data and credentials out.

### Slice B: complete-plan checks

1. Prepare the virtual files, then use **Open folder** or **Open virtual plan**
   to inspect them.
2. Choose **Use this test source**. Review the exact `sources` directory, save
   its authorization and explicitly **Build / Refresh index**. Preparing the
   folder alone does none of these.
3. Copy the panel's **Native Chat prompt** into the native Local Agent. Before
   confirmation, `frag_read` with `requireCompletePlan=true` must refuse. Do not
   bypass refusal with filesystem tools or an excerpt read.
4. Review the entire virtual file. In its completed Search Run, choose
   **Confirm entire document as a plan**. Search again and repeat the complete
   read.
5. In Runs, inspect **Full returned text** and **Advanced · complete audit
   JSON**: the entire plan, `role: confirmed_plan`, `windowed: false`, matching
   `planRevision` and its server-required evidence ID must be retained. Markers
   alone do not establish completeness.
6. Edit only the virtual plan and refresh the index without reconfirming. The
   complete read must refuse. Review and confirm the new revision, then repeat.
   **Clear confirmed plans**, followed by saving authorization, revokes
   complete-plan access without deleting files or completed Runs.

This plan exercise is not all of Slice B. Full B acceptance also needs an
explicitly authorized official FC economic report, a positive synthetic case
with all required evidence, and refusal when critical financial facts are
missing. Single account items or monthly flows alone do not establish complete
cash stocks, debt/obligation timing or affordability. Required evidence and
selected Memory must remain whole or delivery must refuse. Test capacity and
Memory-overflow cases in isolated synthetic checks, not by altering real data.

### Slice A: safety foundation

Select **A · Safety foundation** for the review checklist. Review isolated
synthetic test results with the developer and inspect **Runs → Synthetic
safety receipts** separately from evidence ToolRuns. An empty receipt list is
normal; there is no production advice launch button.

Verify draft isolation, missing/stale evidence refusal, unknown checks,
cancellation, timeout, persistence failure, exact checked-byte return, shared
reservations and bounded remediation. Interrupted work must not resend.
Synthetic budget arithmetic is not a provider billing guarantee. Checked does
not mean correct, adopted or executed.

Preparing files or passing these checks does not record human acceptance,
complete Slice C or enable a production recommendation gate. Native loading,
provider behavior, factual review and human acceptance remain separate. See
[manual acceptance](manual-acceptance.md), [complete plans](confirmed-plan-evidence.md)
and [recommendation safety](recommendation-safety.md).

## Folders and ownership

Expand **Folders & storage** in Settings to see this project's locations, open
private state or open native Settings.

| Location | Owner and purpose |
| --- | --- |
| Authorized source folder | User-selected evidence; independently approved and indexed |
| Project-private state | Backend-owned approvals, indexes, Runs, Memory and backend-only `fc.env` |
| Acceptance workspace | User-edited synthetic manual-check files, outside the repository |
| Host installation | Matching packaged backend and Webview; not a source or editable data folder |
| Repository `src/management/` | Developer-owned UI implementation |
| Repository `integrations/vscode/bridge/` | Developer-owned native commands and local helpers |
| Repository `.tmp/` | Governed development runs and regenerable output, not production state |
| Repository `packages/v<version>/` | Matching versioned Host/VSIX delivery artifacts, not private user data |

Private state defaults to VS Code extension storage under
`projects/<project-hash>/`. To customize it, set `frag.privateStateRoot` to a
private absolute local container; FRAG appends the same project suffix.
`frag.hostInstallation` selects the matching Host. Stop the backend and reload
after changing state or Host locations. No migration, merging or deletion is
automatic; choosing an empty state root starts new approvals/history.

Do not move user customization into source code, copied runtime bundles or
developer scratch folders. Keep state, `fc.env` and private acceptance material
out of Git and shared/cloud-synced locations. FC Vaults remain FC-owned, and
model credentials remain in native VS Code.
