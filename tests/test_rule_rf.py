"""Règle Rf : format LCMCE, f en indice Word, valeur jamais modifiée."""

import pytest
from docx import Document

from core import config as cfg
from core.config import RmnConfig
from core.processor import build_registry, process_texts, standardize_file
from core.rules.base import ActionKind
from core.rules.rf import RfRule

RULE = RfRule()
TARGET = "Rf = 0.38 (SiO₂; heptane/CH₂Cl₂ 1:1)"


def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]


def test_typical_entry_is_normalized():
    assert RULE.apply("Rf = 0.38 (SiO2; heptane/CH2Cl2 1:1)").new_text == TARGET


@pytest.mark.parametrize("written", [
    "Rf = 0.38 (SiO2; heptane/CH2Cl2 1:1)",
    "Rf: 0.38 (SiO2; heptane/CH2Cl2 1:1)",
    "Rf 0.38 (SiO2; heptane/CH2Cl2 1:1)",
    "R.f. = 0.38 (SiO2; heptane/CH2Cl2 1:1)",
    "R_f = 0.38 (SiO2; heptane/CH2Cl2 1:1)",
    "Rf (SiO2; heptane/CH2Cl2 1:1) = 0.38",
    "Rf = 0.38 (SiO2, heptane/CH2Cl2 1:1)",
    "Rf=0.38 (SiO2;  heptane/CH2Cl2   1:1)",
])
def test_variants_give_the_target(written):
    result = RULE.apply(written)
    assert result.new_text == TARGET
    assert not _flags(result)


def test_output_is_idempotent():
    result = RULE.apply(TARGET)
    assert result.new_text == TARGET
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_conform_output_is_recognized():
    assert RULE.applies(TARGET)


def test_segments_label_is_bold_with_word_subscript_f():
    result = RULE.apply("Rf = 0.38 (SiO2; heptane/CH2Cl2 1:1)")
    assert "".join(s.text for s in result.segments) == TARGET
    assert result.replaced_text == "Rf = 0.38 (SiO2; heptane/CH2Cl2 1:1)"
    r, f, rest = result.segments
    assert (r.text, r.bold, r.subscript) == ("R", True, False)
    assert (f.text, f.bold, f.subscript) == ("f", True, True)
    assert not rest.bold and not rest.subscript and not rest.italic


def test_label_bold_is_configurable():
    cfg.set_config(RmnConfig(bold_label=False))
    r, f, _ = RULE.apply("Rf = 0.38 (SiO2; heptane/CH2Cl2 1:1)").segments
    assert not r.bold and not f.bold and f.subscript


def test_text_around_the_entry_is_kept():
    result = RULE.apply("Composé 3 : Rf = 0.38 (SiO2; heptane/CH2Cl2 1:1) ; pf 12")
    assert result.new_text == f"Composé 3 : {TARGET} ; pf 12"


def test_trailing_punctuation_is_kept():
    result = RULE.apply("Rf = 0.38 (SiO2; heptane/EtOAc 4:1).")
    assert result.new_text == "Rf = 0.38 (SiO₂; heptane/EtOAc 4:1)."


# --- Vérifications : valeur conservée, signalement ----------------------------------

def test_wrong_decimals_are_flagged_value_kept():
    result = RULE.apply("Rf = 0.4 (SiO2; heptane/EtOAc 4:1)")
    assert "0.4 (SiO₂" in result.new_text
    assert any(m.startswith("Nombre de décimales du Rf inattendu : ") for m in _flags(result))


def test_three_decimals_are_flagged():
    assert _flags(RULE.apply("Rf = 0.385 (SiO2; heptane/EtOAc 4:1)"))


def test_value_above_one_is_flagged_and_kept():
    result = RULE.apply("Rf = 1.35 (SiO2; heptane/EtOAc 4:1)")
    assert "1.35" in result.new_text
    assert any(m.startswith("Rf hors de l'intervalle [0 ; 1] : ") for m in _flags(result))


def test_missing_stationary_phase_is_flagged():
    result = RULE.apply("Rf = 0.35 (pentane/EtOAc 4:1)")
    assert [m for m in _flags(result) if m.startswith("Phase stationnaire absente")]


def test_missing_ratio_is_flagged():
    result = RULE.apply("Rf = 0.35 (SiO2; pentane/EtOAc)")
    assert [m for m in _flags(result) if m.startswith("Proportions de l'éluant absentes")]


def test_missing_parenthesis_is_flagged_and_text_kept():
    text = "Rf = 0.35"
    result = RULE.apply(text)
    assert result.new_text == text
    assert [m for m in _flags(result) if m.startswith("Éluant et phase stationnaire absents")]


def test_flags_survive_on_conform_text():
    text = "Rf = 0.4 (SiO₂; heptane/EtOAc 4:1)"
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result) and ActionKind.UNCHANGED not in [a.kind for a in result.actions]


def test_decimal_comma_is_flagged_and_kept():
    text = "Rf = 0,35 (SiO2; heptane/EtOAc 4:1)"
    result = RULE.apply(text)
    assert result.new_text == text and _flags(result)


@pytest.mark.parametrize("text", [
    "Rf = 0.3-0.4 (SiO2; heptane/EtOAc 4:1)",            # plage
    "Rf (SiO2) = 0.35 (heptane/EtOAc 4:1)",              # deux parenthèses
])
def test_unrecognized_structure_is_flagged_unchanged(text):
    result = RULE.apply(text)
    assert result.new_text == text and _flags(result)


def test_c18_and_f254_are_not_subscripted():
    result = RULE.apply("Rf = 0.35 (silica gel 60 F254; EtOAc/hexane 1:4)")
    assert "F254" in result.new_text and "F₂₅₄" not in result.new_text
    result = RULE.apply("Rf = 0.35 (C18; MeOH/H2O 7:3)")
    assert "C18" in result.new_text and "H₂O" in result.new_text


def test_prose_mention_is_ignored():
    assert not RULE.applies("Les valeurs de Rf ont été mesurées sur plaque.")


def test_messages_have_fixed_part_before_values():
    result = RULE.apply("Rf = 0.4 (SiO2; heptane/EtOAc 4:1)")
    assert _flags(result)[0].split(" : ")[0] == "Nombre de décimales du Rf inattendu"


# --- Chaîne complète et sections collées -------------------------------------------

def test_in_chain_with_nmr_section_before():
    text = "13C NMR (101 MHz, CDCl3, 298 K) δ 77.0. Rf = 0.30 (SiO2; A/B 1:1)"
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final == (
        "¹³C NMR (101 MHz, CDCl₃, 298 K) δ (ppm) = 77.0. Rf = 0.30 (SiO₂; A/B 1:1)"
    )


def test_rf_rule_is_in_the_catalog():
    from core.processor import available_rules

    assert "Rf" in [r.name for r in available_rules()]


# --- Document Word : f réellement en indice ----------------------------------------

def test_docx_output_has_subscript_f_only(tmp_path):
    src, out = tmp_path / "in.docx", tmp_path / "out.docx"
    doc = Document()
    doc.add_paragraph("Rf = 0.38 (SiO2; heptane/CH2Cl2 1:1)")
    doc.save(src)
    standardize_file(str(src), str(out))
    runs = Document(out).paragraphs[0].runs
    assert "".join(r.text for r in runs) == TARGET
    subs = [r.text for r in runs if r.font.subscript]
    assert subs == ["f"]
    assert [r.text for r in runs if r.bold] == ["R", "f"]
