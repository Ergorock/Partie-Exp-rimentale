"""Tests du moteur de règles (Task 2)."""

from core.rules.base import Action, ActionKind, Rule, RuleResult
from core.rules.registry import RuleRegistry


class NoOpRule(Rule):
    """Règle de démonstration : s'applique aux paragraphes marqués 'DEMO'."""

    name = "no-op"

    def applies(self, paragraph_text: str) -> bool:
        return paragraph_text.strip().startswith("DEMO")

    def apply(self, paragraph_text: str) -> RuleResult:
        return RuleResult(
            new_text=paragraph_text,
            actions=[Action(ActionKind.UNCHANGED, "vu", self.name)],
        )


def test_registry_registers_and_lists():
    registry = RuleRegistry()
    rule = NoOpRule()
    registry.register(rule)
    assert registry.rules == [rule]


def test_rules_for_matches_only_targeted_paragraphs():
    registry = RuleRegistry()
    registry.register(NoOpRule())

    assert registry.rules_for("DEMO ceci est ciblé") != []
    assert registry.rules_for("autre paragraphe") == []


def test_apply_returns_result_with_actions():
    rule = NoOpRule()
    result = rule.apply("DEMO x")
    assert result.new_text == "DEMO x"
    assert result.actions[0].kind == ActionKind.UNCHANGED
    assert result.changed is False
