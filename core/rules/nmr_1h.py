"""Règle de standardisation des paragraphes ``1H NMR`` (sortie stylisée).

Format cible (exposant Unicode, gras sur le label + la parenthèse, delta
italique)::

    ¹H NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>

Décisions utilisateur appliquées :

- le mot d'entrée est conservé (``1H NMR`` -> ``¹H NMR``, ``1H RMN`` -> ``¹H RMN``) ;
- la parenthèse comporte trois éléments (fréquence MHz, solvant, température K)
  avec ``[??? K]`` si la température manque ;
- la règle ne traite QUE son segment de section (du label ``1H NMR`` jusqu'au
  prochain label de section RMN), laissant le reste du paragraphe intact ;
- les signaux sont triés du déplacement le plus grand au plus petit uniquement
  si tous sont parsables ; sinon aucun réordonnancement et une action FLAGGED.
"""

from __future__ import annotations

import re

from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment
from core.rules import nmr_common

# Préfixe reconnu en tête de paragraphe (insensible à la casse / aux espaces).
# Le mot d'entrée peut être 'NMR' ou 'RMN' (conservé tel quel en sortie).
_PREFIX_RE = re.compile(r"^\s*1H\s*(?:NMR|RMN)\b", re.IGNORECASE)

# Structure d'un segment 1H : label + texte avant parenthèse + parenthèse + reste.
_STRUCTURE_RE = re.compile(
    r"^(?P<label>1H\s*(?:NMR|RMN))\b(?P<between>[^(]*)\((?P<inside>[^)]*)\)(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _looks_like_frequency(segment: str) -> bool:
    """Indique si un segment ressemble à une fréquence RMN (nombre + MHz)."""
    return bool(re.search(r"\d+(?:\.\d+)?\s*MHz", segment, re.IGNORECASE))


_KIND_MAP = {
    "corrected": ActionKind.CORRECTED,
    "placeholder": ActionKind.PLACEHOLDER,
    "flagged": ActionKind.FLAGGED,
}


class OneHNmrRule(Rule):
    """Valide et standardise les paragraphes ``1H NMR`` (sortie stylisée)."""

    name = "1H NMR"
    description = (
        "Format stylisé : label ¹H exposant Unicode (NMR/RMN conservé) et "
        "parenthèse (MHz, solvant, K) en gras, δ en italique, signaux triés du "
        "plus grand au plus petit (si tous parsables), [??? K] si température "
        "absente."
    )

    def applies(self, paragraph_text: str) -> bool:
        return bool(_PREFIX_RE.match(paragraph_text))

    def apply(self, paragraph_text: str) -> RuleResult:
        from core.config import get_config

        config = get_config()
        text = nmr_common.normalize_spaces(paragraph_text)

        # 1) Délimiter le segment 1H (du label au prochain label de section).
        # normalize_spaces est un remplacement caractère par caractère : les
        # positions dans ``text`` et ``paragraph_text`` coïncident. On garde la
        # sous-chaîne ORIGINALE (avec ses \xa0) comme replaced_text pour que
        # docx_io.apply_styled_edit la retrouve dans le paragraphe réel.
        seg_start, seg_end = nmr_common.section_span(text, 0)
        segment = text[seg_start:seg_end]
        original_segment = paragraph_text[seg_start:seg_end]
        prefix = text[:seg_start]
        suffix = text[seg_end:]

        match = _STRUCTURE_RE.match(segment)
        if not match:
            # Pas de parenthèse exploitable : impossible de corriger sûrement.
            return RuleResult(
                new_text=paragraph_text,
                actions=[
                    Action(
                        ActionKind.FLAGGED,
                        "Aucune parenthèse exploitable après '1H NMR' : "
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
        paren = nmr_common.normalize_parenthesis(inside, config)
        for kind, message in paren.actions:
            actions.append(Action(_KIND_MAP[kind], message, self.name))

        # 4) Construire le label stylisé (exposant Unicode, mot d'entrée conservé).
        styled_label = nmr_common.superscript_label(label)
        label_paren = f"{styled_label} ({paren.text})"

        # 5) Isoler et formater les signaux (après le delta).
        body = nmr_common.split_delta_body(rest)
        signals_text = ""
        if body is not None:
            signals, all_parsable = nmr_common.parse_signals(body, config)
            if not all_parsable:
                actions.append(
                    Action(
                        ActionKind.FLAGGED,
                        "Un ou plusieurs signaux n'ont pas pu être analysés : "
                        "aucun réordonnancement effectué, vérification manuelle.",
                        self.name,
                    )
                )
            ordered = nmr_common.sort_signals(signals, all_parsable, config)
            signals_text = ", ".join(nmr_common.format_signal_1h(s) for s in ordered)
        else:
            # Pas de delta/liste de signaux : on signale sans inventer de chimie.
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
            StyledSegment(label_paren, bold=config.bold_label),
            StyledSegment(" "),
            StyledSegment(nmr_common.DELTA, italic=config.italic_delta),
        ]
        segment_plain = f"{label_paren} {nmr_common.DELTA}"
        if signals_text:
            segments.append(StyledSegment(f" {signals_text}"))
            segment_plain += f" {signals_text}"

        # Réinsère l'espace séparateur perdu avant une section suivante collée.
        separator = nmr_common.section_separator(original_segment, suffix)
        if separator:
            segments.append(StyledSegment(separator))
            segment_plain += separator

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
