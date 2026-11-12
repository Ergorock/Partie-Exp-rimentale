"""Règle IR : méthode entre parenthèses, bandes entières en cm⁻¹, tri décroissant."""

import pytest

from core import config as cfg
from core.config import RmnConfig
from core.processor import build_registry, process_texts
from core.rules.base import ActionKind
from core.rules.ir import IrRule

RULE = IrRule()
NU = "ν\u0303"  # ν + U+0303
TARGET = f"IR (ATR): {NU}(cm⁻¹) = 3420, 1715, 1600"


def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]


# --- Mise en forme --------------------------------------------------------------------

def test_typical_entry_is_normalized():
    assert RULE.apply("IR (ATR) 3420, 1715, 1600 cm-1").new_text == TARGET


def test_output_is_idempotent():
    result = RULE.apply(TARGET)
    assert result.new_text == TARGET
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_segments_match_new_text():
    result = RULE.apply("IR (ATR) 3420, 1715, 1600 cm-1")
    assert "".join(s.text for s in result.segments) == TARGET
    assert result.replaced_text == "IR (ATR) 3420, 1715, 1600 cm-1"


def test_only_label_is_bold():
    result = RULE.apply("IR (ATR) 3420, 1715 cm-1")
    assert [s.text for s in result.segments if s.bold] == ["IR"]
    assert not any(s.italic for s in result.segments)


def test_bold_label_is_configurable():
    cfg.set_config(RmnConfig(bold_label=False))
    result = RULE.apply("IR (ATR) 3420, 1715 cm-1")
    assert not any(s.bold for s in result.segments)


@pytest.mark.parametrize(
    "raw",
    [
        "IR (ATR) νmax 3420, 1715, 1600 cm-1",
        "IR (ATR) vmax 3420, 1715, 1600 cm-1",
        "IR (ATR) ν 3420, 1715, 1600 cm−1",
        "IR (ATR) ν̃ = 3420, 1715, 1600 cm^-1",
        "IR (ATR): 3420, 1715, 1600 cm⁻¹",
        "IR (ATR) νmax/cm-1 3420, 1715, 1600",
        "IR (ATR) ν (cm-1) 3420, 1715, 1600",
        "IR (ATR, cm-1) ν̃ = 3420, 1715, 1600",
        "IR (ATR, cm⁻¹): ν̃ = 3420, 1715, 1600",
        "IR (ATR) 3420, 1715, 1600",
        "IR (ATR) 1600, 3420, 1715 cm-1",
        "IR (ATR) ν̃ : 3420, 1715, 1600 cm-1",
    ],
)
def test_variants_are_normalized(raw):
    result = RULE.apply(raw)
    assert result.new_text == TARGET
    assert not _flags(result)


def test_methods_are_copied_with_subscripts():
    result = RULE.apply("IR (CHCl3) 3420, 1715 cm-1")
    assert result.new_text == f"IR (CHCl₃): {NU}(cm⁻¹) = 3420, 1715"
    assert RULE.apply("IR (KBr) 3420 cm-1").new_text == f"IR (KBr): {NU}(cm⁻¹) = 3420"
    assert RULE.apply("IR (neat) 3420 cm-1").new_text == f"IR (neat): {NU}(cm⁻¹) = 3420"
    assert RULE.apply("IR (film) 3420 cm-1").new_text == f"IR (film): {NU}(cm⁻¹) = 3420"


def test_attributions_and_intensities_are_kept():
    result = RULE.apply("IR (ATR) 1600 (s), 3420 (br, O-H), 1715 (C=O) cm-1")
    assert result.new_text == (
        f"IR (ATR): {NU}(cm⁻¹) = 3420 (br, O-H), 1715 (C=O), 1600 (s)"
    )
    assert not _flags(result)


def test_bands_are_sorted_descending():
    result = RULE.apply("IR (ATR) 1020, 2950, 1715, 3420 cm-1")
    assert result.new_text == f"IR (ATR): {NU}(cm⁻¹) = 3420, 2950, 1715, 1020"


def test_trailing_punctuation_is_kept():
    result = RULE.apply("IR (ATR) 3420, 1715 cm-1.")
    assert result.new_text == f"IR (ATR): {NU}(cm⁻¹) = 3420, 1715."
    result = RULE.apply("IR (ATR) 3420, 1715.")
    assert result.new_text == f"IR (ATR): {NU}(cm⁻¹) = 3420, 1715."


