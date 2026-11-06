"""Tests de la règle 1H NMR (Task 3)."""

from core.rules.base import ActionKind
from core.rules.nmr_1h import OneHNmrRule

RULE = OneHNmrRule()


def test_applies_to_1h_nmr_paragraphs():
    assert RULE.applies("1H NMR (400 MHz, CDCl3, 298 K) δ ...") is True
    assert RULE.applies("  1H NMR (400 MHz, CDCl3, 298 K)") is True


def test_does_not_apply_to_other_paragraphs():
    assert RULE.applies("13C NMR (100 MHz, CDCl3, 298 K)") is False
    assert RULE.applies("A random experimental paragraph") is False


def test_conforming_paragraph_is_unchanged():
    text = "1H NMR (400.18 MHz, DMF-d7, 298 K): δ (ppm) = 9.18 (dd, 2H)"
    result = RULE.apply(text)
    assert result.new_text == text
    assert result.changed is False
    assert result.actions[0].kind == ActionKind.UNCHANGED


def test_missing_space_before_mhz_is_corrected():
    text = "1H NMR (400.18MHz, DMF-d7, 298 K): δ (ppm) = 9.18"
    result = RULE.apply(text)
    assert "400.18 MHz" in result.new_text
    assert result.changed is True
    assert any(a.kind == ActionKind.CORRECTED for a in result.actions)


def test_temperature_without_kelvin_unit_is_corrected():
    # Cas réel du fichier exemple : '298 ' sans 'K'
    text = "1H NMR (400.18 MHz, DMF-d7, 298 ): δ (ppm) = 9.18"
    result = RULE.apply(text)
    assert "298 K" in result.new_text
    assert result.changed is True
    assert any(a.kind == ActionKind.CORRECTED for a in result.actions)


def test_temperature_number_only_gets_kelvin_unit():
    text = "1H NMR (400 MHz, CDCl3, 298): δ (ppm) = 1.0"
    result = RULE.apply(text)
    assert "298 K" in result.new_text
    assert any(a.kind == ActionKind.CORRECTED for a in result.actions)


def test_missing_temperature_inserts_placeholder():
    text = "1H NMR (400 MHz, CDCl3): δ (ppm) = 1.0"
    result = RULE.apply(text)
    assert "[??? K]" in result.new_text
    assert any(a.kind == ActionKind.PLACEHOLDER for a in result.actions)


def test_frequency_outside_parenthesis_is_moved_inside():
    text = "1H NMR 400 MHz (CDCl3, 298 K): δ (ppm) = 1.0"
    result = RULE.apply(text)
    assert "(400 MHz, CDCl3, 298 K)" in result.new_text
    assert result.changed is True
    assert any(a.kind == ActionKind.CORRECTED for a in result.actions)


def test_no_parenthesis_is_flagged():
    text = "1H NMR 400 MHz CDCl3 298 K δ = 1.0"
    result = RULE.apply(text)
    # Impossible de corriger de façon sûre -> signalé
    assert any(
        a.kind in (ActionKind.FLAGGED, ActionKind.PLACEHOLDER) for a in result.actions
    )
