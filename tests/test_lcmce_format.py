"""Format LCMCE (Scientific Writing Tips) : plages, δ (ppm) =, intégration, ``;``,
décimales contrôlées, plages IR et tolérance HRMS absolue.

Les valeurs ne sont jamais modifiées : un nombre de décimales inattendu est
seulement signalé (FLAGGED).
"""

import pytest

from core import config as cfg
from core.config import RmnConfig
from core.processor import build_registry, process_texts
from core.rules.base import ActionKind
from core.rules.hrms import HrmsRule
from core.rules.ir import IrRule
from core.rules.nmr_13c import ThirteenCNmrRule
from core.rules.nmr_1h import OneHNmrRule
from core.rules.nmr_hetero import NineteenFNmrRule

NB = "\u00a0"
RULE_1H = OneHNmrRule()
RULE_13C = ThirteenCNmrRule()
HEAD = "1H NMR (400 MHz, CDCl3, 298 K) δ "
STYLED_HEAD = "¹H NMR (400 MHz, CDCl₃, 298 K) δ (ppm) = "


def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]


def _decimal_flags(result):
    return [m for m in _flags(result) if "décimales" in m]


# --- Plage : tiret demi-cadratin entouré d'espaces ---------------------------------

def test_range_is_written_with_spaced_en_dash():
    result = RULE_1H.apply(HEAD + "7.31-7.24 (m, 2H)")
    assert result.new_text == f"{STYLED_HEAD}7.31{NB}–{NB}7.24 (m, 2{NB}H)"


@pytest.mark.parametrize("sep", ["-", "–", " - ", " – ", f"{NB}–{NB}"])
def test_range_variants_give_the_same_output(sep):
    result = RULE_1H.apply(HEAD + f"7.31{sep}7.24 (m, 2H)")
    assert result.new_text == f"{STYLED_HEAD}7.31{NB}–{NB}7.24 (m, 2{NB}H)"


def test_range_is_sorted_on_its_upper_bound_and_idempotent():
    result = RULE_1H.apply(HEAD + "1.20 (t, 3H), 7.31-7.24 (m, 2H)")
    assert result.new_text.index("7.31") < result.new_text.index("1.20")
    again = RULE_1H.apply(result.new_text)
    assert again.new_text == result.new_text
    assert [a.kind for a in again.actions] == [ActionKind.UNCHANGED]


# --- δ (ppm) = ----------------------------------------------------------------------

def test_delta_is_followed_by_ppm_equal_sign():
    result = RULE_1H.apply(HEAD + "7.26 (s, 1H)")
    assert result.new_text == f"{STYLED_HEAD}7.26 (s, 1{NB}H)"


def test_only_delta_is_italic_not_ppm():
    result = RULE_1H.apply(HEAD + "7.26 (s, 1H)")
    assert [s.text for s in result.segments if s.italic] == ["δ"]
    assert " (ppm) =" in [s.text for s in result.segments]


@pytest.mark.parametrize("variant", ["δ", "ẟ", "δ (ppm) =", "ẟ (ppm) =", "δ (ppm)", "δ ="])
def test_delta_variants_are_normalized(variant):
    result = RULE_1H.apply(f"1H NMR (400 MHz, CDCl3, 298 K) {variant} 7.26 (s, 1H)")
    assert result.new_text == f"{STYLED_HEAD}7.26 (s, 1{NB}H)"


def test_13c_also_uses_delta_ppm():
    result = RULE_13C.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 77.0")
    assert result.new_text == "¹³C NMR (101 MHz, CDCl₃, 298 K) δ (ppm) = 77.0"


# --- Intégration « 5 H » et point-virgule avant l'attribution -----------------------

def test_integration_has_a_non_breaking_space():
    result = RULE_1H.apply(HEAD + "4.31 (d, J = 17.2 Hz, 1H)")
    assert result.new_text.endswith(f"4.31 (d, J = 17.2 Hz, 1{NB}H)")


@pytest.mark.parametrize("written", ["5H", "5 H", f"5{NB}H"])
def test_integration_variants(written):
    result = RULE_1H.apply(HEAD + f"4.60 (m, {written})")
    assert result.new_text.endswith(f"4.60 (m, 5{NB}H)")


def test_semicolon_between_integration_and_attribution():
    result = RULE_1H.apply(HEAD + "4.60 (m, 5H, OCH2)")
    assert result.new_text.endswith(f"4.60 (m, 5{NB}H; OCH₂)")


