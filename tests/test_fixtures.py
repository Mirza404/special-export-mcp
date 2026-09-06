"""Tier 2/3/4 acceptance criteria, run against real committed fixtures.

See docs/specs/007-testing.md section 2. Assertions are structural
(counts, specific carried-down values), not full byte-exact dicts, so a
harmless article edit after a refetch does not produce a wall of red.
"""

from __future__ import annotations

from pathlib import Path

import defusedxml.ElementTree as ET

from special_export_mcp.wikitext.tables import parse_tables

FIXTURES = Path(__file__).parent / "fixtures"


def _wikitext_from_export_xml(path: Path) -> str:
    root = ET.parse(path).getroot()
    assert root is not None
    for page in root:
        for child in page:
            if child.tag.rsplit("}", 1)[-1] != "revision":
                continue
            for rev_child in child:
                if rev_child.tag.rsplit("}", 1)[-1] == "text":
                    assert rev_child.text is not None
                    return rev_child.text
    raise AssertionError(f"no revision text found in {path}")


def test_golf_mk4_has_exactly_two_tables() -> None:
    wikitext = _wikitext_from_export_xml(FIXTURES / "volkswagen_golf_mk4.xml")
    tables = parse_tables(wikitext)
    assert len(tables) == 2


def test_golf_mk4_engine_table_headers() -> None:
    wikitext = _wikitext_from_export_xml(FIXTURES / "volkswagen_golf_mk4.xml")
    tables = parse_tables(wikitext)
    assert tables[0].headers == ["Model", "Year", "Engine", "Code", "Displ.", "Power", "Torque"]


def test_golf_mk4_every_row_has_seven_cells() -> None:
    wikitext = _wikitext_from_export_xml(FIXTURES / "volkswagen_golf_mk4.xml")
    tables = parse_tables(wikitext)
    for row in tables[0].rows:
        assert len(row) == 7


def test_golf_mk4_rowspan_carries_1595cc_down() -> None:
    wikitext = _wikitext_from_export_xml(FIXTURES / "volkswagen_golf_mk4.xml")
    tables = parse_tables(wikitext)
    matches = [row for row in tables[0].rows if "AVU/BFQ" in row[3]]
    assert len(matches) == 1
    assert matches[0][4] == "1595 cc"


def test_golf_mk4_rowspan_with_spaces_around_equals_carries_1598cc() -> None:
    wikitext = _wikitext_from_export_xml(FIXTURES / "volkswagen_golf_mk4.xml")
    tables = parse_tables(wikitext)
    matches = [row for row in tables[0].rows if "Gasoline direct injection" in row[0]]
    assert len(matches) == 1
    assert matches[0][4] == "1598 cc"


def test_golf_mk4_no_row_has_zero_cells() -> None:
    wikitext = _wikitext_from_export_xml(FIXTURES / "volkswagen_golf_mk4.xml")
    tables = parse_tables(wikitext)
    for table in tables:
        for row in table.rows:
            assert len(row) > 0
