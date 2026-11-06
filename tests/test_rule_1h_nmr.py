"""Tests de la règle 1H NMR au format stylisé (FEAT-002).

L'ancien format texte-brut '1H NMR (...)' a été remplacé par la sortie
stylisée cible : label ¹H exposant Unicode (mot NMR/RMN conservé) + parenthèse
en gras, δ en italique, signaux triés du plus grand au plus petit avec règle de
sûreté. Ces tests vérifient l'intention (correction/signalement) sur le nouveau
format.
"""

from core.rules.base import ActionKind, StyledSegment
from core.rules.nmr_1h import OneHNmrRule

RULE = OneHNmrRule()


def _seg_text(result) -> str:
    return "".join(s.text for s in result.segments)


def test_applies_to_1h_nmr_paragraphs():
    assert RULE.applies("1H NMR (400 MHz, CDCl3, 298 K) δ ...") is True
    assert RULE.applies("  1H NMR (400 MHz, CDCl3, 298 K)") is True


def test_does_not_apply_to_other_paragraphs():
    assert RULE.applies("13C NMR (100 MHz, CDCl3, 298 K)") is False
    assert RULE.applies("A random experimental paragraph") is False


def test_styled_output_has_bold_label_and_italic_delta():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.98 (d, J = 8.2 Hz, 2H)"
    result = RULE.apply(text)
    assert result.is_styled is True
    # Un segment en gras (label + parenthèse) et un segment δ en italique.
    bold = [s for s in result.segments if s.bold]
    italic = [s for s in result.segments if s.italic]
    assert bold and "NMR" in bold[0].text
    assert italic and italic[0].text == "δ"


def test_label_keeps_input_word_nmr_with_superscript():
    result = RULE.apply("1H NMR (400 MHz, CDCl3, 298 K) δ 1.0 (s, 3H)")
    assert result.new_text.startswith("¹H NMR")


def test_label_keeps_input_word_rmn_with_superscript():
    result = RULE.apply("1H RMN (400 MHz, CDCl3, 298 K) δ 1.0 (s, 3H)")
    assert result.new_text.startswith("¹H RMN")


def test_solvent_gets_unicode_subscripts():
    result = RULE.apply("1H NMR (400 MHz, CDCl3, 298 K) δ 1.0 (s, 3H)")
    assert "CDCl₃" in result.new_text


def test_signals_sorted_descending_when_all_parsable():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 2.34 (s, 3H), 7.98 (d, 2H), 4.31 (q, 2H)"
    result = RULE.apply(text)
    body = _seg_text(result)
    assert body.index("7.98") < body.index("4.31") < body.index("2.34")


def test_unparsable_signal_flags_and_keeps_order():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 2.3 (s, 3H), bizarre, 7.5 (m, 1H)"
    result = RULE.apply(text)
    assert any(a.kind == ActionKind.FLAGGED for a in result.actions)
    body = _seg_text(result)
    # Pas de réordonnancement : l'ordre d'entrée est conservé.
    assert body.index("2.3") < body.index("bizarre") < body.index("7.5")


def test_missing_space_before_mhz_is_corrected():
    text = "1H NMR (400.18MHz, DMF-d7, 298 K) δ 9.18 (s, 1H)"
    result = RULE.apply(text)
    assert "400.18 MHz" in result.new_text
    assert any(a.kind == ActionKind.CORRECTED for a in result.actions)


def test_temperature_number_only_gets_kelvin_unit():
    text = "1H NMR (400 MHz, CDCl3, 298) δ 1.0 (s, 3H)"
    result = RULE.apply(text)
    assert "298 K" in result.new_text
    assert any(a.kind == ActionKind.CORRECTED for a in result.actions)


def test_missing_temperature_inserts_placeholder():
    text = "1H NMR (400 MHz, CDCl3) δ 1.0 (s, 3H)"
    result = RULE.apply(text)
    assert "[??? K]" in result.new_text
    assert any(a.kind == ActionKind.PLACEHOLDER for a in result.actions)


def test_multiplicity_bs_is_normalized_to_br_s():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 8.35 (bs, 2H)"
    result = RULE.apply(text)
    assert "br s" in result.new_text


def test_frequency_outside_parenthesis_is_moved_inside():
    text = "1H NMR 400 MHz (CDCl3, 298 K) δ 1.0 (s, 3H)"
    result = RULE.apply(text)
    assert "400 MHz" in result.new_text
    assert result.new_text.index("400 MHz") < result.new_text.index("CDCl₃")
    assert any(a.kind == ActionKind.CORRECTED for a in result.actions)


def test_no_parenthesis_is_flagged():
    text = "1H NMR 400 MHz CDCl3 298 K δ = 1.0"
    result = RULE.apply(text)
    assert any(
        a.kind in (ActionKind.FLAGGED, ActionKind.PLACEHOLDER) for a in result.actions
    )


def test_only_1h_segment_reformatted_in_multisection_paragraph():
    # 1H + 13C + 19F collés : seul le segment 1H est reformaté.
    text = (
        "1H NMR (400.18MHz, DMF-d7, 298) δ 9.18 (dd, J = 4.7 Hz, 2H) "
        "13C NMR (100.63 MHz, DMF-d7, 298 K) δ 149.4 (2C) "
        "19F{1H} NMR (376.55 MHz, DMF-d7, 298 K) δ -20.9 (3F)"
    )
    result = RULE.apply(text)
    # Le segment 1H est reformaté...
    assert result.new_text.startswith("¹H NMR (400.18 MHz")
    # ...mais les segments 13C et 19F restent intacts (non reformatés).
    assert "13C NMR (100.63 MHz, DMF-d7, 298 K) δ 149.4 (2C)" in result.new_text
    assert "19F{1H} NMR (376.55 MHz, DMF-d7, 298 K) δ -20.9 (3F)" in result.new_text
    # replaced_text ne couvre que le segment 1H.
    assert result.replaced_text.strip().startswith("1H NMR")
    assert "13C" not in result.replaced_text


def test_separator_space_preserved_before_next_section():
    # Régression cosmétique : un espace doit séparer la fin du segment 1H
    # reformaté du label de la section suivante (pas de '2H)13C').
    text = (
        "1H NMR (400 MHz, CDCl3, 298 K) δ 9.18 (dd, J = 4.7 Hz, 2H) "
        "13C NMR (100 MHz, CDCl3, 298 K) δ 149.4 (2C)"
    )
    result = RULE.apply(text)
    assert "2H) 13C NMR" in result.new_text
    assert "2H)13C" not in result.new_text
