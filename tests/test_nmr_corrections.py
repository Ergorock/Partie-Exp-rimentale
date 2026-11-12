"""Corrections des règles RMN : attributions, signe moins, label à tiret,
indices après parenthèse, découplage {1H}, noyaux 19F / 31P, J en italique et
table des multiplicités étendue."""

from core import config as cfg
from core.config import RmnConfig
from core.processor import available_rules, build_registry, process_texts
from core.rules import nmr_common
from core.rules.base import ActionKind
from core.rules.nmr_13c import ThirteenCNmrRule
from core.rules.nmr_1h import OneHNmrRule

RULE_1H = OneHNmrRule()
RULE_13C = ThirteenCNmrRule()
HEAD = "1H NMR (400 MHz, CDCl3, 298 K) δ "


def _flagged(result) -> bool:
    return any(a.kind == ActionKind.FLAGGED for a in result.actions)


def _final(text: str) -> str:
    return process_texts([text], build_registry()).paragraphs[0].new_text


def _rule(name):
    return next(r for r in available_rules() if r.name == name)


# --- Attributions : numéros de position jamais mis en indice ------------------

def test_position_number_in_attribution_is_not_subscripted():
    result = RULE_1H.apply(HEAD + "7.26 (d, J = 8.0 Hz, 1H, H4)")
    assert result.new_text.endswith("(d, J = 8.0 Hz, 1\xa0H; H4)")


def test_primed_position_and_carbon_numbering_are_kept():
    result = RULE_13C.apply("13C NMR (100 MHz, CDCl3, 298 K) δ 128.0 (C3), 120.1 (C4')")
    assert result.new_text.endswith("δ (ppm) = 128.0 (C3), 120.1 (C4')")


def test_formula_group_in_attribution_is_still_subscripted():
    result = RULE_1H.apply(HEAD + "3.80 (s, 3H, OCH3)")
    assert result.new_text.endswith("(s, 3\xa0H; OCH₃)")


def test_attribution_formula_after_parenthesis():
    assert nmr_common.subscript_attribution("N(CH3)2") == "N(CH₃)₂"


# --- Indices après une parenthèse fermante ------------------------------------

def test_subscript_after_closing_parenthesis():
    assert nmr_common.subscript_formula("(CD3)2SO") == "(CD₃)₂SO"


def test_solvent_with_parenthesis_group():
    result = RULE_1H.apply("1H NMR (400 MHz, (CD3)2SO, 298 K) δ 7.26 (s, 1H)")
    assert "(CD₃)₂SO" in result.new_text


# --- Signe moins Unicode / tiret demi-cadratin --------------------------------

def test_unicode_minus_shift_is_parsed_and_kept():
    signals, ok = nmr_common.parse_signals("−20.9 (s, 3F), −29.3 (s, 6F)")
    assert ok
    assert signals[0].shift == "−20.9"
    assert signals[0].shift_high == -20.9


def test_en_dash_minus_shift_is_parsed():
    signals, ok = nmr_common.parse_signals("–1.5 (s, 1H)")
    assert ok
    assert signals[0].shift_high == -1.5


def test_negative_shifts_are_sorted():
    result = RULE_1H.apply(HEAD + "−1.5 (s, 1H), 0.5 (s, 1H)")
    assert result.new_text.endswith("δ (ppm) = 0.5 (s, 1\xa0H), −1.5 (s, 1\xa0H)")


# --- Label écrit avec un tiret -------------------------------------------------

def test_hyphenated_label_is_recognized_and_normalized():
    result = RULE_1H.apply("1H-NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")
    assert result.new_text.startswith("¹H NMR (400 MHz, CDCl₃, 298 K)")


def test_hyphenated_sections_are_split():
    text = "1H-NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H) 13C-NMR (100 MHz, CDCl3, 298 K) δ 77.0"
    final = _final(text)
    assert final == (
        "¹H NMR (400 MHz, CDCl₃, 298 K) δ (ppm) = 7.26 (s, 1\xa0H) "
        "¹³C NMR (100 MHz, CDCl₃, 298 K) δ (ppm) = 77.0"
    )


