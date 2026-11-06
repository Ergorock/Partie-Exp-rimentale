"""Moteur de règles modulaire.

Chaque type de paragraphe à standardiser (1H NMR, 13C NMR, HRMS, ...) est
implémenté comme une règle indépendante. Les règles sont enregistrées dans un
``RuleRegistry`` et appliquées par le processor aux paragraphes concernés.
"""

from core.rules.base import Action, Rule, RuleResult
from core.rules.registry import RuleRegistry

__all__ = ["Action", "Rule", "RuleResult", "RuleRegistry"]
