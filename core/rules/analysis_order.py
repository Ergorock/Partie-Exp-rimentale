"""Règle « Ordre des analyses » : contrôle de la séquence dans un paragraphe.

Guide LCMCE (6.3) : Rf ; m.p. ou b.p. ; 1H ; 13C ; autres RMN ; IR ; UV/Vis ;
MS ; HRMS ; analyse élémentaire.

La règle ne MODIFIE jamais le texte (aucun déplacement automatique) : elle
signale (FLAGGED) un paragraphe qui contient plusieurs analyses dans un ordre
différent. Elle ne regarde que l'intérieur d'un paragraphe : l'ordre entre
paragraphes successifs n'est pas contrôlé (on ne sait pas où un composé
s'arrête et où le suivant commence).

La règle ne s'applique (et n'est donc évaluée) que si l'ordre est
incorrect : un paragraphe bien ordonné ne produit aucun élément en mode
évaluation (sinon l'ordre correct gonflerait artificiellement le score).

Un label n'est retenu que s'il ouvre une vraie entrée (parenthèse, ``:``, ``=``
ou valeur juste après) : une mention en prose est ignorée.
"""

from __future__ import annotations

import re
from typing import List, Tuple

from core.rules import nmr_common
from core.rules.base import Action, ActionKind, Rule, RuleResult

# (rang, nom affiché, motif du label). Le motif exige une entrée derrière lui.
_ENTRY = r"(?=\s*[(:=]|\s*\d)"
_ANALYSES: List[Tuple[int, str, "re.Pattern[str]"]] = [
    (1, "Rf", re.compile(r"(?<![A-Za-z])R\s*[._]?\s*f(?![A-Za-z])\.?" + _ENTRY)),
    (2, "m.p. / b.p.", re.compile(
        r"(?<![A-Za-z])(?:[mb]\.?\s?p(?![A-Za-z])\.?|melting\s+point|boiling\s+point)"
        r"(?=\s*[:=]?\s*\d)", re.IGNORECASE)),
    (6, "IR", re.compile(r"(?<![A-Za-z])IR(?![A-Za-z])" + _ENTRY)),
    (7, "UV/Vis", re.compile(r"(?<![A-Za-z])UV\s?[\-/–]?\s?[Vv]is(?![A-Za-z])" + _ENTRY)),
    (8, "MS", re.compile(r"(?<![A-Za-z])MS(?![A-Za-z])" + _ENTRY)),
    (9, "HRMS", re.compile(r"(?<![A-Za-z])HRMS(?![A-Za-z])" + _ENTRY)),
    (10, "Analyse élémentaire", re.compile(
        r"(?<![A-Za-z])(?:Anal\.|Elemental\s+analysis)", re.IGNORECASE)),
]
_ORDER_TEXT = (
    "Rf ; m.p./b.p. ; 1H ; 13C ; autres RMN ; IR ; UV/Vis ; MS ; HRMS ; "
    "analyse élémentaire"
)


def find_analyses(text: str) -> List[Tuple[int, int, str, int]]:
    """Analyses du texte dans l'ordre du texte : ``(début, rang, nom, fin)``."""
    found: List[Tuple[int, int, str, int]] = []
    for rank, name, pattern in _ANALYSES:
        for match in pattern.finditer(text):
            found.append((match.start(), rank, name, match.end()))
    for match in nmr_common._SECTION_LABEL_RE.finditer(text):
        label = match.group(0)
        if not re.match(r"\s*\(", text[match.end():match.end() + 40] or "") and not re.match(
            r"\s*[:=]?\s*\d", text[match.end():match.end() + 40] or ""
        ):
            continue
        nucleus = re.sub(r"[\s\-–]*(?:NMR|RMN)$", "", label, flags=re.IGNORECASE)
        nucleus = re.sub(r"\{[^}]*\}", "", nucleus)
        plain = nucleus.translate(str.maketrans("⁰¹²³⁴⁵⁶⁷⁸⁹", "0123456789"))
        found.append((match.start(), 3 if plain == "1H" else 4 if plain == "13C" else 5,
                      f"{plain} NMR", match.end()))
    return sorted(found)


class AnalysisOrderRule(Rule):
    """Signale un paragraphe dont les analyses ne suivent pas l'ordre du guide."""

    name = "Ordre des analyses"
    description = (
        "Contrôle l'ordre Rf ; m.p./b.p. ; 1H ; 13C ; autres RMN ; IR ; UV/Vis ; "
        "MS ; HRMS ; analyse élémentaire dans un paragraphe. Ne déplace rien : "
        "signale seulement."
    )

    @staticmethod
    def _problems(paragraph_text: str) -> List[Tuple[str, str]]:
        """``(« B après A », label de B tel qu'écrit)`` pour chaque inversion."""
        text = nmr_common.normalize_spaces(paragraph_text)
        found = find_analyses(text)
        return [
            (f"{name_b} après {name_a}", paragraph_text[start_b:end_b])
            for (_, rank_a, name_a, _), (start_b, rank_b, name_b, end_b)
            in zip(found, found[1:])
            if rank_b < rank_a
        ]

    def applies(self, paragraph_text: str) -> bool:
        return bool(self._problems(paragraph_text))

    def apply(self, paragraph_text: str) -> RuleResult:
        problems = self._problems(paragraph_text)
        if not problems:
            return RuleResult(
                new_text=paragraph_text,
                actions=[Action(ActionKind.UNCHANGED, "Ordre des analyses conforme.", self.name)],
            )
        return RuleResult(
            new_text=paragraph_text,
            actions=[Action(
                ActionKind.FLAGGED,
                f"Ordre des analyses non conforme : {', '.join(p for p, _ in problems)} ; "
                f"ordre attendu {_ORDER_TEXT}. Texte laissé tel quel.",
                self.name,
                tuple(label for _, label in problems),
            )],
        )