def test_semicolon_input_form_is_recognized_and_idempotent():
    text = HEAD + "4.60 (m, 5 H; OCH2, Ar-H)"
    result = RULE_1H.apply(text)
    assert result.new_text.endswith(f"4.60 (m, 5{NB}H; OCH₂, Ar-H)")
    again = RULE_1H.apply(result.new_text)
    assert again.new_text == result.new_text
    assert [a.kind for a in again.actions] == [ActionKind.UNCHANGED]


def test_13c_attribution_keeps_its_parenthesis_without_semicolon():
    result = RULE_13C.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 213.2 (C=S), 21.1 (CH3)")
    assert result.new_text.endswith("213.2 (C=S), 21.1 (CH₃)")


# --- Décimales : contrôlées, jamais modifiées -----------------------------------------

def test_1h_shift_with_wrong_decimals_is_flagged_and_kept():
    result = RULE_1H.apply(HEAD + "7.2 (s, 1H), 1.20 (t, 3H)")
    messages = _decimal_flags(result)
    assert len(messages) == 1 and "7.2 (1)" in messages[0]
    assert "7.2 (s," in result.new_text  # valeur conservée


def test_1h_three_decimals_are_tolerated():
    assert not _decimal_flags(RULE_1H.apply(HEAD + "7.263 (s, 1H), 1.20 (t, 3H)"))


def test_1h_integer_shift_is_flagged():
    assert _decimal_flags(RULE_1H.apply(HEAD + "7 (s, 1H)"))


def test_j_needs_one_decimal():
    result = RULE_1H.apply(HEAD + "7.26 (d, J = 8 Hz, 1H), 1.20 (dd, J = 8.43, 2.1 Hz, 3H)")
    messages = [m for m in _flags(result) if "constante de couplage" in m]
    assert len(messages) == 1
    assert "8 (0)" in messages[0] and "8.43 (2)" in messages[0]
    assert "2.1" not in messages[0]


def test_range_bounds_are_both_checked():
    assert _decimal_flags(RULE_1H.apply(HEAD + "7.31-7.2 (m, 2H)"))
    assert not _decimal_flags(RULE_1H.apply(HEAD + "7.31-7.24 (m, 2H)"))


def test_13c_expects_one_decimal():
    ok = RULE_13C.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 128.0, 77.05")
    assert not _decimal_flags(ok)
    bad = RULE_13C.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 128, 77.0")
    assert len(_decimal_flags(bad)) == 1 and "128 (0)" in _decimal_flags(bad)[0]


def test_19f_expects_one_decimal():
    result = NineteenFNmrRule().apply("19F NMR (376 MHz, CDCl3, 298 K) δ -63.25, -20.9")
    assert not _decimal_flags(result)
    assert _decimal_flags(NineteenFNmrRule().apply("19F NMR (376 MHz, CDCl3, 298 K) δ -63, -20.9"))


def test_decimal_flag_survives_on_conform_text():
    text = f"{STYLED_HEAD}7.2 (s, 1{NB}H)"
    result = RULE_1H.apply(text)
    assert result.new_text == text
    assert _decimal_flags(result)
    assert ActionKind.UNCHANGED not in [a.kind for a in result.actions]


def test_decimal_message_has_a_fixed_part_before_the_values():
    message = _decimal_flags(RULE_1H.apply(HEAD + "7.2 (s, 1H)"))[0]
    assert message.split(" : ")[0] == "Nombre de décimales du déplacement chimique inattendu"


def test_unparsable_list_is_not_checked_for_decimals():
    result = RULE_1H.apply(HEAD + "7.2 (s, 1H), bizarre")
    assert not _decimal_flags(result)
    assert _flags(result)


# --- IR : plages --------------------------------------------------------------------------

NU = "\u03bd\u0303"
RULE_IR = IrRule()


def test_ir_range_is_recognized_and_written_with_spaced_en_dash():
    result = RULE_IR.apply("IR (ATR) 2990 (m), 3300-2400 (m), 1725 (s) cm-1")
    assert result.new_text == (
        f"IR (ATR): {NU}(cm⁻¹) = 3300{NB}–{NB}2400 (m), 2990 (m), 1725 (s)"
    )
    assert not _flags(result)


