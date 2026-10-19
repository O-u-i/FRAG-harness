"""The backend entrypoint must discover custom options before external paths."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest


@pytest.mark.parametrize("selected", [False, True])
def test_backend_wrapper_preserves_external_archive_options_and_selection(tmp_path, selected):
    shell = shutil.which("pwsh")
    if not shell:
        pytest.skip("PowerShell backend entrypoint is unavailable on this host.")
    root = tmp_path / "synthetic project"
    scripts = root / "scripts"
    tests = root / "backend/tests"
    scripts.mkdir(parents=True)
    tests.mkdir(parents=True)
    source = Path(__file__).resolve().parents[2] / "scripts/test-backend.ps1"
    shutil.copyfile(source, scripts / source.name)
    # Isolate allocator effects too; the outer pytest owns all temporary files.
    (scripts / "maintain-tmp.ps1").write_text(
        "param($NewRun, [switch]$Disposable, $OwnerProcessId, $CloseRun)\n"
        "if ($NewRun) { $env:WRAPPER_TEST_RUN } else {\n"
        "Set-Content -LiteralPath (Join-Path $env:WRAPPER_TEST_RUN 'closed') -Value 'yes' }\n",
        encoding="utf8",
    )
    (root / "backend/pyproject.toml").write_text(
        '[tool.pytest.ini_options]\ntestpaths = ["tests"]\naddopts = "-q"\n', encoding="utf8"
    )
    (tests / "conftest.py").write_text(
        "def pytest_addoption(parser):\n"
        "    parser.addoption('--fc-archive')\n"
        "    parser.addoption('--legacy-host')\n", encoding="utf8"
    )
    outside = tmp_path / "outside artifacts"
    outside.mkdir()
    archives = [outside / "reader.zip", outside / "host.zip"]
    for archive in archives:
        archive.write_bytes(b"synthetic path fixture, not a package")
    (tests / "test_probe.py").write_text(
        "def test_selected(request):\n"
        f"    assert request.config.getoption('--fc-archive') == {str(archives[0])!r}\n"
        f"    assert request.config.getoption('--legacy-host') == {str(archives[1])!r}\n"
        "def test_other():\n    pass\n", encoding="utf8"
    )
    run = root / "run"
    run.mkdir()
    arguments = ["--fc-archive", str(archives[0]), "--legacy-host", str(archives[1]), "-o", "addopts=-q"]
    if selected:
        arguments.append("tests/test_probe.py::test_selected")
    (scripts / "uv.ps1").write_text("""
    $forward = @($args)
    if (($forward[0..4] -join ' ') -ne 'run --offline --no-sync --project .') {
        throw 'The wrapper changed offline/no-sync execution.'
    }
    if ($forward[5] -ne '--cache-dir' -or $forward[7] -ne 'pytest') { throw 'Unexpected uv arguments.' }
    & $env:WRAPPER_TEST_PYTHON -m pytest @($forward[8..($forward.Count - 1)])
    exit $LASTEXITCODE
""", encoding="utf8")
    env = {**os.environ, "WRAPPER_TEST_RUN": str(run), "WRAPPER_TEST_PYTHON": sys.executable,
           "PATH": str(scripts) + os.pathsep + os.environ["PATH"]}
    result = subprocess.run([shell, "-NoProfile", "-File", str(scripts / source.name), *arguments],
                            env=env, cwd=root, capture_output=True, text=True, timeout=60)
    assert (run / "closed").is_file(), result.stdout + result.stderr
    assert result.returncode == 0, result.stdout + result.stderr
    assert ("1 passed" if selected else "2 passed") in result.stdout
