"""Règle de standardisation des sections ``1H NMR`` (sortie stylisée).

Format cible (exposant Unicode, gras sur le label seul, delta
italique)::

    ¹H NMR (<fréquence> MHz, <solvant>, <température> K) δ (ppm) = <signaux>

Signal 1H : déplacement, puis entre parenthèses multiplicité, J, intégration,
attribution. Toute la logique de section est dans ``nmr_section``.
"""

from __future__ import annotations

from core.rules import nmr_common
from core.rules.nmr_section import NmrSectionRule


class OneHNmrRule(NmrSectionRule):
    """Valide et standardise les sections ``1H NMR`` (sortie stylisée)."""

    name = "1H NMR"
    description = (
        "Format stylisé : label ¹H exposant Unicode (NMR/RMN conservé) en "
        "gras, parenthèse (MHz, solvant, K), δ en italique, signaux triés du "
        "plus grand au plus petit (si tous parsables), [??? K] si température "
        "absente."
    )
    nucleus = "1H"
    shift_decimals = 2  # δ du 1H : 2 décimales (3 tolérées)

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_1h(signal)