def test_ir_range_output_is_idempotent():
    text = f"IR (ATR): {NU}(cm⁻¹) = 3300{NB}–{NB}2400 (m), 2990 (m), 1725 (s)"
    result = RULE_IR.apply(text)
    assert result.new_text == text
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_ir_range_is_sorted_on_its_upper_bound():
    result = RULE_IR.apply("IR (ATR) 1700, 3000-2500, 3400 cm-1")
    assert result.new_text.endswith(f"3400, 3000{NB}–{NB}2500, 1700")


def test_ir_range_values_are_not_changed():
    result = RULE_IR.apply("IR (ATR) 2400-3300 (br) cm-1")  # écrite à l'envers : conservée
    assert f"2400{NB}–{NB}3300 (br)" in result.new_text


# --- HRMS : tolérance absolue et décimales ----------------------------------------------

HRMS = "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found {found}."


def test_absolute_tolerance_default_is_0_003():
    assert RmnConfig().hrms_abs_tolerance == 0.003


def test_absolute_gap_above_tolerance_is_flagged_even_if_ppm_is_loose():
    cfg.set_config(RmnConfig(hrms_ppm_tolerance=100.0))
    result = HrmsRule().apply(HRMS.format(found="165.0950"))
    messages = [m for m in _flags(result) if "absolu" in m]
    assert len(messages) == 1 and "0.0040 Da" in messages[0]
    assert "165.0950" in result.new_text  # masse jamais modifiée


def test_absolute_gap_within_tolerance_is_not_flagged():
    cfg.set_config(RmnConfig(hrms_ppm_tolerance=100.0))
    result = HrmsRule().apply(HRMS.format(found="165.0930"))
    assert not [m for m in _flags(result) if "absolu" in m]
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_absolute_tolerance_is_configurable():
    cfg.set_config(RmnConfig(hrms_ppm_tolerance=100.0, hrms_abs_tolerance=0.01))
    result = HrmsRule().apply(HRMS.format(found="165.0950"))
    assert not [m for m in _flags(result) if "absolu" in m]


def test_hrms_abs_tolerance_config_roundtrip_and_validation():
    data = cfg.config_to_dict(RmnConfig(hrms_abs_tolerance=0.005))
    assert cfg.config_from_dict(data).hrms_abs_tolerance == 0.005
    for bad in (0, -1, "0.003", None, True):
        assert cfg.config_from_dict({"hrms_abs_tolerance": bad}).hrms_abs_tolerance == 0.003


def test_low_mass_needs_four_decimals():
    result = HrmsRule().apply(
        "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.091; Found 165.0912."
    )
    messages = _decimal_flags(result)
    assert len(messages) == 1 and "calculée 165.091 (3)" in messages[0]
    assert "165.091;" in result.new_text  # masse conservée


def test_five_decimals_are_flagged_for_low_mass():
    result = HrmsRule().apply(
        "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.09100; Found 165.09120."
    )
    assert len(_decimal_flags(result)) == 1


def test_high_mass_is_not_checked_for_decimals():
    result = HrmsRule().apply(
        "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₃₀H₅₁O₁₀ 571.35; Found 571.35."
    )
    assert not _decimal_flags(result)


def test_decimal_flag_in_full_chain():
    report = process_texts(
        ["HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.091; Found 165.0912."],
        build_registry(),
    )
    assert any("décimales" in a.message for a in report.paragraphs[0].actions)


# --- IR : unité / symbole ajoutés = correction explicite dans le rapport ---------------

def _corrections(result):
    return [a.message for a in result.actions if a.kind == ActionKind.CORRECTED]


def test_ir_missing_unit_is_reported_explicitly():
    result = RULE_IR.apply("IR (neat) ν: 2966, 2943, 1705, 827.")
    assert any(m.startswith("Unité des bandes IR absente : ") for m in _corrections(result))
    assert result.new_text.endswith("(cm⁻¹) = 2966, 2943, 1705, 827.")


def test_ir_missing_symbol_is_reported_explicitly():
    result = RULE_IR.apply("IR (neat) 3420, 1715 cm-1")
    assert any(m.startswith("Symbole du nombre d'onde absent : ") for m in _corrections(result))
    assert not any(m.startswith("Unité") for m in _corrections(result))


@pytest.mark.parametrize("text", [
    "IR (ATR) ν̃ 3420, 1715 cm-1",
    "IR (ATR, cm-1): ν̃ 3420, 1715",
    "IR (ATR) νmax/cm-1 3420, 1715",
])
def test_ir_present_unit_is_not_reported_missing(text):
    assert not any(m.startswith("Unité") for m in _corrections(RULE_IR.apply(text)))
