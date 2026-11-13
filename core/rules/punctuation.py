"""Règle Ponctuation : espaces avant ``:`` / ``;`` et ponctuation doublée.

Corrections (forme seulement, aucune donnée touchée) :

- les espaces (ordinaires ou insécables) placés AVANT ``:`` ou ``;`` sont
  supprimés (``HRMS (ESI) : 165`` -> ``HRMS (ESI): 165``) ;
- une ponctuation doublée est réduite à un seul signe : ``,,`` -> ``,``,
  ``;;`` -> ``;``, ``::`` -> ``:``, ``..`` -> ``.``. Les points de suspension
  (``...``) et les nombres ne sont pas touchés.

Signalé sans modification (FLAGGED) : deux ponctuations différentes collées
(``,;``, ``;,``, ``:,``, ``,:``, ``:;``, ``;:``, ``,.``), car la bonne
ponctuation ne peut pas être devinée.

La règle ne s'applique (et n'est donc évaluée) que s'il y a quelque chose à
corriger ou à signaler : appliquée à tous les paragraphes, une règle « toujours
conforme » gonflerait le score d'évaluation (même dérogation que l'ordre des
analyses). La sortie est idempotente.
"""

from __future__ import annotations

import re
from typing import List

from core.rules.base import Action, ActionKind, Rule, RuleResult

# Espace (ordinaire, insécable, fine insécable) avant ``:`` ou ``;``.
_SPACE_BEFORE_RE = re.compile(r"[ \u00a0\u202f]+(?=[:;])")

# Ponctuation doublée : ``,,`` ``;;`` ``::`` (2 signes ou plus) et ``..``
# EXACTEMENT deux points (``...`` = points de suspension, conservés).
_DOUBLED_RE = re.compile(r"([,;:])\1+|(?<!\.)\.\.(?!\.)")

# Deux ponctuations différentes collées (hors ``.`` suivi d'une autre, qui
# suit souvent une abréviation : ``etc.,``).
_MIXED_RE = re.compile(r"[,;:][,;:.]")


def _problems(text: str) -> tuple[list, list, list]:
    """``(espaces, doublons, mélanges)`` : listes de correspondances."""
    spaces = list(_SPACE_BEFORE_RE.finditer(text))
    doubled = list(_DOUBLED_RE.finditer(text))
    cleaned = _fix(text)
    mixed = [m for m in _MIXED_RE.finditer(cleaned) if m.group(0)[0] != m.group(0)[1]]
    return spaces, doubled, mixed


def _fix(text: str) -> str:
    text = _SPACE_BEFORE_RE.sub("", text)
    return _DOUBLED_RE.sub(lambda m: m.group(0)[0], text)


class PunctuationRule(Rule):
    name = "Ponctuation"
    description = (
        "Supprime les espaces avant « : » et « ; » et réduit la ponctuation "
        "doublée (,, ;; :: ..) ; deux ponctuations différentes collées sont "
        "seulement signalées."
    )

    def applies(self, paragraph_text: str) -> bool:
        spaces, doubled, mixed = _problems(paragraph_text)
        return bool(spaces or doubled or mixed)

    def apply(self, paragraph_text: str) -> RuleResult:
        spaces, doubled, mixed = _problems(paragraph_text)
        new_text = _fix(paragraph_text)
        actions: List[Action] = []

        if spaces:
            samples = _samples(
                paragraph_text, [(m.start(), m.end() + 1) for m in spaces]
            )
            actions.append(Action(
                ActionKind.CORRECTED,
                f"Espace supprimée avant deux-points ou point-virgule : {samples}",
                self.name,
            ))
        if doubled:
            samples = _samples(paragraph_text, [(m.start(), m.end()) for m in doubled])
            actions.append(Action(
                ActionKind.CORRECTED,
                f"Ponctuation doublée réduite : {samples}",
                self.name,
            ))
        if mixed:
            found = [m.group(0) for m in mixed]
            actions.append(Action(
                ActionKind.FLAGGED,
                "Deux ponctuations différentes collées, à vérifier : "
                + ", ".join(f"« {s} »" for s in dict.fromkeys(found)),
                self.name,
                tuple(dict.fromkeys(found)),
            ))
        if not actions:
            return RuleResult(
                new_text=paragraph_text,
                actions=[Action(ActionKind.UNCHANGED, "Ponctuation déjà conforme.", self.name)],
            )
        return RuleResult(new_text=new_text, actions=actions)


def _samples(text: str, spans: List[tuple], limit: int = 3) -> str:
    """Extraits courts (mot précédent + ponctuation) pour le message."""
    out: List[str] = []
    for start, end in spans[:limit]:
        left = text[max(0, start - 12):start].split()
        word = left[-1] if left and not text[start - 1:start].isspace() else ""
        out.append(f"« {word}{text[start:end]} »".replace("\u00a0", " "))
    more = f" (+{len(spans) - limit})" if len(spans) > limit else ""
    return ", ".join(out) + more
