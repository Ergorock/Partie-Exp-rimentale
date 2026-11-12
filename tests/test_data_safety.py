"""Tests de non-régression : aucune perte de donnée silencieuse.

Chaque cas reproduit une entrée réaliste qui, avant correction, faisait
disparaître ou altérer une donnée chimique sans signalement. Règle de sûreté :
un signal qu'on ne sait pas reconstruire sans perte n'est pas réécrit, et une
action FLAGGED est émise.
"""

import pytest

from core import config as cfg
from core.config import RmnConfig
from core.rules.base import ActionKind
from core.rules.nmr_13c import ThirteenCNmrRule
from core.rules.nmr_1h import OneHNmrRule

RULE_1H = OneHNmrRule()
RULE_13C = ThirteenCNmrRule()


@pytest.fixture(autouse=True)
def _default_config():
    cfg.set_config(RmnConfig())
    yield
    cfg.reset_config()


def _flagged(result) -> bool:
    return any(a.kind == ActionKind.FLAGGED for a in result.actions)


# --- Ponctuation finale -------------------------------------------------------

def test_trailing_period_keeps_last_signal_parenthesis():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H), 1.20 (t, J = 7.1 Hz, 3H)."
    result = RULE_1H.apply(text)
    assert result.new_text.endswith("1.20 (t, J = 7.1 Hz, 3\xa0H).")
    assert not _flagged(result)


def test_trailing_period_with_sorting():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 1.20 (t, 3H), 7.26 (s, 1H)."
    result = RULE_1H.apply(text)
    assert result.new_text.endswith("δ (ppm) = 7.26 (s, 1\xa0H), 1.20 (t, 3\xa0H).")


def test_trailing_period_13c():
    text = "13C NMR (101 MHz, CDCl3, 298 K) δ 21.7 (CH3), 166.4 (C=O)."
    result = RULE_13C.apply(text)
    assert result.new_text.endswith("δ (ppm) = 166.4 (C=O), 21.7 (CH₃).")


# --- Texte hors parenthèse ----------------------------------------------------

def test_text_after_parenthesis_is_not_dropped():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 3.50 (br s, 1H) overlapped, 1.2 (s, 3H)"
    result = RULE_1H.apply(text)
    assert "3.50 (br s, 1H) overlapped" in result.new_text
    assert _flagged(result)


def test_text_without_parenthesis_is_not_dropped():
    text = "1H NMR (400 MHz, CDCl3, 298 K) δ 1.2 (s, 3H), 3.50 br, 7.2 (s, 1H)"
    result = RULE_1H.apply(text)
    assert "3.50 br" in result.new_text
    assert _flagged(result)


def test_nested_parenthesis_is_not_dropped():
    text = "13C NMR (101 MHz, CDCl3, 298 K) δ 25.1 (CH(CH3)2), 130.0"
    result = RULE_13C.apply(text)
    assert "25.1 (CH(CH3)2)" in result.new_text
    assert _flagged(result)


def test_unparsable_body_is_kept_verbatim():
    body = "2.3 (s, 3H), bizarre, 7.5 (m, 1H)"
    result = RULE_1H.apply(f"1H NMR (400 MHz, CDCl3, 298 K) δ {body}")
    assert result.new_text.endswith(f"δ (ppm) = {body}")


# --- Virgule décimale ---------------------------------------------------------

def test_decimal_comma_is_flagged_and_kept():
    body = "7,26 (s, 1H), 1,20 (t, 3H)"
    result = RULE_1H.apply(f"1H RMN (400 MHz, CDCl3, 298 K) δ {body}")
    assert result.new_text.endswith(f"δ (ppm) = {body}")
    assert _flagged(result)


# --- Multiplicité 13C ---------------------------------------------------------

def test_13c_multiplicity_is_kept():
    text = "13C NMR (101 MHz, CDCl3, 298 K) δ 115.0 (d, J = 21 Hz), 162.3 (d, J = 245 Hz)"
    result = RULE_13C.apply(text)
    assert "162.3 (d, J = 245 Hz), 115.0 (d, J = 21 Hz)" in result.new_text


# --- Unité de température -----------------------------------------------------

def test_explicit_kelvin_not_relabelled_as_celsius():
    cfg.set_config(RmnConfig(temperature_unit="°C"))
    result = RULE_1H.apply("1H NMR (400 MHz, CDCl3, 298 K) δ 1.0 (s, 3H)")
    assert "298 K" in result.new_text
    assert "298 °C" not in result.new_text
    assert _flagged(result)


def test_explicit_celsius_not_relabelled_as_kelvin():
    result = RULE_1H.apply("1H NMR (400 MHz, CDCl3, 25 °C) δ 1.0 (s, 3H)")
    assert "25 °C" in result.new_text
    assert "25 K" not in result.new_text
    assert _flagged(result)


def test_matching_unit_is_still_normalized():
    result = RULE_1H.apply("1H NMR (400 MHz, CDCl3, 298K) δ 1.00 (s, 3H)")
    assert "298 K" in result.new_text
    assert not _flagged(result)


# --- IR : jamais de valeur modifiée ni de texte supprimé --------------------------------

@pytest.mark.parametrize(
    "text",
    [
        "IR (ATR) 3420, 1715.5, 1600 cm-1",      # bande décimale
        "IR (ATR) 3420, 1715,5 cm-1",            # virgule décimale
        "IR (ATR) 3420 large, 1715 cm-1",        # texte hors parenthèse
        "IR (ATR) 3420 (br (OH)), 1715 cm-1",    # parenthèse imbriquée
        "IR 3420, 1715 cm-1",                    # méthode absente
        "IR (ATR) 3420, 1715 cm-1. Voir texte.",  # texte final inconnu
    ],
)
def test_ir_unsafe_entry_is_kept_verbatim_and_flagged(text):
    from core.rules.ir import IrRule

    result = IrRule().apply(text)
    assert result.new_text == text
    assert result.segments is None
    assert _flagged(result)
