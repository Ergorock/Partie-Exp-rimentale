"""Règle de standardisation des sections ``13C NMR`` (sortie stylisée).

Format cible (exposant Unicode, gras sur le label seul, delta
italique)::

    ¹³C NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>

Spécificités du carbone : signaux généralement découplés, donnés par leur
déplacement puis une attribution optionnelle entre parenthèses (``Cq``,
``CH₂``, ``C=O``…) ; multiplicité et ``J`` conservées en cas de couplage
(ex. C–F). Reconnaît ``13C NMR`` et ``13C RMN`` (mot d'entrée conservé). Toute
la logique de section est dans ``nmr_section``.
"""

from __future__ import annotations

from core.rules import nmr_common
from core.rules.nmr_section import NmrSectionRule


class ThirteenCNmrRule(NmrSectionRule):
    """Valide et standardise les sections ``13C NMR`` (sortie stylisée)."""

    name = "13C NMR"
    description = (
        "Format stylisé : label ¹³C exposant Unicode (NMR/RMN conservé) en "
        "gras, parenthèse (MHz, solvant, K), δ en italique, attribution () "
        "optionnelle, multiplicité et J conservées si couplage, signaux triés "
        "du plus grand au plus petit (si tous parsables)."
    )
    nucleus = "13C"

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_13c(signal)
