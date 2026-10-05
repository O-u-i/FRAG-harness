from collections.abc import Iterator
from pathlib import Path
import os

# Apply before importing the application: tests must never load a local API key
# or inherit production provider settings. Individual tests opt into mocks.
os.environ["PYTHON_DOTENV_DISABLED"] = "1"
for name in tuple(os.environ):
    if name.startswith(("OPENAI_", "FINANCE_CORE_", "FRAG_CONTEXT_LLM_", "FRAG_INFERENCE_LLM_", "FRAG_RESEARCH_LLM_", "FRAG_LLM_", "FRAG_RUNTIME_")):
        os.environ.pop(name)

import pytest
from fastapi.testclient import TestClient

from frag_api.main import create_app


@pytest.fixture(autouse=True)
def isolated_runtime(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("FRAG_RUNTIME_PATH", str(tmp_path / "runtime.sqlite3"))


@pytest.fixture
def source_root(tmp_path: Path) -> Path:
    root = tmp_path / "sources"
    root.mkdir()
    (root / "evidence.md").write_text("# Finding\nA synthetic finding is supported.\n# Limits\nEvidence is incomplete.", encoding="utf-8")
    return root


@pytest.fixture
def client(tmp_path: Path, source_root: Path) -> Iterator[TestClient]:
    app = create_app(context_source_root=source_root, rag_index_path=tmp_path / "rag.sqlite3", plugin_root=tmp_path / "plugins")
    with TestClient(app, raise_server_exceptions=False) as value:
        yield value
