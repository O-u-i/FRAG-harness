import hashlib
from pathlib import Path

import pytest

from frag_api.services.context_source_service import ContextSourceError, ContextSourceService


def test_hash_and_extraction_use_one_byte_snapshot_even_if_path_changes(source_root, monkeypatch):
    path = source_root / "evidence.md"
    original = path.read_bytes()
    service = ContextSourceService(source_root)
    parser = service._parse_md
    def changed_path_parser(data):
        path.write_text("# Changed\nUnapproved new bytes.", encoding="utf-8")
        return parser(data)
    monkeypatch.setattr(service, "_parse_md", changed_path_parser)
    result = service.parse("evidence.md")
    assert result.source.sha256 == hashlib.sha256(original).hexdigest()
    assert "synthetic finding" in result.sections[0].text
    assert "Unapproved" not in result.sections[0].text
    assert hashlib.sha256(path.read_bytes()).hexdigest() != result.source.sha256


def test_markdown_preamble_and_fenced_heading_keep_selectable_provenance(source_root):
    text = "---\ntitle: Synthetic\n---\nPreamble fact.\n# Finding\n```text\n# Example only\n```\nReal limitation.\n## Detail\nQualified fact."
    (source_root / "evidence.md").write_text(text, encoding="utf-8")
    result = ContextSourceService(source_root).parse("evidence.md")
    assert len(result.sections) == 3
    assert result.sections[0].text == "Preamble fact."
    assert "# Example only" in result.sections[1].text and "Real limitation" in result.sections[1].text
    assert result.sections[2].locator.label == "Finding > Detail"


@pytest.mark.parametrize("path", ["../outside.txt", "C:\\outside.txt", "\\outside.txt", "/outside.txt", "evidence.md:stream", "missing.md"])
def test_snapshot_paths_reject_escape_and_alternate_stream(source_root, path):
    with pytest.raises((ContextSourceError, OSError)):
        ContextSourceService(source_root).read_snapshot(path)


def test_snapshot_formats_parse_memory_streams(source_root):
    from docx import Document
    from openpyxl import Workbook
    for name, text in {"plain.txt": "Synthetic fact.", "rows.csv": "label,value\nsynthetic,1",
                       "page.html": "<p>Synthetic fact.</p><script>password=hidden</script>"}.items():
        (source_root / name).write_text(text, encoding="utf-8")
    document = Document()
    document.add_paragraph("Synthetic document fact.")
    document.save(source_root / "document.docx")
    workbook = Workbook()
    workbook.active.append(["Synthetic", 1])
    workbook.save(source_root / "workbook.xlsx")
    workbook.close()
    service = ContextSourceService(source_root)
    for name in ("plain.txt", "rows.csv", "page.html", "document.docx", "workbook.xlsx"):
        result = service.parse(name)
        assert result.source.sha256 == hashlib.sha256((source_root / name).read_bytes()).hexdigest()
        assert result.sections
    assert "password=" not in service.parse("page.html").sections[0].text


def test_source_root_identity_cannot_be_reused_for_another_root(source_root, tmp_path):
    from frag_api.schemas.harness import HarnessRequest
    from frag_api.services.harness_service import HarnessService
    other = tmp_path / "other"
    other.mkdir()
    (other / "evidence.md").write_bytes((source_root / "evidence.md").read_bytes())
    body = HarnessRequest(goal="Explain the finding", fileSelections=[{"relativePath": "evidence.md",
                          "locatorIds": ["section-1"], "relevanceReason": "Selected for review"}])
    first = HarnessService(ContextSourceService(source_root)).preview(body)
    second = HarnessService(ContextSourceService(other)).preview(body)
    assert first.source_bindings[0].revision == second.source_bindings[0].revision
    assert first.context_fingerprint != second.context_fingerprint
