"""Règle « Unités » : espace insécable entre un nombre et son unité.

Guide LCMCE (ISO 80000) : une espace insécable sépare toujours le nombre de
l'unité (``5 m``, ``220 mg``, ``77 %``, ``25 °C``), sauf ``mol%`` / ``wt%`` /
``vol%`` où le ``%`` est collé (``10 mol%``).

Seule la FORME change (jamais un nombre, jamais une unité ajoutée) :

- ``220 mg`` / ``220mg`` -> ``220\u00a0mg`` ;
- ``10 mol %`` -> ``10\u00a0mol%`` ;
- ``25°C`` / ``25 ºC`` / ``25 ˚C`` -> ``25\u00a0°C`` (vrai symbole degré).

Garde-fous :

- les unités d'une seule lettre (``g``, ``h``, ``L``, ``M``) ne sont traitées
  que si une espace est déjà écrite (``5g`` peut être le composé 5g) ;
- une espace fine insécable (U+202F) déjà présente est conservée ;
- tout texte à partir du premier label d'analyse (RMN, HRMS, IR, Rf, m.p.,
  b.p.) est laissé aux règles d'analyse : cette règle ne touche que la
  procédure qui précède ;
- rendement avec décimale dans ``(843 mg, 77.5 %)`` : signalé (FLAGGED), valeur
  conservée.

Limite : les ``MHz``, ``K`` et ``Hz`` des parenthèses RMN restent écrits avec
une espace ordinaire (gérés par les règles RMN).
"""

from __future__ import annotations

import re
from typing import List, Tuple

from core.rules import nmr_common
from core.rules.base import Action, ActionKind, Rule, RuleResult

NBSP = nmr_common.NBSP
_NARROW_NBSP = "\u202f"

# Unités reconnues. Les multi-lettres et symboles acceptent l'absence d'espace
# (``220mg``) ; celles d'une lettre exigent une espace déjà écrite.
_MULTI = [
    "mmol", "µmol", "μmol", "mol", "mg", "kg", "µg", "μg", "ng", "mL", "µL", "μL",
    "min", "equiv.", "equiv", "eq.", "mM", "µM", "μM", "nm", "mm", "cm", "MHz",
    "kHz", "Hz", "mbar", "bar", "mmHg", "Torr", "kJ", "kcal", "rpm",
]
_SINGLE = ["g", "h", "L", "M"]
_DEGREE = r"[°º˚]\s?C"
_PERCENT_UNITS = r"(?:mol|wt|vol)\s?%"

_MULTI_RAW = "|".join(re.escape(u) for u in sorted(_MULTI, key=len, reverse=True))
_SINGLE_RAW = "|".join(re.escape(u) for u in _SINGLE)

_NUMBER = r"(?<![\w.,])(?P<num>\d+(?:[.,]\d+)?)"
_SEP = r"[ \t\u00a0\u202f]"
_END = r"(?![A-Za-zµμ])"

# Un nombre suivi de son unité. Groupes : num, sep, unit.
_QUANTITY_RE = re.compile(
    _NUMBER
    + r"(?:"
    + rf"(?P<sep1>{_SEP}*)(?P<unit1>{_PERCENT_UNITS}|{_DEGREE}|%|{_MULTI_RAW}){_END}"
    + rf"|(?P<sep2>{_SEP}+)(?P<unit2>{_SINGLE_RAW}){_END}"
    + r")"
)

# Rendement avec décimale : (843 mg, 77.5 %).
_YIELD_RE = re.compile(
    r"\(\s*\d+(?:[.,]\d+)?\s*(?:mg|g|kg|mmol|mol)\s*,\s*(?P<y>\d+[.,]\d+)\s*%"
)


def _protected_start(text: str) -> int:
    """Début de la zone réservée aux règles d'analyse (fin du texte si aucune)."""
    positions = [
        m.start()
        for m in (
            nmr_common._SECTION_LABEL_RE.search(text),
            nmr_common._OTHER_ANALYSIS_RE.search(text),
        )
        if m
    ]
    return min(positions, default=len(text))


def _normalized_unit(raw: str) -> str:
    if re.fullmatch(_DEGREE, raw):
        return "°C"
    if re.fullmatch(_PERCENT_UNITS, raw):
        return raw.replace(" ", "")
    return raw


class UnitsRule(Rule):
    """Pose l'espace insécable entre un nombre et son unité (procédure)."""

    name = "Unités"
    description = (
        "Espace insécable entre le nombre et l'unité (220 mg, 77 %, 25 °C), "
        "10 mol% sans espace avant le %. Seule la forme change ; le texte des "
        "analyses est laissé aux règles d'analyse."
    )

    def _edits(self, text: str) -> Tuple[List[Tuple[int, int, str]], int]:
        """Remplacements ``(début, fin, texte)`` et début de zone protégée."""
        limit = _protected_start(text)
        edits: List[Tuple[int, int, str]] = []
        for match in _QUANTITY_RE.finditer(text, 0, limit):
            sep = match.group("sep1") if match.group("unit1") else match.group("sep2")
            unit = match.group("unit1") or match.group("unit2")
            wanted = f"{match.group('num')}{NBSP}{_normalized_unit(unit)}"
            if sep == _NARROW_NBSP and _normalized_unit(unit) == unit:
                continue  # espace fine insécable conservée
            if match.group(0) != wanted:
                edits.append((match.start(), match.end(), wanted))
        return edits, limit

    def applies(self, paragraph_text: str) -> bool:
        return bool(_QUANTITY_RE.search(paragraph_text, 0, _protected_start(paragraph_text)))

    def apply(self, paragraph_text: str) -> RuleResult:
        edits, limit = self._edits(paragraph_text)
        flags = [
            (
                "Rendement avec décimale : "
                f"{m.group('y')} % ; 0 décimale attendue, valeur conservée.",
                (f"{m.group('y')} %",),
            )
            for m in _YIELD_RE.finditer(paragraph_text, 0, limit)
            if "." in m.group("y") or "," in m.group("y")
        ]
        actions = [Action(ActionKind.FLAGGED, f, self.name, h) for f, h in flags]
        if not edits:
            return RuleResult(
                new_text=paragraph_text,
                actions=actions
                or [Action(ActionKind.UNCHANGED, "Unités déjà conformes.", self.name)],
            )
        new_text = paragraph_text
        for start, end, replacement in reversed(edits):
            new_text = new_text[:start] + replacement + new_text[end:]
        shown = ", ".join(
            paragraph_text[start:end].strip() for start, end, _ in edits[:5]
        ) + (" …" if len(edits) > 5 else "")
        corrections = [Action(
            ActionKind.CORRECTED,
            f"Espace insécable entre nombre et unité : {shown} "
            f"({len(edits)} occurrence{'s' if len(edits) > 1 else ''}).",
            self.name,
        )]
        return RuleResult(new_text=new_text, actions=corrections + actions)
