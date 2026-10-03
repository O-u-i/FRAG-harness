"""Deterministic Markdown view of the same record returned to the page and JSON."""
import json
import re
from frag_api.schemas.runtime import RunReport


def report_markdown(report: RunReport) -> str:
    payload = json.dumps(report.model_dump(by_alias=True), ensure_ascii=False, indent=2)
    # User/model text is quoted as data and cannot terminate the code fence.
    fence = "`" * max(3, 1 + max((len(m.group()) for m in re.finditer(r"`+", payload)), default=0))
    return (f"# Run {report.run.id}\n\n"
            f"Status: {report.run.status}\n\n"
            f"Structural validation: {report.structural_validation}\n\n"
            f"Human semantic review: {report.semantic_review}\n\n"
            "The canonical record below is shared with the page and JSON export.\n\n"
            f"{fence}json\n{payload}\n{fence}\n")
