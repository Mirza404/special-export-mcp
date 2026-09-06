"""Tier 3 tests: template argument parsing and the convert/cvt handler."""

from __future__ import annotations

from special_export_mcp.wikitext.templates import TemplateWarning, resolve_templates


def _resolve(text: str, *, strict: bool = False) -> tuple[str, list[TemplateWarning]]:
    warnings: list[TemplateWarning] = []
    result = resolve_templates(text, strict=strict, warnings=warnings)
    return result, warnings


def test_convert_kw_ps_hp_precision_abbr() -> None:
    result, warnings = _resolve("{{convert|55|kW|PS hp|0|abbr=on}}")
    assert result == "55 kW"
    assert warnings == []


def test_convert_nm_lbft_no_precision() -> None:
    result, warnings = _resolve("{{convert|128|Nm|lb.ft|abbr=on}}")
    assert result == "128 Nm"


def test_convert_nm_zero_precision_no_output_units() -> None:
    result, _ = _resolve("{{convert|170|Nm|0|abbr=on}}")
    assert result == "170 Nm"


def test_cvt_nm_lbft_precision() -> None:
    result, _ = _resolve("{{cvt|148|Nm|lbft|0}}")
    assert result == "148 Nm"


def test_cvt_kw_ps_hp_no_precision() -> None:
    result, _ = _resolve("{{cvt|81|kW|PS hp|0}}")
    assert result == "81 kW"


def test_cvt_order_out_does_not_change_the_authored_value() -> None:
    # order=out only changes which unit Wikipedia's own rendering shows
    # first; it never changes what the author wrote (spec 003 section
    # 3.3, Q2). Cross-checked against Wikipedia's own rendering of this
    # exact template call: "85 kW (115 PS; 113 hp)".
    result, _ = _resolve("{{cvt|115|PS|kW PS hp|0|order=out}}")
    assert result == "115 PS (85 kW)"


def test_convert_hp_to_kw() -> None:
    result, _ = _resolve("{{convert|150|hp|kW}}")
    assert result == "150 hp (112 kW)"


def test_convert_lbft_to_nm() -> None:
    result, _ = _resolve("{{convert|200|lbft|Nm}}")
    assert result == "200 lbft (271 Nm)"


def test_convert_litres_to_cc() -> None:
    result, _ = _resolve("{{convert|2.0|L|cc}}")
    assert result == "2.0 L (2000 cc)"


def test_convert_range_with_unconvertible_unit() -> None:
    result, _ = _resolve("{{convert|1950|4700|rpm}}")
    assert result == "1950–4700 rpm"


def test_convert_range_with_convertible_unit() -> None:
    result, _ = _resolve("{{convert|100|120|hp|kW}}")
    assert result == "100–120 hp (75–89 kW)"


def test_convert_already_canonical_unit_is_not_duplicated() -> None:
    result, _ = _resolve("{{convert|100|kg}}")
    # kg has no canonical mapping at all -- emitted alone either way.
    assert result == "100 kg"


def test_convert_non_numeric_value_is_an_unknown_template_warning() -> None:
    result, warnings = _resolve("{{convert|abc|kW}}")
    assert result == ""
    assert len(warnings) == 1
    warning = warnings[0]
    assert warning.kind == "unknown_template"
    assert warning.name == "convert"
    assert warning.raw == "{{convert|abc|kW}}"
    assert warning.reason == "argument 1 is not numeric"


def test_convert_missing_unit_is_an_unknown_template_warning() -> None:
    result, warnings = _resolve("{{convert|55}}")
    assert result == ""
    assert warnings[0].reason == "missing input unit"


def test_unrecognized_template_produces_a_warning_and_empty_text() -> None:
    result, warnings = _resolve("{{some_unknown_template|x|y}}")
    assert result == ""
    assert warnings[0].kind == "unknown_template"
    assert warnings[0].name == "some unknown template"


def test_strict_mode_raises_instead_of_warning() -> None:
    from special_export_mcp.errors import TemplateResolutionError

    warnings: list[TemplateWarning] = []
    try:
        resolve_templates("{{convert|abc|kW}}", strict=True, warnings=warnings)
        raise AssertionError("expected TemplateResolutionError")
    except TemplateResolutionError as exc:
        assert exc.message == "argument 1 is not numeric"
    assert warnings == []


def test_warning_carries_table_position_context() -> None:
    warnings: list[TemplateWarning] = []
    resolve_templates(
        "{{convert|abc|kW}}",
        strict=False,
        warnings=warnings,
        table_index=0,
        row=4,
        column=5,
    )
    warning = warnings[0]
    assert warning.table_index == 0
    assert warning.row == 4
    assert warning.column == 5
    assert warning.to_dict() == {
        "kind": "unknown_template",
        "name": "convert",
        "raw": "{{convert|abc|kW}}",
        "reason": "argument 1 is not numeric",
        "table_index": 0,
        "row": 4,
        "column": 5,
    }


def test_nested_templates_resolve_innermost_first() -> None:
    result, warnings = _resolve("{{nowrap|{{convert|55|kW}}}}")
    assert result == "55 kW"
    assert warnings == []


def test_nowrap() -> None:
    result, _ = _resolve("{{nowrap|do not break this}}")
    assert result == "do not break this"


def test_nbsp_and_spaces() -> None:
    assert _resolve("a{{nbsp}}b")[0] == "a b"
    assert _resolve("a{{spaces}}b")[0] == "a b"


def test_dashes() -> None:
    assert _resolve("{{ndash}}")[0] == "–"
    assert _resolve("{{endash}}")[0] == "–"
    assert _resolve("{{--}}")[0] == "–"
    assert _resolve("{{mdash}}")[0] == "—"


def test_sfrac_and_frac() -> None:
    assert _resolve("{{sfrac|1|2}}")[0] == "1/2"
    assert _resolve("{{frac|3|4}}")[0] == "3/4"


def test_val_with_unit() -> None:
    assert _resolve("{{val|100|u=kg}}")[0] == "100 kg"


def test_val_without_unit() -> None:
    assert _resolve("{{val|100}}")[0] == "100"


def test_small_big_nobold_passthrough() -> None:
    assert _resolve("{{small|x}}")[0] == "x"
    assert _resolve("{{big|x}}")[0] == "x"
    assert _resolve("{{nobold|x}}")[0] == "x"


def test_sortname() -> None:
    assert _resolve("{{sortname|John|Smith}}")[0] == "John Smith"


def test_sort_keeps_display_value_only() -> None:
    assert _resolve("{{sort|zzz|Actual Name}}")[0] == "Actual Name"


def test_ubl_and_plainlist() -> None:
    assert _resolve("{{ubl|a|b|c}}")[0] == "a, b, c"
    assert _resolve("{{plainlist|x|y}}")[0] == "x, y"


def test_dropped_templates_produce_no_warning() -> None:
    for name in ("clear", "clarify", "citation needed", "cn", "efn", "refn"):
        result, warnings = _resolve(f"{{{{{name}}}}}")
        assert result == ""
        assert warnings == []


def test_lang() -> None:
    assert _resolve("{{lang|fr|Bonjour}}")[0] == "Bonjour"
