"""Règles de standardisation des sections RMN hétéronucléaires (``19F``, ``31P``, ``11B``, ``29Si``).

Même format que ``1H NMR`` / ``13C NMR`` (exposant Unicode, gras sur le label
seul, δ en italique), avec découplage optionnel conservé
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
        "Format stylisé : label ¹⁹F (ou ¹⁹F{¹H}) exposant Unicode en gras, "
        "parenthèse (MHz, solvant, K), δ en italique, signaux triés du plus grand "
        "au plus petit (si tous parsables)."
    )
    nucleus = "19F"

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_1h(signal)


class ThirtyOnePNmrRule(NmrSectionRule):
    """Valide et standardise les sections ``31P NMR`` (sortie stylisée)."""

    name = "31P NMR"
    description = (
        "Format stylisé : label ³¹P (ou ³¹P{¹H}) exposant Unicode en gras, "
        "parenthèse (MHz, solvant, K), δ en italique, signaux triés du plus grand "
        "au plus petit (si tous parsables)."
    )
    nucleus = "31P"

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_13c(signal)

class ElevenBNmrRule(NmrSectionRule):
    """Valide et standardise les sections ``11B NMR`` (sortie stylisée)."""

    name = "11B NMR"
    description = (
        "Format stylisé : label ¹¹B (ou ¹¹B{¹H}) exposant Unicode en gras, "
        "parenthèse (MHz, solvant, K), δ (ppm) =, signaux triés du plus grand "
        "au plus petit (si tous parsables), 1 décimale attendue pour δ."
    )
    nucleus = "11B"

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_13c(signal)


class TwentyNineSiNmrRule(NmrSectionRule):
    """Valide et standardise les sections ``29Si NMR`` (sortie stylisée)."""

    name = "29Si NMR"
    description = (
        "Format stylisé : label ²⁹Si (ou ²⁹Si{¹H}) exposant Unicode en gras, "
        "parenthèse (MHz, solvant, K), δ (ppm) =, signaux triés du plus grand "
        "au plus petit (si tous parsables), 1 décimale attendue pour δ."
    )
    nucleus = "29Si"

    def format_signal(self, signal: nmr_common.Signal) -> str:
        return nmr_common.format_signal_13c(signal)
