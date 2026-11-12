"""Règle m.p. / b.p. : structure imposée LCMCE, valeurs jamais modifiées."""

import pytest
from docx import Document

from core import config as cfg
from core.config import RmnConfig
from core.processor import available_rules, build_registry, process_texts, standardize_file
from core.rules.base import ActionKind
from core.rules.melting_point import MeltingPointRule

NB = "\u00a0"
RULE = MeltingPointRule()
TARGET = f"m.p. 185{NB}–{NB}186{NB}°C"
FULL = f"m.p. 185{NB}–{NB}186{NB}°C (Et₂O/hexane; dec.; lit. [12] 185{NB}–{NB}187{NB}°C)"


def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]


def _corrections(result):
    return [a.message for a in result.actions if a.kind == ActionKind.CORRECTED]


# --- Forme de base --------------------------------------------------------------

@pytest.mark.parametrize("written", [
    "m.p. 185-186 °C",
    "mp 185–186 °C",
    "Mp: 185 - 186 °C",
    "M.p. = 185–186°C",
    "MP 185 – 186 ºC",
    "m. p. 185-186 ˚C",
    "melting point 185-186 C",
    f"m.p. 185{NB}–{NB}186{NB}°C",
])
def test_variants_give_the_target(written):
    result = RULE.apply(written)
    assert result.new_text == TARGET
    assert not _flags(result)


def test_single_value():
    assert RULE.apply("mp 128 °C").new_text == f"m.p. 128{NB}°C"


def test_output_is_idempotent_and_recognized():
    for text in (TARGET, FULL, f"b.p. 80{NB}°C (15{NB}mmHg)"):
        assert RULE.applies(text)
        result = RULE.apply(text)
        assert result.new_text == text
        assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_segments_and_replaced_text():
    original = "Composé 3 : mp 185-186 °C ; autre"
    result = RULE.apply(original)
    assert result.new_text == f"Composé 3 : {TARGET} ; autre"
    assert result.replaced_text == "mp 185-186 °C"
    assert "".join(s.text for s in result.segments) == TARGET
    label, rest = result.segments
    assert label.text == "m.p." and label.bold and not label.subscript
    assert not rest.bold and not rest.italic


def test_label_bold_is_configurable():
    cfg.set_config(RmnConfig(bold_label=False))
    assert not RULE.apply("mp 128 °C").segments[0].bold


# --- Structure de la parenthèse -------------------------------------------------------

def test_parenthesis_items_are_reordered():
    result = RULE.apply("mp 185-186 °C (lit. [12] 185-187 °C; dec.; Et2O/hexane)")
    assert result.new_text == FULL


def test_colon_literature_form_from_the_guide():
    result = RULE.apply("m.p. 185 – 186 °C (Et2O/hexane: [12] 185 – 187 °C)")
    assert result.new_text == (
        f"m.p. 185{NB}–{NB}186{NB}°C (Et₂O/hexane; lit. [12] 185{NB}–{NB}187{NB}°C)"
    )


@pytest.mark.parametrize("written", ["(dec.)", "(decomp.)", "(decomposition)", "dec."])
def test_decomposition_variants(written):
    result = RULE.apply(f"mp 128 °C {written}")
    assert result.new_text == f"m.p. 128{NB}°C (dec.)"


def test_solvent_gets_unicode_subscripts_but_not_c18():
    assert RULE.apply("mp 128 °C (CH2Cl2/MeOH)").new_text.endswith("(CH₂Cl₂/MeOH)")
    assert RULE.apply("mp 128 °C (EtOH)").new_text.endswith("(EtOH)")


def test_literature_without_reference():
    assert RULE.apply("mp 120 °C (lit. 119-121 °C)").new_text == (
        f"m.p. 120{NB}°C (lit. 119{NB}–{NB}121{NB}°C)"
    )


def test_literature_value_is_not_required():
    result = RULE.apply("mp 120 °C (EtOH)")
    assert not _flags(result)


# --- b.p. et pression -------------------------------------------------------------------

@pytest.mark.parametrize("written", [
    "bp 80 °C / 15 mmHg",
    "b.p. 80 °C (15 mmHg)",
    "Bp 80°C at 15 mmHg",
    "boiling point 80 °C/15 mmHg",
])
def test_boiling_point_with_pressure(written):
    assert RULE.apply(written).new_text == f"b.p. 80{NB}°C (15{NB}mmHg)"


def test_boiling_point_without_pressure():
    assert RULE.apply("b.p. 80 °C").new_text == f"b.p. 80{NB}°C"


# --- Vérifications : valeurs conservées -----------------------------------------------

