"""Règle « Ordre des analyses » et sections RMN 11B / 29Si."""

import pytest

from core.processor import available_rules, build_registry, process_texts
from core.evaluation import evaluate_texts
from core.rules.analysis_order import AnalysisOrderRule
from core.rules.base import ActionKind
from core.rules.nmr_hetero import ElevenBNmrRule, TwentyNineSiNmrRule

ORDER = AnalysisOrderRule()
RULE_B = ElevenBNmrRule()
RULE_SI = TwentyNineSiNmrRule()
NB = "\u00a0"


# --- 11B / 29Si ---------------------------------------------------------------------

def test_11b_section_is_formatted():
    result = RULE_B.apply("11B NMR (128 MHz, CDCl3, 298 K) δ 5.1 (br s), 28.5")
    assert result.new_text == "¹¹B NMR (128 MHz, CDCl₃, 298 K) δ (ppm) = 28.5, 5.1 (br s)"


def test_29si_section_with_decoupling_is_formatted():
    result = RULE_SI.apply("29Si{1H} NMR (79.5 MHz, CDCl3, 298 K) δ -2.0, 7.2 (s)")
    assert result.new_text == "²⁹Si{¹H} NMR (79.5 MHz, CDCl₃, 298 K) δ (ppm) = 7.2 (s), -2.0"


@pytest.mark.parametrize("rule, text", [
    (RULE_B, "¹¹B NMR (128 MHz, CDCl₃, 298 K) δ (ppm) = 28.5, 5.1 (br s)"),
    (RULE_SI, "²⁹Si NMR (79.5 MHz, CDCl₃, 298 K) δ (ppm) = 7.2"),
])
def test_output_is_idempotent_and_recognized(rule, text):
    assert rule.applies(text)
    result = rule.apply(text)
    assert result.new_text == text
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_one_decimal_is_expected_for_b_and_si():
    for rule, label in ((RULE_B, "11B"), (RULE_SI, "29Si")):
        ok = rule.apply(f"{label} NMR (100 MHz, CDCl3, 298 K) δ 28.5")
        bad = rule.apply(f"{label} NMR (100 MHz, CDCl3, 298 K) δ 28.55555")
        assert not [a for a in ok.actions if a.kind == ActionKind.FLAGGED]
        assert [a for a in bad.actions if a.kind == ActionKind.FLAGGED]


def test_missing_temperature_gets_the_marker_and_other_nuclei_are_not_captured():
    result = RULE_B.apply("11B NMR (128 MHz, CDCl3) δ 28.5")
    assert "[??? K]" in result.new_text
    assert not RULE_B.applies("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")
    assert not RULE_SI.applies("11B NMR (128 MHz, CDCl3, 298 K) δ 28.5")


def test_b_section_collated_after_1h():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H) 11B NMR (128 MHz, CDCl3, 298 K) δ 30.1"
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final == (
        f"¹H NMR (400 MHz, CDCl₃, 298 K) δ (ppm) = 7.26 (s, 1{NB}H) "
        "¹¹B NMR (128 MHz, CDCl₃, 298 K) δ (ppm) = 30.1"
    )


def test_rules_are_in_the_catalog():
    names = [r.name for r in available_rules()]
    assert "11B NMR" in names and "29Si NMR" in names


# --- Ordre des analyses ----------------------------------------------------------------

GOOD = ("Rf = 0.30 (SiO2; A/B 1:1). mp 120 °C. 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H). "
        "13C NMR (101 MHz, CDCl3, 298 K) δ 77.0. 19F NMR (376 MHz, CDCl3, 298 K) δ -63.2. "
        "IR (ATR) 1715. HRMS (ESI) m/z: calcd for C10H13O2 165.0910; found 165.0912.")


def test_correct_order_is_not_reported_nor_evaluated():
    assert not ORDER.applies(GOOD)
    items = evaluate_texts([GOOD], build_registry()).items
    assert "Ordre des analyses" not in [i.rule_name for i in items]


@pytest.mark.parametrize("text, expected", [
    ("13C NMR (101 MHz, CDCl3) δ 77.0. 1H NMR (400 MHz, CDCl3) δ 7.26 (s, 1H).", "1H NMR après 13C NMR"),
    ("HRMS (ESI) calcd for C1 1; found 1. IR (ATR) 1715.", "IR après HRMS"),
    ("IR (ATR) 1715. mp 120 °C", "m.p. / b.p. après IR"),
    ("19F NMR (376 MHz) δ -63.2. 13C NMR (101 MHz) δ 77.0.", "13C NMR après 19F NMR"),
    ("1H NMR (400 MHz) δ 7.26. Rf = 0.30 (SiO2; A/B 1:1)", "Rf après 1H NMR"),
])
def test_wrong_order_is_flagged_and_text_untouched(text, expected):
    assert ORDER.applies(text)
    result = ORDER.apply(text)
    assert result.new_text == text
    messages = [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]
    assert len(messages) == 1 and expected in messages[0]
    assert messages[0].split(" : ")[0] == "Ordre des analyses non conforme"


def test_prose_mentions_are_ignored():
    assert not ORDER.applies("Les spectres IR et la RMN 1H sont décrits ci-dessous.")
    assert not ORDER.applies("Le Rf et le mp sont donnés.")


def test_single_analysis_never_applies():
    assert not ORDER.applies("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")


def test_flag_is_reported_by_the_full_chain():
    text = "13C NMR (101 MHz, CDCl3, 298 K) δ 77.0. 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)."
    actions = process_texts([text], build_registry()).paragraphs[0].actions
    assert any(a.rule_name == "Ordre des analyses" and a.kind == ActionKind.FLAGGED for a in actions)


def test_rule_is_in_the_catalog():
    assert "Ordre des analyses" in [r.name for r in available_rules()]
