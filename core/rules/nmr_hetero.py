"""Règles de standardisation des sections RMN hétéronucléaires (``19F``, ``31P``).

Même format que ``1H NMR`` / ``13C NMR`` (exposant Unicode, gras sur le label
+ la parenthèse, δ en italique), avec découplage optionnel conservé
(``19F{1H} NMR`` -> ``¹⁹F{¹H} NMR``). Les signaux suivent le format générique :
déplacement, puis multiplicité, J, intégration (``3F``) et attribution entre
parenthèses. Toute la logique de section est dans ``nmr_section``.
"""

from __future__ import annotations

from core.rules import nmr_common
from core.rules.nmr_section import NmrSectionRule


class NineteenFNmrRule(NmrSectionRule):
    """Valide et standardise les sections ``19F NMR`` (sortie stylisée)."""

    name = "19F NMR"
    description = (
        "Format stylisé : label ¹⁹F (ou ¹⁹F{¹H}) exposant Unicode et parenthèse "
        "(MHz, solvant, K) en gras, δ en italique, signaux triés du plus grand "
        "au plus petit (si tous parsables)."
    )
    nucleus = "19F"

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_1h(signal)


class ThirtyOnePNmrRule(NmrSectionRule):
    """Valide et standardise les sections ``31P NMR`` (sortie stylisée)."""

    name = "31P NMR"
    description = (
        "Format stylisé : label ³¹P (ou ³¹P{¹H}) exposant Unicode et parenthèse "
        "(MHz, solvant, K) en gras, δ en italique, signaux triés du plus grand "
        "au plus petit (si tous parsables)."
    )
    nucleus = "31P"

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_13c(signal)
