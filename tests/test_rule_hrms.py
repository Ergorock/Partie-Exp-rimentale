"""Règle HRMS : format ACS, recalcul de la masse exacte, écart en ppm."""

import pytest

from core import config as cfg
from core.config import RmnConfig
from core.processor import build_registry, process_texts
from core.rules import mass
from core.rules.base import ActionKind
from core.rules.hrms import HrmsRule

RULE = HrmsRule()
TARGET = "HRMS (ESI-TOF) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0912."


def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]


# --- Calcul de masse ---------------------------------------------------------------

def test_monoisotopic_mass_of_simple_formula():
    assert mass.monoisotopic_mass("C10H12O2") == pytest.approx(164.083730, abs=1e-5)


def test_formula_with_groups_and_subscripts():
    assert mass.parse_formula("C6H5(CH3)2") == {"C": 8, "H": 11}
    assert mass.parse_formula("C₁₀H₁₃O₂") == {"C": 10, "H": 13, "O": 2}


def test_unknown_element_is_not_computed():
    assert mass.parse_formula("C10Xx2") is None
    assert mass.monoisotopic_mass("C10Xx2") is None


# --- Mise en forme -----------------------------------------------------------------

def test_typical_entry_is_normalized():
    result = RULE.apply(
        "HRMS (ESI-TOF) m/z: [M+H]+ calcd for C10H13O2 165.0910, found 165.0912."
    )
    assert result.new_text == TARGET
    assert not _flags(result)


def test_output_is_idempotent():
    result = RULE.apply(TARGET)
    assert result.new_text == TARGET
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_styles_label_bold_and_mz_italic():
    result = RULE.apply("HRMS (ESI-TOF) m/z: [M+H]+ calcd for C10H13O2 165.0910, found 165.0912.")
    assert [s.text for s in result.segments if s.italic] == ["m/z"]
    assert [s.text for s in result.segments if s.bold] == ["HRMS"]
    assert result.segments[1].text == " (ESI-TOF) " and not result.segments[1].bold
    assert "".join(s.text for s in result.segments) == result.new_text


def test_ion_written_after_formula_is_moved_before_calcd():
    result = RULE.apply("HRMS (ESI) calcd for C10H12O2Na [M+Na]+ 187.0730, found 187.0733")
    assert result.new_text == (
        "HRMS (ESI) m/z: [M + Na]⁺ Calcd for C₁₀H₁₂O₂Na 187.0730; Found 187.0733"
    )
    assert not _flags(result)


def test_negative_ion():
    result = RULE.apply("HRMS (ESI) m/z: [M-H]- calcd for C10H11O2 163.0765, found 163.0763.")
    assert result.new_text == (
        "HRMS (ESI) m/z: [M − H]⁻ Calcd for C₁₀H₁₁O₂ 163.0765; Found 163.0763."
    )
    assert not _flags(result)


def test_radical_cation_and_unbracketed_ion():
    result = RULE.apply("HRMS (EI) m/z: M+• calcd for C10H12O2 164.0832, found 164.0835.")
    assert "m/z: [M]⁺• Calcd for C₁₀H₁₂O₂ 164.0832; Found 164.0835." in result.new_text
    assert not _flags(result)


def test_charge_inside_parenthesis():
    result = RULE.apply("HRMS (EI): calcd for C10H12O2 (M+) 164.0832, found 164.0835")
    assert result.new_text == "HRMS (EI) m/z: [M]⁺ Calcd for C₁₀H₁₂O₂ 164.0832; Found 164.0835"
    assert not _flags(result)


def test_period_between_calcd_and_found():
    result = RULE.apply("HRMS (ESI) m/z: [M+H]+ calcd. for C10H13O2: 165.0910. Found: 165.0912.")
    assert result.new_text == TARGET.replace("ESI-TOF", "ESI")


