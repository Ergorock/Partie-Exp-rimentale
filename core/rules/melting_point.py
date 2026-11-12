"""Règle de standardisation des points de fusion et d'ébullition (sortie stylisée).

Structure IMPOSÉE (guide LCMCE)::

    m.p. 185 – 186 °C (Et₂O/hexane; dec.; lit. [12] 185 – 187 °C)
    b.p. 80 °C (15 mmHg)

- label ``m.p.`` / ``b.p.`` en gras (``config.bold_label``). Entrées acceptées :
  ``mp``, ``m.p.``, ``Mp``, ``M.p.``, ``MP``, ``melting point`` (idem ``bp``,
  ``boiling point``) ; sortie toujours en minuscules avec points ;
- température entière ou plage : ``185 – 186 °C`` (tiret demi-cadratin entouré
  d'espaces insécables, espace insécable avant ``°C``) ; ``°C`` seul (``ºC``,
  ``˚C``, ``C`` ou unité absente -> ``°C``) ;
- parenthèse optionnelle, éléments dans cet ORDRE séparés par ``; `` : solvant
  (recopié, indices Unicode), pression (``15 mmHg``), ``dec.`` (décomposition),
  ``lit. [réf] valeur °C`` (valeur de la littérature). Les formes d'entrée
  ``(dec.)``, ``dec.`` seul, ``/ 15 mmHg``, ``Et2O/hexane: [réf] 185-187 °C``
  sont reconnues ; l'ordre des éléments est rétabli.

Vérifications (valeurs jamais modifiées ni arrondies, FLAGGED sinon) :

- 0 décimale ;
- plage inversée (``130 – 128``) ;
- unité absente : ``°C`` ajoutée (correction de forme signalée).

Entrée laissée telle quelle et signalée : kelvins (jamais convertis), virgule
décimale, plusieurs solvants, éléments en double, texte inconnu. Tous les
points de fusion / d'ébullition d'un paragraphe sont traités ; le texte entre
deux entrées est conservé. Les labels français (``Pf``, ``Tf``) ne sont pas
reconnus.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from core.config import get_config
from core.rules import nmr_common
from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment

NBSP = nmr_common.NBSP
_UNIT_OUT = "°C"
_DECIMALS = 0

# Label : mp, m.p., M.p., melting point, bp, b.p., boiling point.
_LABEL_RAW = (
    r"(?<![A-Za-z])(?:"
    r"(?P<mp>m\.?\s?p(?![A-Za-z])\.?|melting\s+point(?![A-Za-z]))"
    r"|(?P<bp>b\.?\s?p(?![A-Za-z])\.?|boiling\s+point(?![A-Za-z]))"
    r")"
)
_LABEL_RE = re.compile(_LABEL_RAW, re.IGNORECASE)

# Température : entier / décimal, plage éventuelle, unité éventuelle.
_UNIT_RAW = r"(?:[°º˚]\s*C|C|K)(?![A-Za-z])"
_TEMP_RAW = (
    r"\d+(?:\.\d+)?(?:\s*[\-\u2212\u2013]\s*\d+(?:\.\d+)?)?"
    rf"(?:\s*{_UNIT_RAW})?"
)
_TEMP_RE = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)(?:\s*[\-\u2212\u2013]\s*(?P<hi>\d+(?:\.\d+)?))?"
    rf"(?:\s*(?P<unit>{_UNIT_RAW}))?",
    re.IGNORECASE,
)
_TEMP_WITH_UNIT_RE = re.compile(
    r"(?P<lo>\d+(?:\.\d+)?)(?:\s*[\-\u2212\u2013]\s*(?P<hi>\d+(?:\.\d+)?))?"
    rf"\s*(?P<unit>{_UNIT_RAW})",
    re.IGNORECASE,
)

_PRESS_RAW = r"\d+(?:\.\d+)?\s*(?:mmHg|Torr|mbar|bar|kPa|Pa|atm)(?![A-Za-z])"
_PRESS_RE = re.compile(
    r"(?P<n>\d+(?:\.\d+)?)\s*(?P<u>mmHg|Torr|mbar|bar|kPa|Pa|atm)(?![A-Za-z])",
    re.IGNORECASE,
)
_DEC_RAW = r"d[eé]c(?:omp(?:osition)?)?\.?(?![A-Za-zéè])"
_DEC_RE = re.compile(_DEC_RAW, re.IGNORECASE)
_REF = r"\[[^\]]*\]"

# Entrée complète, du label à la dernière donnée.
_ENTRY_RE = re.compile(
    _LABEL_RAW
    + r"(?P<sep>\s*[:=]?\s*)"
    + rf"(?P<main>{_TEMP_RAW})(?![.,]?\d)"
    + rf"(?:\s+(?P<dec>{_DEC_RAW}))?"
    + rf"(?:\s*(?:/|\bat\b)\s*(?P<press>{_PRESS_RAW}))?"
    + r"(?:\s*\((?P<paren>(?:[^()]|\([^()]*\))*)\))?",
    re.IGNORECASE,
)

# Éléments de la parenthèse.
_LIT_RE = re.compile(
    rf"lit(?:erature)?\.?\s*(?P<ref>{_REF})?\s*:?\s*(?P<val>{_TEMP_RAW})",
    re.IGNORECASE,
)
_COLON_LIT_RE = re.compile(
    rf"(?P<solv>[^:]+?)\s*:\s*(?P<ref>{_REF})?\s*"
    rf"(?P<val>\d+(?:\.\d+)?(?:\s*[\-\u2212\u2013]\s*\d+(?:\.\d+)?)?\s*{_UNIT_RAW})",
    re.IGNORECASE,
)

# Indice qu'une mention de m.p. / b.p. ouvre une vraie entrée.
_DATA_HINT_RE = re.compile(r"\s*[:=]?\s*\d")


class _Unrecognized(Exception):
    """Entrée qui ne respecte pas la structure : laissée telle quelle."""


class _Entry:
    def __init__(self, start: int, end: int) -> None:
        self.start, self.end = start, end
        self.segments: List[StyledSegment] = []
        self.flags: List[Tuple[str, Tuple[str, ...]]] = []  # (message, extraits)
        self.corrections: List[str] = []


def _split_top_level(text: str) -> List[str]:
    """Découpe sur ``;`` et ``,`` hors parenthèses / crochets."""
    parts: List[str] = []
    depth, current = 0, ""
    for ch in text:
        if ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        if ch in ";," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    parts.append(current)
    return [p.strip() for p in parts if p.strip()]


class MeltingPointRule(Rule):
    """Valide et standardise les points de fusion (m.p.) et d'ébullition (b.p.)."""

    name = "m.p. / b.p."
    description = (
        "Format : m.p. 185 – 186 °C (solvant; pression; dec.; lit. [réf] "
        "185 – 187 °C), idem b.p. Valeurs jamais modifiées : 0 décimale, plage "
        "inversée et kelvins signalés ; °C ajouté si l'unité est absente."
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

    # ------------------------------------------------------------------ #
    def apply(self, paragraph_text: str) -> RuleResult:
        config = get_config()
        text = nmr_common.normalize_spaces(paragraph_text)
        entries: List[_Entry] = []
        flags: List[Tuple[str, Tuple[str, ...]]] = []
        position = 0
        for label in self._labels(text):
            if label.start() < position:
                continue
            match = _ENTRY_RE.match(text, label.start())
            if match is None:
                flags.append((
                    "Entrée m.p. / b.p. non reconnue (virgule décimale, plage "
                    "ou texte inconnu) : laissée telle quelle, vérification "
                    "manuelle.",
                    (text[label.start():label.end() + 20].rstrip(),),
                ))
                continue
            try:
                entry = self._build(match, config.bold_label)
            except _Unrecognized as error:
                flags.append((str(error), (match.group(0),)))
                position = match.end()
                continue
            entries.append(entry)
            position = match.end()

        if not entries:
            return RuleResult(
                new_text=paragraph_text,
                actions=[Action(ActionKind.FLAGGED, m, self.name, h) for m, h in flags]
                or [Action(
                    ActionKind.FLAGGED,
                    "Entrée m.p. / b.p. non reconnue : laissée telle quelle, "
                    "vérification manuelle.",
                    self.name,
                )],
            )

        first, last = entries[0].start, entries[-1].end
        segments: List[StyledSegment] = []
        cursor = first
        for entry in entries:
            if entry.start > cursor:
                segments.append(StyledSegment(paragraph_text[cursor:entry.start]))
            segments += entry.segments
            cursor = entry.end
            flags += entry.flags
        corrections: List[str] = []
        for entry in entries:
            for message in entry.corrections:
                if message not in corrections:
                    corrections.append(message)

        new_segment = "".join(s.text for s in segments)
        new_text = paragraph_text[:first] + new_segment + paragraph_text[last:]
        actions = [Action(ActionKind.FLAGGED, f, self.name, h) for f, h in flags]
        if new_text == paragraph_text:
            return RuleResult(
                new_text=paragraph_text,
                actions=actions
                or [Action(ActionKind.UNCHANGED, "Entrée déjà conforme.", self.name)],
            )
        actions = (
            [Action(ActionKind.CORRECTED, "Entrée m.p. / b.p. reformatée.", self.name)]
            + [Action(ActionKind.CORRECTED, m, self.name) for m in corrections]
            + actions
        )
        return RuleResult(
            new_text=new_text,
            actions=actions,
            segments=segments,
            replaced_text=paragraph_text[first:last],
        )

    # ------------------------------------------------------------------ #
    def _build(self, match: re.Match, bold: bool) -> _Entry:
        entry = _Entry(match.start(), match.end())
        label = "m.p." if match.group("mp") else "b.p."
        numbers: List[str] = []
        ranges: List[Tuple[str, str]] = []

        def temperature(raw: str, *, require_unit: bool = False) -> str:
            parsed = (_TEMP_WITH_UNIT_RE if require_unit else _TEMP_RE).fullmatch(raw.strip())
            if parsed is None:
                raise _Unrecognized(
                    "Entrée m.p. / b.p. non reconnue (température illisible) : "
                    f"{raw.strip()} ; laissée telle quelle, vérification manuelle."
                )
            unit = parsed.group("unit")
            if unit and unit.upper() == "K":
                raise _Unrecognized(
                    "Température en kelvins : "
                    f"{raw.strip()} ; unité non convertie, entrée laissée telle "
                    "quelle, vérification manuelle requise."
                )
            if not unit:
                message = f"Unité de la température absente : {_UNIT_OUT} ajoutée."
                if message not in entry.corrections:
                    entry.corrections.append(message)
            lo, hi = parsed.group("lo"), parsed.group("hi")
            numbers.extend(n for n in (lo, hi) if n)
            if hi:
                if float(hi) < float(lo):
                    ranges.append((lo, hi))
                value = f"{lo}{nmr_common.RANGE_SEP}{hi}"
            else:
                value = lo
            return f"{value}{NBSP}{_UNIT_OUT}"

        main = temperature(match.group("main"))

        solvent: Optional[str] = None
        pressure: Optional[str] = None
        decomposition = bool(match.group("dec"))
        literature: Optional[str] = None

        def set_pressure(raw: str) -> str:
            parsed = _PRESS_RE.fullmatch(raw.strip())
            assert parsed is not None
            return f"{parsed.group('n')}{NBSP}{parsed.group('u')}"

        if match.group("press"):
            pressure = set_pressure(match.group("press"))

        for token in _split_top_level(match.group("paren") or ""):
            token = " ".join(token.split())
            lit = _LIT_RE.fullmatch(token)
            colon = _COLON_LIT_RE.fullmatch(token)
            if _DEC_RE.fullmatch(token):
                if decomposition:
                    raise _Unrecognized(self._duplicate("dec."))
                decomposition = True
            elif _PRESS_RE.fullmatch(re.sub(r"^(?:at|/)\s*", "", token, flags=re.IGNORECASE)):
                if pressure:
                    raise _Unrecognized(self._duplicate("pression"))
                pressure = set_pressure(re.sub(r"^(?:at|/)\s*", "", token, flags=re.IGNORECASE))
            elif lit or (colon and not token.lower().startswith("lit")):
                if literature:
                    raise _Unrecognized(self._duplicate("lit."))
                source = lit or colon
                if colon and not lit:
                    if solvent:
                        raise _Unrecognized(self._duplicate("solvant"))
                    solvent = nmr_common.subscript_text(colon.group("solv").strip())
                ref = source.group("ref")
                value = temperature(source.group("val"))
                literature = f"lit. {ref + ' ' if ref else ''}{value}"
            elif token.lower().startswith("lit"):
                raise _Unrecognized(
                    "Entrée m.p. / b.p. non reconnue (valeur de la littérature "
                    f"illisible) : {token} ; laissée telle quelle, vérification manuelle."
                )
            else:
                if solvent:
                    raise _Unrecognized(self._duplicate("solvant"))
                solvent = nmr_common.subscript_text(token)

        items = [i for i in (solvent, pressure, "dec." if decomposition else None, literature) if i]
        rest = f" {main}" + (f" ({'; '.join(items)})" if items else "")
        entry.segments = [StyledSegment(label, bold=bold), StyledSegment(rest)]

        wrong = [f"{n} ({len(n.split('.')[1]) if '.' in n else 0})" for n in numbers
                 if (len(n.split(".")[1]) if "." in n else 0) != _DECIMALS]
        if wrong:
            entry.flags.append((
                "Nombre de décimales de la température inattendu : "
                f"{', '.join(wrong)} ; {_DECIMALS} attendue, valeurs conservées.",
                tuple(w.split(" (")[0] for w in wrong),
            ))
        for lo, hi in ranges:
            entry.flags.append((
                f"Plage de températures inversée : {lo} – {hi} ; valeurs "
                "conservées, vérification manuelle requise.",
                (f"{lo}{nmr_common.RANGE_SEP}{hi}",),
            ))
        return entry

    @staticmethod
    def _duplicate(what: str) -> str:
        return (
            f"Entrée m.p. / b.p. non reconnue ({what} en double) : laissée "
            "telle quelle, vérification manuelle."
        )
