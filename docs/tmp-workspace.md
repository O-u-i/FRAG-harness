# Local temporary workspace

`.tmp/` holds local development outputs, not production state. Check it before creating temporary files and at handoff. Every task uses one directory; all its fixtures, logs, profiles and build experiments stay inside it.

Versioned delivery packages and their checksum receipt live in the repository's `packages/v<version>/`, not disposable `.tmp/`. Keep private state and acceptance evidence out of that delivery folder.

## Locations and names

| Location | Permitted writes | Naming |
| --- | --- | --- |
| `.tmp/runs/` | Synthetic tests/evaluations, owned browser review profiles, build experiments and temporary helpers | `YYYYMMDD-HHmm+0800-purpose-NN`, Asia/Shanghai time to the minute; increment NN on a collision |
| `.tmp/evidence/` | Verified archives, screenshots and redacted acceptance receipts retained after a task | The same timestamped task format; retain original paths/hashes inside archives |
| `.tmp/packages/` | Ignored package staging and retained legacy artifacts; not the default delivery output | Versioned package filenames; receipt records artifact time |
| `.tmp/agents-dist/` | The standard Review build used by packaging | Fixed tooling path; regenerated build, not retained evidence |
| `.tmp/uv-cache/`, `.tmp/npm-cache/` | Dependency caches | Fixed tooling paths; clean only when their owners are stopped and the cache is verified disposable |
| `.tmp/plugin-uploads/` | Active backend plugin staging | Fixed service path; never delete an in-flight upload |
| `.tmp/artifacts/` | Two inaccessible legacy pytest directories | Read-only exception; no new files |

Do not create loose files or new arbitrary directories at `.tmp`'s root. Nested fixture names need not repeat the task timestamp. Credentials, copied real KB/finance sources, canonical memory and production databases do not belong in disposable runs. A synthetic test database is allowed only within its test run. Private acceptance evidence belongs in the ignored development ledger or a verified evidence archive.

## Create and close a task

```powershell
$fragTask = pwsh -NoProfile -File ./scripts/maintain-tmp.ps1 -NewRun backend-tests -Disposable
# Example: .tmp/runs/20261008-2110+0800-backend-tests-01
# All task files go beneath $fragTask.
.\backend\.venv\Scripts\python.exe -X utf8 -m pytest backend/tests -o addopts= -p no:cacheprovider --basetemp "$fragTask/pytest"
pwsh -NoProfile -File ./scripts/maintain-tmp.ps1 -CloseRun $fragTask
```

`run.json` records an ISO timestamp with timezone, purpose, owner process and lifecycle. `-Disposable` explicitly declares that contents can be regenerated and contain no unique evidence. Omit it for a browser profile or unarchived review material. `closed` only means work has ended; it is not a successful-test or human-acceptance claim. Pass `-OwnerProcessId` when creating a run for another process. Closing a run is an explicit action.

`npm run test:python` and bridge tests use this allocator automatically. Backend tests use the previously installed locked environment without dependency synchronization, disable pytest's repository cache and use a run-local base directory. Bridge tests keep per-case fixtures inside two named suite directories. The normal packaging build and dependency caches use the fixed exceptions above. Run `pwsh -NoProfile -File scripts/maintain-tmp.test.ps1` to verify allocation, expiry, protected-state and path/capacity guards with synthetic fixtures.

## Capacity and cleanup

The previous rule covered only `.tmp/artifacts/`: **300 MiB**, **14 days**, and files at least **2 days** old under capacity pressure. It did not cap the whole temporary tree. The current policy retains those age/pressure values for disposable runs and adds a **2 GiB ceiling for all of `.tmp`**, including caches, builds, packages and evidence. A scan that cannot read a directory reports a lower bound, not an exact total.

```powershell
# Read-only inventory, naming/capacity warnings and eligible runs.
pwsh -NoProfile -File ./scripts/maintain-tmp.ps1

# Batch-delete all qualifying runs under the maintainer's standing authorization.
pwsh -NoProfile -File ./scripts/maintain-tmp.ps1 -Apply
```

Cleanup requires a valid manifest, `disposable: true`, `closed` status, a stopped owner and age of at least 14 days, or at least 2 days when disposable runs exceed 300 MiB. It rejects links and paths outside the temporary root. Each file is inspected again before deletion; only empty directories are removed afterward. Active, unclassified, inaccessible and unique material is retained. Current matching Host/VSIX packages and evidence archives are protected. The maintainer authorized verified, justified batch deletion without another question; neither age nor capacity alone proves a file disposable.

When approaching 2 GiB, remove verified superseded builds, stopped disposable caches or completed synthetic fixtures whose useful evidence has been retained. The script does not infer those facts for caches, profiles or unclassified folders. If protected state prevents staying below the ceiling, report the limitation and stop additional temporary writes. No scheduled cleanup or administrator elevation is installed.

The 2026-10-08 consolidation retained current packages, archived 2,757 verification files and reclaimed approximately 3.54 GB. Two legacy directories (`artifacts/test-runs/pytest-frag` and `pytest-frag-fc`) remain unreadable under the current Windows token; failures are recorded separately from successful deletion.
