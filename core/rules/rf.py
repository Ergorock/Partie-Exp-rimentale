"""Règle de standardisation des entrées ``Rf`` (sortie stylisée).

Format cible (guide LCMCE)::

    Rf = 0.38 (SiO₂; heptane/CH₂Cl₂ 1:1)

- label ``Rf`` en gras (``config.bold_label``), le **f en indice Word** (une des
  trois seules exceptions à la règle « indices en Unicode », voir AGENTS.md
  7.8) ; le R n'est pas en italique ;
- valeur recopiée telle quelle ; ``=`` normalisé (``Rf:``, ``Rf 0.35``,
  ``R.f.``, ``R_f`` acceptés) ;
- parenthèse : phase stationnaire puis éluant avec proportions, recopiés tels
  quels (indices Unicode : ``CH2Cl2`` -> ``CH₂Cl₂``) ; un séparateur ``,`` après
  la phase stationnaire placée en tête devient ``;`` ; la parenthèse écrite AVANT
  la valeur (``Rf (hexane/EtOAc 4:1) = 0.35``) est placée après.

Vérifications (valeur jamais modifiée ni arrondie, FLAGGED sinon) :

- 2 décimales ;
- valeur dans l'intervalle [0 ; 1] ;
- parenthèse absente, phase stationnaire absente, proportions de l'éluant
  absentes.

Entrée non reconnue (virgule décimale, plage ``0.3-0.4``, deux parenthèses,
texte inconnu…) : laissée telle quelle et signalée. Seule la première entrée
``Rf`` d'un paragraphe est traitée.
"""

from __future__ import annotations

import re
from typing import List

from core.rules import nmr_common
from core.config import get_config
from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment

# Nombre de décimales attendu pour un Rf.
_DECIMALS = 2

# Label isolé : Rf, R.f., R_f, R f (pas au milieu d'un mot).
_LABEL = r"(?<![A-Za-z])R\s*[._]?\s*f(?![A-Za-z])\.?"
_LABEL_RE = re.compile(_LABEL)

# Parenthèse, un niveau d'imbrication toléré.
_PAREN = r"\((?:[^()]|\([^()]*\))*\)"

# Entrée complète : label, parenthèse éventuelle AVANT la valeur, séparateur,
# valeur, parenthèse éventuelle APRÈS la valeur.
_ENTRY_RE = re.compile(
    _LABEL
    + r"\s*(?:\((?P<p1>(?:[^()]|\([^()]*\))*)\)\s*)?"
    + r"[=:]?\s*"
    + r"(?P<value>\d+(?:[.,]\d+)?)(?![.,]?\d)(?!\s*[\-\u2212\u2013]\s*\d)"
    + r"(?:\s*\((?P<p2>(?:[^()]|\([^()]*\))*)\))?"
)

# Indice qu'une mention de Rf ouvre une vraie entrée : valeur (éventuellement
# précédée d'une parenthèse et de « = ») juste après le label.
_DATA_HINT_RE = re.compile(r"\s*(?:" + _PAREN + r"\s*)?[=:]?\s*\d")

# Phase stationnaire reconnue (n'importe où dans la parenthèse).
_PHASE_RE = re.compile(
    r"SiO\s*[2\u2082]|silica|Al\s*[2\u2082]\s*O\s*[3\u2083]|alumina|"
    r"(?<![A-Za-z0-9])C\s*-?\s*18(?![0-9])|(?<![A-Za-z])RP\b|florisil|celite",
    re.IGNORECASE,
)
# Phase stationnaire placée en tête de parenthèse, suivie d'un séparateur.
_LEADING_PHASE_RE = re.compile(
    r"^(?P<phase>(?:silica(?: gel)?(?: [0-9]+)?(?: F[0-9]+)?|SiO\s*[2\u2082]"
    r"|Al\s*[2\u2082]\s*O\s*[3\u2083]|alumina|C\s*-?\s*18|RP-?18))\s*[,;]\s*(?=\S)",
    re.IGNORECASE,
)
# Proportions de l'éluant : 4:1, 9/1, 20 %, v/v.
_RATIO_RE = re.compile(r"\d+(?:\.\d+)?\s*[:/]\s*\d+|\d+(?:\.\d+)?\s*%|v\s*/\s*v", re.IGNORECASE)
_subscript = nmr_common.subscript_text


def _decimals(value: str) -> int:
    return len(value.split(".")[1]) if "." in value else 0


