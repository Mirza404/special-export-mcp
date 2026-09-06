"""Tier 2/3/4 acceptance criteria, run against real committed fixtures.

See docs/specs/007-testing.md section 2. Assertions are structural
(counts, specific carried-down values), not full byte-exact dicts, so a
harmless article edit after a refetch does not produce a wall of red.
"""

from __future__ import annotations

import re
from pathlib import Path

import defusedxml.ElementTree as ET

from special_export_mcp.wikitext.inline import clean_cell
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


# Rows whose Power cell is not expected to yield a kW figure, and why. Both
# reasons are genuine facts about this real, unmodified article -- not
# parser defects. See docs/specs/002-table-parsing.md section 2.5 and the
# session note on the "1.8 T" (AUQ/AWP) row below.
_KNOWN_NON_POWER_ROWS = {
    # A doubled |- with a pending rowspan produces a row that carries only
    # the spanned Displ. value; there is no power data in that row at all.
    ("", "", "", "", "1781 cc", "", ""),
    # `|colspan="7"|` with empty content: a genuine blank spacer row.
    ("", "", "", "", "", "", ""),
}


def test_golf_mk4_every_power_cell_yields_a_kw_figure() -> None:
    # Acceptance criteria 9 and 12 in docs/specs/003-inline-and-templates.md:
    # a (\d+)\s*kW regex matches every power cell, whether authored in kW
    # or in PS. One row in this real article is a known exception: its
    # rowspan="3" on Displ. covers only 3 of the 4 rows that actually share
    # that displacement (the article's own inconsistency, confirmed by
    # reading the raw wikitext -- a real browser renders the same
    # column-shifted row from the same HTML rowspan arithmetic). That
    # shifts Power's value into the Torque column and Torque's into
    # nothing, for the "1.8 T" (AUQ/AWP, 2001-2006) row specifically.
    wikitext = _wikitext_from_export_xml(FIXTURES / "volkswagen_golf_mk4.xml")
    tables = parse_tables(wikitext)
    engine_table = tables[0]
    power_idx = engine_table.headers.index("Power")

    misses = []
    for row in engine_table.rows:
        if tuple(row) in _KNOWN_NON_POWER_ROWS:
            continue
        if "AUQ/AWP" in row[3]:  # the known column-shifted row, see above
            continue
        cleaned, _ = clean_cell(row[power_idx])
        if not re.search(r"(\d+)\s*kW", cleaned):
            misses.append(row)

    assert misses == []