def test_prefix_and_suffix_are_kept():
    text = "Composé 3. HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165.0910; Found 165.0912. Rendement 80 %."
    result = RULE.apply(text)
    assert result.new_text.startswith("Composé 3. HRMS (ESI) m/z: [M + H]⁺")
    assert result.new_text.endswith("Found 165.0912. Rendement 80 %.")
    assert result.replaced_text in text


# --- Vérifications (jamais de valeur modifiée) -----------------------------------------

def test_neutral_formula_convention_is_accepted():
    result = RULE.apply("HRMS (ESI) m/z: [M + H]+ Calcd for C10H12O2 165.0910; Found 165.0912.")
    assert not _flags(result)


def test_calcd_without_electron_correction_is_accepted():
    result = RULE.apply("HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165.0916; Found 165.0912.")
    assert not _flags(result)


def test_wrong_calcd_is_flagged_and_kept():
    result = RULE.apply("HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165.0950; Found 165.0952.")
    assert "165.0950" in result.new_text and "165.0952" in result.new_text
    flags = _flags(result)
    assert any("165.0910" in f for f in flags)


def test_found_outside_tolerance_is_flagged():
    result = RULE.apply("HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165.0910; Found 165.0930.")
    assert "Found 165.0930" in result.new_text
    assert any("ppm" in f for f in _flags(result))


def test_ppm_tolerance_is_configurable():
    cfg.set_config(RmnConfig(hrms_ppm_tolerance=15.0))
    result = RULE.apply("HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165.0910; Found 165.0930.")
    assert not _flags(result)


def test_unknown_element_flags_verification_but_formats():
    result = RULE.apply("HRMS (ESI) m/z: [M + H]+ Calcd for C10Xx2 165.0910; Found 165.0912.")
    assert "Calcd for C₁₀Xx₂ 165.0910" in result.new_text
    assert any("vérif" in f for f in _flags(result))


def test_missing_ion_is_flagged():
    result = RULE.apply("HRMS (ESI) calcd for C10H13O2 165.0910, found 165.0912")
    assert result.new_text == "HRMS (ESI) m/z: Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0912"
    assert any("Ion" in f for f in _flags(result))


def test_missing_ionization_method_is_flagged():
    result = RULE.apply("HRMS m/z: [M + H]+ Calcd for C10H13O2 165.0910; Found 165.0912.")
    assert result.new_text.startswith("HRMS m/z: [M + H]⁺")
    assert any("ionisation" in f for f in _flags(result))


def test_unrecognized_structure_is_flagged_unchanged():
    text = "HRMS (ESI) m/z 165.0912 (M+H)"
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result)


def test_decimal_comma_is_not_rewritten():
    text = "HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165,0910; Found 165,0912."
    result = RULE.apply(text)
    assert result.new_text == text
    assert _flags(result)


def test_prose_mention_is_ignored():
    assert not RULE.applies("Les analyses HRMS ont été réalisées sur un Q-TOF.")


# --- Intégration avec les sections RMN ----------------------------------------------

def test_nmr_section_stops_before_hrms():
    text = (
        "13C NMR (100 MHz, CDCl3, 298 K) δ 77.0, 128.0. "
        "HRMS (ESI) m/z: [M + H]+ Calcd for C10H13O2 165.0910; Found 165.0912."
    )
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final == (
        "¹³C NMR (100 MHz, CDCl₃, 298 K) δ (ppm) = 128.0, 77.0. "
        "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0912."
    )


def test_hrms_tolerance_config_roundtrip():
    data = cfg.config_to_dict(RmnConfig(hrms_ppm_tolerance=3.0))
    assert data["hrms_ppm_tolerance"] == 3.0
    assert cfg.config_from_dict(data).hrms_ppm_tolerance == 3.0
    for bad in (-1, 0, "5", True, None):
        assert cfg.config_from_dict({"hrms_ppm_tolerance": bad}).hrms_ppm_tolerance == 5.0
