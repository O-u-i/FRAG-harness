# Local temporary workspace

`.tmp/` is Git ignored and contains local caches, browser review state, and disposable evidence. It is not a single safe-to-delete folder. Keep these areas separate:

| Area | Contents | Cleanup rule |
| --- | --- | --- |
| `.tmp/uv-cache/` | Backend dependency cache used by the documented startup and test commands. | Keep at its current path while FRAG or `uv` may be running. |
| `.tmp/npm-cache/` | Local npm package cache from setup. | Review manually when npm is idle; excluded from automatic cleanup. |
| `.tmp/plugin-uploads/` | Backend staging for plugin management. | Never clean while the backend may be processing an upload. |
| `.tmp/artifacts/` | Reproducible screenshots, Archify browser evidence, and finished pytest runs. | Eligible for the guarded cleanup script. |
| `.tmp/workbench/` | One-off helper scripts, package samples, and handoff drafts. | Review manually; excluded from automatic cleanup. |
| Browser profile directories at the `.tmp/` root | Chrome/Edge, Figma, and Sites review profiles that may retain session state. | Do not move or delete until the owning processes are confirmed stopped and the profile is reviewed. |
| Other `.tmp/` directories | Unreadable test runs, `codex/`, and task-specific scratch work not yet classified. | Excluded from automatic cleanup until classified. |

The current browser process command lines are not readable in this environment, so browser profiles remain in place. Several pytest directories cannot be fully read and remain at the `.tmp/` root. The project keeps `uv-cache` and `plugin-uploads` at their existing paths because application scripts refer to them. The cleanup script never traverses either location. The organizer moves only recognized scratch items and leaves caches, browser profiles, runtime staging, and unclassified directories untouched.

## Organize known scratch items

```powershell
# Preview reversible moves from the .tmp root.
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/organize-tmp.ps1

# Apply the reviewed moves without deleting files.
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/organize-tmp.ps1 -Apply
```

## Guarded cleanup

Run from the repository root:

```powershell
# Preview the next eligible file; no deletion.
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/maintain-tmp.ps1

# Delete at most one eligible file from .tmp/artifacts/.
powershell -NoProfile -ExecutionPolicy Bypass -File ./scripts/maintain-tmp.ps1 -Apply
```

The default policy selects a file from `.tmp/artifacts/` after 14 days. If that area exceeds 300 MiB, a file at least two days old can be selected sooner. The 300 MiB threshold applies only to disposable artifacts; protected caches and browser profiles can keep the whole `.tmp/` tree above it. Each invocation deletes at most one named file. The script does not delete folders, follow reparse points, or touch caches, browser profiles, plugin uploads, or workbench files. No scheduled task is installed; `-Apply` is suitable for an explicitly configured daily schedule after reviewing the preview output.

Manual cleanup uses one named file per command, for example:

```powershell
Remove-Item -LiteralPath '.tmp/artifacts/screenshots/frag-retry.png'
```

Do not use recursive directory deletion or a broad file glob. Before deleting a browser profile or cache, identify the owning process and decide whether its state is still needed.