def test_prefix_and_suffix_are_kept():
    text = "Composé 3. IR (ATR) 3420, 1715 cm-1 \u2003"
    result = RULE.apply(text)
    assert result.new_text == f"Composé 3. IR (ATR): {NU}(cm⁻¹) = 3420, 1715 \u2003"
    assert result.replaced_text == "IR (ATR) 3420, 1715 cm-1"


def test_text_after_the_bands_is_never_dropped():
    # Sans label d'analyse suivant, le segment va jusqu'à la fin : texte inconnu -> intact.
    text = "IR (ATR) 3420, 1715 cm-1. Rendement 80 %."
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result)


def test_nbsp_is_handled():
    result = RULE.apply("IR\xa0(ATR)\xa03420,\xa01715\xa0cm-1")
    assert result.new_text == f"IR (ATR): {NU}(cm⁻¹) = 3420, 1715"


# --- Vérifications (jamais de valeur modifiée) -----------------------------------------

def test_values_are_never_changed():
    result = RULE.apply("IR (ATR) 3420, 1715, 1600 cm-1")
    for value in ("3420", "1715", "1600"):
        assert value in result.new_text


def test_decimal_band_is_flagged_and_kept():
    text = "IR (ATR) 3420, 1715.5, 1600 cm-1"
    result = RULE.apply(text)
    assert result.new_text == text
    assert result.segments is None
    assert len(_flags(result)) == 1


def test_decimal_comma_is_flagged_and_kept():
    text = "IR (ATR) 3420, 1715,5, 1600 cm-1"
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result)


def test_text_outside_parenthesis_is_flagged_and_kept():
    text = "IR (ATR) 3420 large, 1715 cm-1"
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result)


def test_nested_parenthesis_is_flagged_and_kept():
    text = "IR (ATR) 3420 (br (OH)), 1715 cm-1"
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result)


def test_missing_method_is_flagged_and_kept():
    text = "IR 3420, 1715, 1600 cm-1"
    result = RULE.apply(text)
    assert result.new_text == text
    assert result.segments is None
    assert _flags(result)


def test_no_band_is_flagged_and_kept():
    text = "IR (ATR) cm-1"
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result)


def test_flag_messages_have_fixed_part_before_colon():
    result = RULE.apply("IR (ATR) 3420, 1715.5 cm-1")
    message = _flags(result)[0]
    assert " : " in message
    assert "1715.5" not in message.split(" : ")[0]


def test_flagged_entry_keeps_flag_when_already_conform_looking():
    text = f"IR (ATR): {NU}(cm⁻¹) = 3420, 1715.5"
    result = RULE.apply(text)
    assert result.new_text == text
    assert ActionKind.UNCHANGED not in [a.kind for a in result.actions]


# --- Détection ------------------------------------------------------------------------

def test_prose_mention_is_ignored():
    assert not RULE.applies("Les spectres IR ont été enregistrés sur un appareil Bruker.")
    assert not RULE.applies("Le FTIR est une technique courante.")


def test_conform_output_is_recognized():
    assert RULE.applies(TARGET)
    assert RULE.applies("IR (ATR) 3420 cm-1")


# --- Intégration ----------------------------------------------------------------------

def test_nmr_section_stops_before_ir():
    text = "13C NMR (100 MHz, CDCl3, 298 K) δ 77.0, 128.0. IR (ATR) 3420, 1715 cm-1"
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final == (
        "¹³C NMR (100 MHz, CDCl₃, 298 K) δ (ppm) = 128.0, 77.0. "
        f"IR (ATR): {NU}(cm⁻¹) = 3420, 1715"
    )


def test_ir_stops_before_hrms():
    text = (
        "IR (ATR) 1715, 3420 cm-1. "
        "HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165.0910; Found 165.0912."
    )
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final == (
        f"IR (ATR): {NU}(cm⁻¹) = 3420, 1715. "
        "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0912."
    )


def test_full_chain_on_ir_paragraph():
    report = process_texts(["IR (KBr) 1715, 3420 cm-1"], build_registry())
    assert report.paragraphs[0].new_text == f"IR (KBr): {NU}(cm⁻¹) = 3420, 1715"