def test_decimals_are_flagged_and_values_kept():
    result = RULE.apply("mp 185.5-186 °C (lit. 186.5 °C)")
    messages = [m for m in _flags(result) if m.startswith("Nombre de décimales de la température")]
    assert len(messages) == 1
    assert "185.5 (1)" in messages[0] and "186.5 (1)" in messages[0]
    assert "185.5" in result.new_text and "186.5" in result.new_text


def test_reversed_range_is_flagged_not_corrected():
    result = RULE.apply("mp 130-128 °C")
    assert f"130{NB}–{NB}128" in result.new_text
    assert any(m.startswith("Plage de températures inversée : ") for m in _flags(result))


def test_reversed_literature_range_is_flagged():
    assert any("inversée" in m for m in _flags(RULE.apply("mp 120 °C (lit. 121-119 °C)")))


def test_missing_unit_is_added_and_reported():
    result = RULE.apply("mp 128")
    assert result.new_text == f"m.p. 128{NB}°C"
    assert any(m.startswith("Unité de la température absente : ") for m in _corrections(result))


def test_present_unit_is_not_reported():
    assert not any(m.startswith("Unité") for m in _corrections(RULE.apply("mp 128 °C")))


def test_kelvin_is_never_converted():
    text = "mp 401 K"
    result = RULE.apply(text)
    assert result.new_text == text
    assert any(m.startswith("Température en kelvins : ") for m in _flags(result))


@pytest.mark.parametrize("text", [
    "mp 128,5 °C",                    # virgule décimale
    "mp 120 °C (EtOH, hexane)",       # deux solvants
    "mp 120 °C (dec.; décomp.)",      # élément en double
    "mp 120 °C (lit. [3])",           # littérature illisible
])
def test_unrecognized_structure_is_flagged_unchanged(text):
    result = RULE.apply(text)
    assert result.new_text == text and _flags(result)


def test_flags_survive_on_conform_text():
    text = f"m.p. 185.5{NB}°C"
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result) and ActionKind.UNCHANGED not in [a.kind for a in result.actions]


def test_message_fixed_part_before_values():
    message = _flags(RULE.apply("mp 185.5 °C"))[0]
    assert message.split(" : ")[0] == "Nombre de décimales de la température inattendu"


# --- Plusieurs entrées, prose, chaîne ---------------------------------------------------

def test_several_entries_in_one_paragraph():
    result = RULE.apply("mp 120-121 °C ; bp 80 °C / 15 mmHg")
    assert result.new_text == (
        f"m.p. 120{NB}–{NB}121{NB}°C ; b.p. 80{NB}°C (15{NB}mmHg)"
    )
    assert result.replaced_text == "mp 120-121 °C ; bp 80 °C / 15 mmHg"
    assert [s.text for s in result.segments if s.bold] == ["m.p.", "b.p."]


def test_prose_mention_is_ignored():
    assert not RULE.applies("Le mp des composés est élevé.")
    assert not RULE.applies("La bp est utilisée.")


def test_in_chain_with_rf_and_nmr():
    text = "13C NMR (101 MHz, CDCl3, 298 K) δ 77.0. mp 120-121 °C"
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final == (
        f"¹³C NMR (101 MHz, CDCl₃, 298 K) δ (ppm) = 77.0. m.p. 120{NB}–{NB}121{NB}°C"
    )
    both = "Rf = 0.30 (SiO2; A/B 1:1) ; mp 120-121 °C"
    assert process_texts([both], build_registry()).paragraphs[0].new_text == (
        f"Rf = 0.30 (SiO₂; A/B 1:1) ; m.p. 120{NB}–{NB}121{NB}°C"
    )


def test_rule_is_in_the_catalog():
    assert "m.p. / b.p." in [r.name for r in available_rules()]


def test_docx_output_bolds_only_the_label(tmp_path):
    src, out = tmp_path / "in.docx", tmp_path / "out.docx"
    doc = Document()
    doc.add_paragraph("mp 185-186 °C (Et2O)")
    doc.save(src)
    standardize_file(str(src), str(out))
    runs = Document(out).paragraphs[0].runs
    assert "".join(r.text for r in runs) == f"m.p. 185{NB}–{NB}186{NB}°C (Et₂O)"
    assert [r.text for r in runs if r.bold] == ["m.p."]
    assert not any(r.font.subscript for r in runs)


def test_french_decomposition_abbreviations():
    for written in ("(décomp.)", "(déc.)", "décomp."):
        assert RULE.apply(f"mp 128 °C {written}").new_text == f"m.p. 128{NB}°C (dec.)"
