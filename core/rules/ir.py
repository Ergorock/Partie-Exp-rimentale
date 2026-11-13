"""Règle de standardisation des entrées IR (sortie stylisée).

Format cible::

    IR (ATR): ν̃(cm⁻¹) = 3420, 1715, 1600

- label ``IR`` seul en gras (``config.bold_label``) ; ``ν̃`` = ν + U+0303 ;
- méthode entre parenthèses (KBr, film, neat, ATR, CHCl₃…), recopiée telle
  qu'écrite, avec des indices Unicode ;
- bandes en cm⁻¹ : valeurs ENTIÈRES recopiées telles quelles, triées de la plus
  grande à la plus petite (tri fixe, une plage ``3300 – 2400`` est triée sur sa
  borne haute et écrite avec un tiret demi-cadratin entouré d'espaces
  insécables) ; attribution / intensité éventuelle
  entre parenthèses conservée (``1715 (C=O)``, ``3420 (br)``) ;
- unité ``cm⁻¹`` Unicode dans la parenthèse du symbole.

Variantes d'entrée acceptées : symbole ``νmax`` / ``ν`` / ``ν̃`` / ``vmax`` /
``v`` ou aucun ; unité ``cm-1`` / ``cm−1`` / ``cm^-1`` / ``cm⁻¹`` en fin de
liste, entre parenthèses ou en tête (``νmax/cm-1``), ou dans la parenthèse de la
méthode (``IR (ATR, cm-1)``) ; séparateur ``=`` ou ``:`` optionnel.

Règle de sûreté : l'entrée est laissée telle quelle et signalée (FLAGGED) si la
méthode est absente, si une bande n'est pas un entier (décimale, virgule
décimale), si du texte figure hors parenthèse ou si une parenthèse est
imbriquée. Aucune valeur n'est jamais modifiée ni arrondie.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from core.config import get_config
from core.rules import nmr_common
from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment

# Symbole de sortie : ν + tilde combinant (U+0303).
_NU_TILDE = "\u03bd\u0303"
# Unité de sortie : cm⁻¹.
_UNIT_OUT = "cm\u207b\u00b9"

# Unité écrite en entrée : cm-1, cm−1, cm–1, cm^-1, cm⁻¹.
_UNIT = r"cm\s*(?:\^\s*)?[\-\u2212\u2013\u207b]\s*(?:1|\u00b9)"
_UNIT_RE = re.compile(_UNIT)
_TRAILING_UNIT_RE = re.compile(rf"\s*{_UNIT}\s*$")

# Symbole écrit en entrée : ν, ν̃, ṽ, v (latin), avec « max » éventuel.
_SYMBOL = r"(?:[\u03bdv]\u0303?|\u1e7d)(?:\s*(?:max|\u2098\u2090\u2093))?"

# Début d'entrée : label, méthode, séparateur, symbole, unité, « = ».
_HEAD_RE = re.compile(
    r"IR\s*(?:\((?P<method>[^()]*)\))?"
    r"\s*[:;,]?\s*"
    rf"(?:(?P<symbol>{_SYMBOL})\s*)?"
    rf"(?:(?P<unit>\(\s*{_UNIT}\s*\)|/\s*{_UNIT}|{_UNIT})\s*)?"
    r"[=:]?\s*"
)

# Une bande : entier de 3 ou 4 chiffres, ou plage d'entiers (``3300 – 2400``,
# OH des acides), + au plus une parenthèse simple.
_BAND_RE = re.compile(
    r"(?P<low>\d{3,4})(?:\s*[-\u2212\u2013]\s*(?P<high>\d{3,4}))?"
    r"\s*(?:\((?P<attr>[^()]*)\))?"
)

# Virgule décimale (``1715,5``) : découpage de la liste ambigu.
_DECIMAL_COMMA_RE = re.compile(r"\d,\d")

# Légende « IR intensities / intensity / inten. » : paragraphe ignoré.
_INTENSITY_WORD_RE = re.compile(r"\s*inten", re.IGNORECASE)

# Label IR isolé (pas au milieu d'un mot : FTIR, DIRECT…).
_LABEL_RE = re.compile(r"(?<![A-Za-z])IR(?![A-Za-z])")
# Indice qu'une mention de IR ouvre une vraie entrée : parenthèse, symbole,
# unité ou bande juste après le label.
_DATA_HINT_RE = re.compile(
    r"\s*(?:\([^()]*\)\s*)?[:;,]?\s*"
    r"(?:\(|\u03bd|\u1e7d|v(?:max)?(?=[\s=(/:\d])|cm\s*\^?\s*[\-\u2212\u2013\u207b]|\d{3,4})"
)


class IrRule(Rule):
    """Valide et standardise les entrées IR (sortie stylisée)."""

    name = "IR"
    description = (
        "Format : IR (ATR): ν̃(cm⁻¹) = 3420, 1715, 1600. Méthode entre "
        "parenthèses, bandes entières triées par ordre décroissant, "
        "attribution éventuelle conservée. Valeurs jamais modifiées : entrée "
        "laissée telle quelle et signalée si la méthode est absente ou si une "
        "bande n'est pas un entier."
    )

    def _labels(self, text: str) -> List[re.Match]:
        found = []
        for match in _LABEL_RE.finditer(text):
            at_start = not text[: match.start()].strip()
            # « IR intensities… » (légende des intensités) n'est pas une entrée IR.
            if _INTENSITY_WORD_RE.match(text, match.end()):
                continue
            if at_start or _DATA_HINT_RE.match(text, match.end()):
                found.append(match)
        return found

    def applies(self, paragraph_text: str) -> bool:
        return bool(self._labels(nmr_common.normalize_spaces(paragraph_text)))

    def apply(self, paragraph_text: str) -> RuleResult:
        config = get_config()
        text = nmr_common.normalize_spaces(paragraph_text)
        labels = self._labels(text)
        if not labels:
            return self._flagged(
                paragraph_text,
                ["Entrée IR non reconnue : laissée telle quelle, vérification manuelle."],
            )

        start = labels[0].start()
        end = nmr_common.next_analysis_start(text, labels[0].end())
        segment = text[start:end].rstrip()
        end = start + len(segment)

        head = _HEAD_RE.match(segment)
        # Le motif commence par le label : il reconnaît toujours au moins « IR ».
        assert head is not None
        flags: List[str] = []

        method = self._clean_method(head.group("method"))
        if method is None:
            flags.append(
                "Méthode d'analyse IR absente ou illisible : à compléter "
                "(ex. KBr, film, neat, ATR)."
            )

        body, punct = nmr_common.split_trailing_punctuation(segment[head.end():])
        body, unit_count = _TRAILING_UNIT_RE.subn("", body)
        body = body.strip()
        raw_method = head.group("method") or ""
        has_unit = bool(
            head.group("unit")
            or unit_count
            or any(_UNIT_RE.fullmatch(" ".join(e.split())) for e in raw_method.split(","))
        )
        bands, band_flags = self._parse_bands(body)
        flags += band_flags

        if flags:
            return self._flagged(paragraph_text, flags, (paragraph_text[start:end],))

        bands.sort(key=lambda b: -max(int(n) for n in re.findall(r"\d+", b[0])))
        listing = ", ".join(f"{v} ({a})" if a else v for v, a in bands)
        rest = f" ({nmr_common.subscript_formula(method)}): {_NU_TILDE}({_UNIT_OUT}) = {listing}{punct}"
        segments = [
            StyledSegment("IR", bold=config.bold_label),
            StyledSegment(rest),
        ]
        new_segment = "".join(s.text for s in segments)
        new_text = paragraph_text[:start] + new_segment + paragraph_text[end:]
        if new_text == paragraph_text:
            return RuleResult(
                new_text=paragraph_text,
                actions=[Action(ActionKind.UNCHANGED, "Entrée déjà conforme.", self.name)],
            )
        actions = [Action(ActionKind.CORRECTED, "Entrée IR reformatée.", self.name)]
        if not has_unit:
            actions.append(Action(
                ActionKind.CORRECTED,
                f"Unité des bandes IR absente : {_UNIT_OUT} ajoutée.",
                self.name,
            ))
        if not head.group("symbol"):
            actions.append(Action(
                ActionKind.CORRECTED,
                f"Symbole du nombre d'onde absent : {_NU_TILDE} ajouté.",
                self.name,
            ))
        return RuleResult(
            new_text=new_text,
            actions=actions,
            segments=segments,
            replaced_text=paragraph_text[start:end],
        )

    # ------------------------------------------------------------------ #

    def _flagged(
        self, paragraph_text: str, messages: List[str], highlights: tuple = ()
    ) -> RuleResult:
        """Texte inchangé + une action FLAGGED par message."""
        return RuleResult(
            new_text=paragraph_text,
            actions=[Action(ActionKind.FLAGGED, m, self.name, highlights) for m in messages],
        )

    @staticmethod
    def _clean_method(raw: Optional[str]) -> Optional[str]:
        """Méthode sans l'unité éventuelle (``ATR, cm-1`` -> ``ATR``), ou None."""
        if raw is None:
            return None
        elements = [" ".join(e.split()) for e in raw.split(",")]
        kept = [e for e in elements if e and not _UNIT_RE.fullmatch(e)]
        method = ", ".join(kept)
        # Une « méthode » sans lettre (``(3420)``) n'en est pas une.
        return method if re.search(r"[A-Za-z]", method) else None

    @staticmethod
    def _parse_bands(body: str) -> Tuple[List[Tuple[str, str]], List[str]]:
        """Bandes ``(valeur, attribution)`` et messages FLAGGED éventuels."""
        if not body:
            return [], ["Aucune bande IR reconnue : liste vide, à compléter."]
        if _DECIMAL_COMMA_RE.search(body):
            return [], [
                "Virgule décimale ou séparateur ambigu dans les bandes IR : "
                f"{body} ; entrée laissée telle quelle, vérification manuelle requise."
            ]
        bands: List[Tuple[str, str]] = []
        unknown: List[str] = []
        for item in nmr_common._split_top_level(body):
            match = _BAND_RE.fullmatch(item)
            attr = (match.group("attr") or "").strip() if match else ""
            if match and (match.group("attr") is None or attr):
                value = match.group("low")
                if match.group("high"):
                    # Plage : tiret demi-cadratin entouré d'espaces insécables.
                    value += f"{nmr_common.RANGE_SEP}{match.group('high')}"
                bands.append((
                    value,
                    nmr_common.subscript_attribution(" ".join(attr.split())),
                ))
            else:
                unknown.append(item)
        if unknown:
            return [], [
                "Bandes IR non reconnues (entiers de 3 à 4 chiffres attendus, "
                f"attribution entre parenthèses) : {' ; '.join(unknown)} ; "
                "entrée laissée telle quelle, vérification manuelle requise."
            ]
        return bands, []