# --- Découplage {1H} et noyaux hétéroatomiques --------------------------------

def test_13c_decoupled_label_is_recognized():
    result = RULE_13C.apply("13C{1H} NMR (100 MHz, CDCl3, 298 K) δ 77.0, 128.0")
    assert result.new_text == "¹³C{¹H} NMR (100 MHz, CDCl₃, 298 K) δ (ppm) = 128.0, 77.0"


def test_19f_rule_is_available_and_formats():
    rule = _rule("19F NMR")
    result = rule.apply("19F{1H} NMR (376 MHz, CDCl3, 298 K) δ -63.2 (s, 3F), -20.9 (s, 3F)")
    assert result.new_text == "¹⁹F{¹H} NMR (376 MHz, CDCl₃, 298 K) δ (ppm) = -20.9 (s, 3\xa0F), -63.2 (s, 3\xa0F)"


def test_31p_rule_is_available_and_formats():
    rule = _rule("31P NMR")
    result = rule.apply("31P{1H} NMR (162 MHz, CDCl3, 298 K) δ 25.1, 30.2 (d, J = 12.0 Hz)")
    assert result.new_text == (
        "³¹P{¹H} NMR (162 MHz, CDCl₃, 298 K) δ (ppm) = 30.2 (d, J = 12.0 Hz), 25.1"
    )


def test_1h_rule_ignores_decoupling_brace_of_19f():
    assert not RULE_1H.applies("19F{1H} NMR (376 MHz, CDCl3, 298 K) δ -63.2 (s, 3F)")


def test_demo_paragraph_19f_section_is_processed():
    text = (
        "13C NMR (100 MHz, CDCl3, 298 K) δ 77.0 "
        "19F{1H} NMR (376.55 MHz, DMF-d7, 298 K): ẟ (ppm) = -20.9 (3F), -29.3 (6F)"
    )
    final = _final(text)
    assert final.endswith("¹⁹F{¹H} NMR (376.55 MHz, DMF-d₇, 298 K) δ (ppm) = -20.9 (3\xa0F), -29.3 (6\xa0F)")


# --- J en italique --------------------------------------------------------------

def test_j_is_italic_by_default():
    result = RULE_1H.apply(HEAD + "7.26 (dd, J = 8.4 Hz, J = 2.1 Hz, 1H)")
    italic = [s.text for s in result.segments if s.italic]
    assert italic == ["δ", "J", "J"]
    assert "".join(s.text for s in result.segments) in result.new_text


def test_j_italic_can_be_disabled():
    cfg.set_config(RmnConfig(italic_j=False))
    result = RULE_1H.apply(HEAD + "7.26 (d, J = 8.4 Hz, 1H)")
    assert [s.text for s in result.segments if s.italic] == ["δ"]


def test_j_italic_config_roundtrip():
    data = cfg.config_to_dict(RmnConfig(italic_j=False))
    assert data["italic_j"] is False
    assert cfg.config_from_dict(data).italic_j is False
    assert cfg.config_from_dict({"italic_j": "oui"}).italic_j is True


# --- Table des multiplicités étendue -------------------------------------------

def test_common_composite_multiplicities_are_recognized():
    body = (
        "7.40 (td, J = 7.5, 1.2 Hz, 1H), 7.30 (dt, J = 8.0, 1.5 Hz, 1H), "
        "7.20 (ddd, J = 8.0, 7.5, 1.2 Hz, 1H), 4.10 (qd, J = 7.1, 2.0 Hz, 2H), "
        "2.50 (sept, J = 6.9 Hz, 1H), 1.60 (sext, J = 7.4 Hz, 2H), 1.20 (br d, 1H)"
    )
    result = RULE_1H.apply(HEAD + body)
    assert not _flagged(result)
    assert result.new_text.endswith("δ (ppm) = " + body.replace("H)", "\xa0H)"))


def test_br_variants_are_normalized():
    result = RULE_1H.apply(HEAD + "5.0 (br. s, 1H), 4.0 (bd, 1H)")
    assert result.new_text.endswith("δ (ppm) = 5.0 (br s, 1\xa0H), 4.0 (br d, 1\xa0H)")
