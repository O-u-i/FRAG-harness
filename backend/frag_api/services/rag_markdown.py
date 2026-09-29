"""RAG-only Markdown hierarchy and small-child segmentation."""
from __future__ import annotations

import re
from dataclasses import dataclass

CHILD_SIZE = 500
CHILD_OVERLAP = 80
HEADING = re.compile(r"^(#{1,6})[ \t]+(.+?)[ \t]*#*[ \t]*$")
FENCE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})")


@dataclass(frozen=True)
class MarkdownSection:
    parent_id: str
    locator_id: str
    label: str
    title_path: str
    text: str


@dataclass(frozen=True)
class MarkdownChild:
    parent: MarkdownSection
    ordinal: int
    text: str


def sections_from_markdown(source: str) -> list[MarkdownSection]:
    lines = source.lstrip("\ufeff").splitlines(keepends=True)
    if lines and lines[0].strip() == "---":
        closing = next((i for i, line in enumerate(lines[1:], 1) if line.strip() in {"---", "..."}), None)
        if closing is not None:
            lines = lines[closing + 1:]
    result: list[MarkdownSection] = []
    titles: dict[int, str] = {}
    block: list[str] = []
    label = "Document preamble"
    title_path = label
    fence_char = ""
    fence_length = 0

    def flush() -> None:
        value = "".join(block).strip()
        if value:
            number = len(result) + 1
            result.append(MarkdownSection(
                parent_id=f"parent-{number:03d}", locator_id=f"section-{number}",
                label=label, title_path=title_path, text=value,
            ))

    for line in lines:
        fence = FENCE.match(line)
        if fence:
            marker = fence.group(1)
            if not fence_char:
                fence_char, fence_length = marker[0], len(marker)
            elif marker[0] == fence_char and len(marker) >= fence_length:
                fence_char, fence_length = "", 0
            block.append(line)
            continue
        match = HEADING.match(line.rstrip("\r\n")) if not fence_char else None
        if match:
            flush()
            block = [line]
            level = len(match.group(1))
            titles = {depth: value for depth, value in titles.items() if depth < level}
            label = match.group(2).strip()
            titles[level] = label
            title_path = " > ".join(titles[depth] for depth in sorted(titles))
        else:
            block.append(line)
    flush()
    return result


def _split_units(text: str, limit: int, level: int = 0) -> list[str]:
    """Recursively prefer paragraphs, lines, sentences, then characters."""
    if len(text) <= limit:
        return [text] if text else []
    separators = (r"\n\s*\n", r"\n", r"(?<=[.!?。！？])(?=\s|[^\s])")
    if level < len(separators):
        parts = re.split(f"({separators[level]})", text)
        units = ["".join(parts[i:i + 2]) for i in range(0, len(parts), 2)]
        return [piece for unit in units for piece in _split_units(unit, limit, level + 1)]
    return [text[i:i + limit] for i in range(0, len(text), limit)]


def children_for(section: MarkdownSection, *, size: int = CHILD_SIZE, overlap: int = CHILD_OVERLAP) -> list[MarkdownChild]:
    if size <= overlap or overlap < 0:
        raise ValueError("Child size must exceed nonnegative overlap.")
    header = f"Title path: {section.title_path}\n"
    capacity = size - len(header)
    if capacity <= overlap:
        raise ValueError("Title path exceeds child size.")
    units = _split_units(section.text, capacity)
    bodies: list[str] = []
    current = ""
    for unit in units:
        if current and len(current) + len(unit) > capacity:
            bodies.append(current)
            current = current[-overlap:] if overlap else ""
        current += unit
        if len(current) > capacity:
            # A carryover can make the next unit exceed capacity; cut at the limit.
            while len(current) > capacity:
                bodies.append(current[:capacity])
                current = current[capacity - overlap:]
    if current:
        bodies.append(current)
    return [MarkdownChild(section, i, header + body) for i, body in enumerate(bodies, 1)]
