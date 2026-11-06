"""Vérifie qu'une nouvelle règle est bien détectée par le registre (Task 6)."""

from core.rules.nmr_13c import ThirteenCNmrRule
from core.rules.registry import RuleRegistry


def test_new_rule_is_discovered_by_registry():
    registry = RuleRegistry()
    registry.register(ThirteenCNmrRule())

    # La règle s'applique à un paragraphe 13C NMR...
    assert registry.rules_for("13C NMR (100 MHz, CDCl3, 298 K)") != []
    # ...et ignore les autres (dont 1H NMR).
    assert registry.rules_for("1H NMR (400 MHz, CDCl3, 298 K)") == []


def test_new_rule_conforms_to_interface():
    rule = ThirteenCNmrRule()
    result = rule.apply("13C NMR (100 MHz, CDCl3, 298 K)")
    assert result.new_text == "13C NMR (100 MHz, CDCl3, 298 K)"
    assert result.actions  # produit au moins une action
