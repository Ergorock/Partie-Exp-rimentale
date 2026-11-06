"""Registre des règles de standardisation."""

from __future__ import annotations

from typing import List

from core.rules.base import Rule


class RuleRegistry:
    """Conteneur ordonné de règles.

    Les règles sont appliquées dans leur ordre d'enregistrement. Pour un
    paragraphe donné, ``rules_for`` retourne les règles qui s'y appliquent.
    """

    def __init__(self) -> None:
        self._rules: List[Rule] = []

    def register(self, rule: Rule) -> None:
        """Enregistre une règle."""
        self._rules.append(rule)

    @property
    def rules(self) -> List[Rule]:
        """Liste des règles enregistrées (ordre d'enregistrement)."""
        return list(self._rules)

    def rules_for(self, paragraph_text: str) -> List[Rule]:
        """Retourne les règles qui s'appliquent au paragraphe donné."""
        return [r for r in self._rules if r.applies(paragraph_text)]
