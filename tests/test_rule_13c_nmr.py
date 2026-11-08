"""Tests de la règle 13C NMR au format stylisé (FEAT-002)."""

from core.rules.base import ActionKind
from core.rules.nmr_13c import ThirteenCNmrRule

RULE = ThirteenCNmrRule()


def _seg_text(result) -> str:
    return "".join(s.text for s in result.segments)


def test_applies_to_13c_nmr_and_rmn():
    assert RULE.applies("13C NMR (101 MHz, CDCl3, 298 K) δ 1.0") is True
    assert RULE.applies("13C RMN (101 MHz, CDCl3, 298 K) δ 1.0") is True
    assert RULE.applies("  13C NMR (101 MHz, CDCl3, 298 K)") is True


def test_does_not_apply_to_1h():
    assert RULE.applies("1H NMR (400 MHz, CDCl3, 298 K)") is False


def test_styled_output_has_bold_label_and_italic_delta():
    result = RULE.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 166.4 (C=O), 21.7 (CH3)")
    assert result.is_styled is True
    assert [s.text for s in result.segments if s.bold] == ["¹³C NMR"]
    assert any(s.italic and s.text == "δ" for s in result.segments)


def test_label_keeps_input_word_nmr():
    result = RULE.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 166.4 (C=O)")
    assert result.new_text.startswith("¹³C NMR")


def test_label_keeps_input_word_rmn():
    result = RULE.apply("13C RMN (101 MHz, CDCl3, 298 K) δ 166.4 (C=O)")
    assert result.new_text.startswith("¹³C RMN")


def test_attribution_in_parentheses_and_subscripts():
    result = RULE.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 60.8 (CH2), 21.7 (CH3)")
    body = _seg_text(result)
    assert "(CH₂)" in body
    assert "(CH₃)" in body


def test_signals_sorted_descending():
    result = RULE.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 21.7 (CH3), 166.4 (C=O), 60.8 (CH2)")
    body = _seg_text(result)
    assert body.index("166.4") < body.index("60.8") < body.index("21.7")


def test_coupling_constant_is_kept():
    result = RULE.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 120.5 (q, J = 32.0 Hz)")
    assert "J = 32.0 Hz" in result.new_text


def test_unparsable_signal_flags_and_keeps_order():
    result = RULE.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 21.7 (CH3), bizarre, 166.4 (C=O)")
    assert any(a.kind == ActionKind.FLAGGED for a in result.actions)
    body = _seg_text(result)
    assert body.index("21.7") < body.index("bizarre") < body.index("166.4")


def test_only_13c_segment_reformatted_in_multisection_paragraph():
    text = (
        "13C NMR (100.63MHz, DMF-d7, 298) δ 149.4 (2C), 143.4 (2C) "
        "19F{1H} NMR (376.55 MHz, DMF-d7, 298 K) δ -20.9 (3F)"
    )
    result = RULE.apply(text)
    assert result.new_text.startswith("¹³C NMR (100.63 MHz")
    # Le segment 19F reste intact.
    assert "19F{1H} NMR (376.55 MHz, DMF-d7, 298 K) δ -20.9 (3F)" in result.new_text
    assert "19F" not in result.replaced_text
