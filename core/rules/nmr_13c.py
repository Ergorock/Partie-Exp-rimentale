"""Règle de standardisation des paragraphes ``13C NMR`` (sortie stylisée).

Format cible (exposant Unicode, gras sur le label + la parenthèse, delta
italique)::

    ¹³C NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>

Symétrique de la règle ``1H NMR`` et réutilise ``nmr_common``. Spécificités du
carbone :

- les signaux sont généralement découplés (singulets) : on indique le
  déplacement chimique (une décimale) puis une attribution optionnelle entre
  parenthèses (``Cq``, ``CH``, ``CH₂``, ``CH₃``, ``C=O``…) ;
- la constante de couplage ``J`` est conservée si un couplage est présent
  (ex. couplage F/P) ;
- même tri (du plus grand au plus petit) et même règle de sûreté (FLAGGED sans
  réordonnancement si un signal n'est pas parsable).

Décisions utilisateur appliquées : le mot d'entrée est conservé (``13C NMR`` ->
``¹³C NMR``, ``13C RMN`` -> ``¹³C RMN``) ; la règle reconnaît les deux formes en
entrée ; elle ne traite QUE son segment de section.
"""

from __future__ import annotations

import re

from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment
from core.rules import nmr_common

# Préfixe reconnu : '13C NMR' OU '13C RMN', insensible à la casse / aux espaces.
_PREFIX_RE = re.compile(r"^\s*13C\s*(?:NMR|RMN)\b", re.IGNORECASE)

# Structure d'un segment 13C : label + texte avant parenthèse + parenthèse + reste.
_STRUCTURE_RE = re.compile(
    r"^(?P<label>13C\s*(?:NMR|RMN))\b(?P<between>[^(]*)\((?P<inside>[^)]*)\)(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)


def _looks_like_frequency(segment: str) -> bool:
    """Indique si un segment ressemble à une fréquence RMN (nombre + MHz)."""
    return bool(re.search(r"\d+(?:\.\d+)?\s*MHz", segment, re.IGNORECASE))


_KIND_MAP = {
    "corrected": ActionKind.CORRECTED,
    "placeholder": ActionKind.PLACEHOLDER,
    "flagged": ActionKind.FLAGGED,
}


class ThirteenCNmrRule(Rule):
    """Valide et standardise les paragraphes ``13C NMR`` (sortie stylisée)."""

    name = "13C NMR"
    description = (
        "Format stylisé : label ¹³C exposant Unicode (NMR/RMN conservé) et "
        "parenthèse (MHz, solvant, K) en gras, δ en italique, déplacements à "
        "une décimale avec attribution () optionnelle, J conservée si couplage, "
        "signaux triés du plus grand au plus petit (si tous parsables)."
    )

    def applies(self, paragraph_text: str) -> bool:
        return bool(_PREFIX_RE.match(paragraph_text))

    def apply(self, paragraph_text: str) -> RuleResult:
        text = nmr_common.normalize_spaces(paragraph_text)

        # 1) Délimiter le segment 13C (du label au prochain label de section).
        # Positions identiques entre text et paragraph_text (normalisation 1:1) :
        # on garde la sous-chaîne originale pour replaced_text.
        seg_start, seg_end = nmr_common.section_span(text, 0)
        segment = text[seg_start:seg_end]
        original_segment = paragraph_text[seg_start:seg_end]
        prefix = text[:seg_start]
        suffix = text[seg_end:]

        match = _STRUCTURE_RE.match(segment)
        if not match:
            return RuleResult(
                new_text=paragraph_text,
                actions=[
                    Action(
                        ActionKind.FLAGGED,
                        "Aucune parenthèse exploitable après '13C NMR' : "
                        "vérification manuelle requise.",
                        self.name,
                    )
                ],
            )

        label = match.group("label")
        between = match.group("between")
        inside = match.group("inside")
        rest = match.group("rest")

        actions: list[Action] = []

        # 2) Fréquence placée hors de la parenthèse -> on la déplace à l'intérieur.
        if _looks_like_frequency(between):
            freq_segment = between.strip()
            inside = f"{freq_segment}, {inside.strip()}"
            actions.append(
                Action(
                    ActionKind.CORRECTED,
                    "Fréquence déplacée à l'intérieur de la parenthèse.",
                    self.name,
                )
            )

        # 3) Normaliser la parenthèse à trois éléments.
        paren = nmr_common.normalize_parenthesis(inside)
        for kind, message in paren.actions:
            actions.append(Action(_KIND_MAP[kind], message, self.name))

        # 4) Label stylisé (exposant Unicode, mot d'entrée NMR/RMN conservé).
        styled_label = nmr_common.superscript_label(label)
        label_paren = f"{styled_label} ({paren.text})"

        # 5) Isoler et formater les signaux (après le delta).
        body = nmr_common.split_delta_body(rest)
        signals_text = ""
        if body is not None:
            signals, all_parsable = nmr_common.parse_signals(body)
            if not all_parsable:
                actions.append(
                    Action(
                        ActionKind.FLAGGED,
                        "Un ou plusieurs signaux n'ont pas pu être analysés : "
                        "aucun réordonnancement effectué, vérification manuelle.",
                        self.name,
                    )
                )
            ordered = nmr_common.sort_signals(signals, all_parsable)
            signals_text = ", ".join(nmr_common.format_signal_13c(s) for s in ordered)
        else:
            actions.append(
                Action(
                    ActionKind.FLAGGED,
                    "Liste de signaux introuvable (symbole δ absent) : "
                    "vérification manuelle requise.",
                    self.name,
                )
            )

        # 6) Reconstruire le segment reformaté et le paragraphe complet.
        segments = [
            StyledSegment(label_paren, bold=True),
            StyledSegment(" "),
            StyledSegment(nmr_common.DELTA, italic=True),
        ]
        segment_plain = f"{label_paren} {nmr_common.DELTA}"
        if signals_text:
            segments.append(StyledSegment(f" {signals_text}"))
            segment_plain += f" {signals_text}"

        new_text = f"{prefix}{segment_plain}{suffix}"

        if new_text == paragraph_text:
            return RuleResult(
                new_text=paragraph_text,
                actions=[
                    Action(ActionKind.UNCHANGED, "Paragraphe déjà conforme.", self.name)
                ],
            )

        if not actions:
            actions.append(
                Action(ActionKind.CORRECTED, "Paragraphe reformaté.", self.name)
            )

        return RuleResult(
            new_text=new_text,
            actions=actions,
            segments=segments,
            replaced_text=original_segment,
        )
