"""Line-level classification of wikitable syntax.

See docs/specs/002-table-parsing.md sections 1 and 2.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum, auto


class LineKind(Enum):
    TABLE_OPEN = auto()
    TABLE_CLOSE = auto()
    ROW_SEP = auto()
    CAPTION = auto()
    HEADER_CELL = auto()
    DATA_CELL = auto()
    OTHER = auto()


@dataclass
class ClassifiedLine:
    kind: LineKind
    payload: str


def classify_line(line: str) -> ClassifiedLine:
    stripped = line.strip()
    if stripped.startswith("{|"):
        return ClassifiedLine(LineKind.TABLE_OPEN, stripped[2:].strip())
    if stripped.startswith("|}"):
        return ClassifiedLine(LineKind.TABLE_CLOSE, stripped[2:].strip())
    if stripped.startswith("|-"):
        return ClassifiedLine(LineKind.ROW_SEP, stripped[2:].strip())
    if stripped.startswith("|+"):
        return ClassifiedLine(LineKind.CAPTION, stripped[2:].strip())
    if stripped.startswith("!"):
        return ClassifiedLine(LineKind.HEADER_CELL, stripped[1:])
    if stripped.startswith("|"):
        return ClassifiedLine(LineKind.DATA_CELL, stripped[1:])
    return ClassifiedLine(LineKind.OTHER, line)


def split_cells(payload: str, separator: str) -> list[str]:
    """Split one header/data line's payload into raw cell strings."""
    return payload.split(separator)


def find_unnested_pipe(text: str) -> int | None:
    """Index of the first '|' outside [[...]], {{...}}, <...>, and quotes."""
    bracket_depth = 0
    brace_depth = 0
    in_angle = False
    quote: str | None = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        two = text[i : i + 2]
        if quote is not None:
            if ch == quote:
                quote = None
            i += 1
            continue
        if ch in ('"', "'"):
            quote = ch
            i += 1
            continue
        if two == "[[":
            bracket_depth += 1
            i += 2
            continue
        if two == "]]":
            bracket_depth = max(0, bracket_depth - 1)
            i += 2
            continue
        if two == "{{":
            brace_depth += 1
            i += 2
            continue
        if two == "}}":
            brace_depth = max(0, brace_depth - 1)
            i += 2
            continue
        if ch == "<":
            in_angle = True
            i += 1
            continue
        if ch == ">":
            in_angle = False
            i += 1
            continue
        if ch == "|" and bracket_depth == 0 and brace_depth == 0 and not in_angle:
            return i
        i += 1
    return None


_ATTR_RE = re.compile(
    r"^\s*[A-Za-z-]+\s*=\s*(\"[^\"]*\"|'[^']*'|\S+)"
    r"(\s+[A-Za-z-]+\s*=\s*(\"[^\"]*\"|'[^']*'|\S+))*\s*$"
)


@dataclass
class SplitCell:
    attrs: str | None
    content: str


def split_attrs_content(raw_cell: str) -> SplitCell:
    """Split one raw cell into its attribute list and content, per spec 2.1."""
    pipe_index = find_unnested_pipe(raw_cell)
    if pipe_index is None:
        return SplitCell(None, raw_cell.strip())
    prefix = raw_cell[:pipe_index]
    if _ATTR_RE.match(prefix):
        return SplitCell(prefix.strip(), raw_cell[pipe_index + 1 :].strip())
    return SplitCell(None, raw_cell.strip())


_ROWSPAN_RE = re.compile(r"rowspan\s*=\s*(\"(\d+)\"|'(\d+)'|(\d+))", re.IGNORECASE)
_COLSPAN_RE = re.compile(r"colspan\s*=\s*(\"(\d+)\"|'(\d+)'|(\d+))", re.IGNORECASE)


def _extract_span(attrs: str | None, pattern: re.Pattern[str]) -> int:
    if not attrs:
        return 1
    match = pattern.search(attrs)
    if not match:
        return 1
    value = next(g for g in match.groups()[1:] if g is not None)
    try:
        n = int(value)
    except ValueError:
        return 1
    return n if n > 0 else 1


def extract_rowspan(attrs: str | None) -> int:
    return _extract_span(attrs, _ROWSPAN_RE)


def extract_colspan(attrs: str | None) -> int:
    return _extract_span(attrs, _COLSPAN_RE)


_CLASS_RE = re.compile(r"class\s*=\s*(\"([^\"]*)\"|'([^']*)'|(\S+))", re.IGNORECASE)


def extract_class_tokens(attrs: str) -> set[str]:
    match = _CLASS_RE.search(attrs)
    if not match:
        return set()
    value = next(g for g in match.groups()[1:] if g is not None)
    return set(value.split())
