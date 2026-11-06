"""Squelette de règle ``13C NMR`` (à compléter).

Fournit un point de départ conforme à l'interface ``Rule`` et démontre
l'extensibilité du moteur. La logique de validation/correction reste à
implémenter ; pour l'instant la règle ne modifie rien et marque le paragraphe
comme « à vérifier » afin de ne pas laisser croire qu'il a été standardisé.
"""

from __future__ import annotations

import re

from core.rules.base import Action, ActionKind, Rule, RuleResult

_PREFIX_RE = re.compile(r"^\s*13C\s*NMR\b", re.IGNORECASE)


class ThirteenCNmrRule(Rule):
    """Point de départ pour la standardisation des paragraphes ``13C NMR``."""

    name = "13C NMR"
    description = "Squelette (non implémenté) : signale les paragraphes 13C NMR."

    def applies(self, paragraph_text: str) -> bool:
        return bool(_PREFIX_RE.match(paragraph_text))

    def apply(self, paragraph_text: str) -> RuleResult:
        # TODO: implémenter la validation/correction du format 13C NMR.
        return RuleResult(
            new_text=paragraph_text,
            actions=[
                Action(
                    ActionKind.FLAGGED,
                    "Règle 13C NMR non encore implémentée : vérification manuelle.",
                    self.name,
                )
            ],
        )