class RfRule(Rule):
    """Valide et standardise les entrées ``Rf`` (sortie stylisée)."""

    name = "Rf"
    description = (
        "Format : Rf = 0.38 (SiO₂; heptane/CH₂Cl₂ 1:1), f en indice Word. "
        "Valeur jamais modifiée : 2 décimales, intervalle [0 ; 1], phase "
        "stationnaire et proportions de l'éluant vérifiés (signalés si "
        "absents)."
    )

    def _labels(self, text: str) -> List[re.Match]:
        found = []
        for match in _LABEL_RE.finditer(text):
            at_start = not text[: match.start()].strip()
            if at_start or _DATA_HINT_RE.match(text, match.end()):
                found.append(match)
        return found

    def applies(self, paragraph_text: str) -> bool:
        return bool(self._labels(nmr_common.normalize_spaces(paragraph_text)))

    def apply(self, paragraph_text: str) -> RuleResult:
        config = get_config()
        text = nmr_common.normalize_spaces(paragraph_text)
        entry = None
        for label in self._labels(text):
            entry = _ENTRY_RE.match(text, label.start())
            if entry:
                break
        if entry is None:
            return self._flagged(
                paragraph_text,
                "Entrée Rf non reconnue (plage, deux parenthèses ou texte "
                "inconnu) : laissée telle quelle, vérification manuelle.",
            )
        value = entry.group("value")
        if "," in value:
            return self._flagged(
                paragraph_text,
                f"Virgule décimale dans le Rf : {value} ; entrée laissée telle "
                "quelle, vérification manuelle requise.",
                (entry.group(0),),
            )
        if entry.group("p1") is not None and entry.group("p2") is not None:
            return self._flagged(
                paragraph_text,
                "Entrée Rf non reconnue (deux parenthèses) : laissée telle "
                "quelle, vérification manuelle.",
                (entry.group(0),),
            )

        raw = entry.group("p1") if entry.group("p1") is not None else entry.group("p2")
        content = _subscript(" ".join(raw.split())) if raw is not None else ""
        content = _LEADING_PHASE_RE.sub(lambda m: m.group("phase") + "; ", content)

        flags: List[str] = []
        if _decimals(value) != _DECIMALS:
            flags.append(
                "Nombre de décimales du Rf inattendu : "
                f"{value} ({_decimals(value)}) ; {_DECIMALS} attendues, valeur conservée."
            )
        if float(value) > 1:
            flags.append(
                f"Rf hors de l'intervalle [0 ; 1] : {value} ; valeur conservée, "
                "vérification manuelle requise."
            )
        if not content:
            flags.append(
                "Éluant et phase stationnaire absents : à compléter "
                "(ex. (SiO₂; heptane/EtOAc 4:1))."
            )
        else:
            if not _PHASE_RE.search(content):
                flags.append("Phase stationnaire absente : à compléter (ex. SiO₂).")
            if not _RATIO_RE.search(content):
                flags.append("Proportions de l'éluant absentes : à compléter (ex. 4:1).")

        segments = [
            StyledSegment("R", bold=config.bold_label),
            StyledSegment("f", bold=config.bold_label, subscript=True),
            StyledSegment(f" = {value}" + (f" ({content})" if content else "")),
        ]
        start, end = entry.span()
        new_segment = "".join(s.text for s in segments)
        new_text = paragraph_text[:start] + new_segment + paragraph_text[end:]
        value_flags = ("Nombre de décimales", "Rf hors")
        actions = [
            Action(
                ActionKind.FLAGGED, f, self.name,
                (value,) if f.startswith(value_flags) else (new_segment,),
            )
            for f in flags
        ]
        if new_text == paragraph_text:
            return RuleResult(
                new_text=paragraph_text,
                actions=actions
                or [Action(ActionKind.UNCHANGED, "Entrée déjà conforme.", self.name)],
            )
        actions.insert(0, Action(ActionKind.CORRECTED, "Entrée Rf reformatée.", self.name))
        return RuleResult(
            new_text=new_text,
            actions=actions,
            segments=segments,
            replaced_text=paragraph_text[start:end],
        )

    def _flagged(
        self, paragraph_text: str, message: str, highlights: tuple = ()
    ) -> RuleResult:
        return RuleResult(
            new_text=paragraph_text,
            actions=[Action(ActionKind.FLAGGED, message, self.name, highlights)],
        )
