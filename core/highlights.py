"""Surlignage dans le texte : empans (début, fin, cas) du texte final d'un paragraphe.

Affichage seulement (l'interface surligne ces empans), sans effet sur le
traitement. Trois cas, par ordre de priorité quand ils se recouvrent :

- ``flagged`` : extraits fournis par les règles (``Action.highlights``) pour
  un signalement « à vérifier » ;
- ``placeholder`` : marqueur inséré pour une donnée manquante (``[??? K]``) ;
- ``corrected`` : portions du texte final qui diffèrent du texte d'origine
  (comparaison mot à mot, espaces insécables comprises).

Les positions sont celles du texte FINAL (``after``). Un extrait introuvable
est ignoré silencieusement.
"""

from __future__ import annotations

import difflib
import re
from typing import Dict, Iterable, List, Optional

from core.config import get_config
from core.rules.base import Action, ActionKind

# Priorité (la plus haute l'emporte sur un recouvrement).
_PRIORITY = {"corrected": 1, "placeholder": 2, "flagged": 3}

_TOKEN_RE = re.compile(r"\w+|\s+|[^\w\s]", re.UNICODE)
_MARKER_RE = re.compile(r"\[\?\?\?[^\]]*\]")


def _tokens(text: str) -> List[re.Match]:
    return list(_TOKEN_RE.finditer(text))


def _corrected_spans(before: str, after: str) -> List[tuple]:
    """Portions de ``after`` modifiées ou ajoutées par rapport à ``before``."""
    if before == after:
        return []
    old, new = _tokens(before), _tokens(after)
    matcher = difflib.SequenceMatcher(
        None, [m.group(0) for m in old], [m.group(0) for m in new], autojunk=False
    )
    spans = []
    for tag, _, _, j1, j2 in matcher.get_opcodes():
        if tag in ("replace", "insert") and j1 < j2:
            spans.append((new[j1].start(), new[j2 - 1].end(), "corrected"))
    return spans


def _find_all(haystack: str, needle: str) -> List[tuple]:
    """Occurrences de ``needle`` (espaces insécables assimilés à des espaces)."""
    if len(needle.strip()) < 2:
        return []
    flat = haystack.replace("\u00a0", " ").replace("\u202f", " ")
    target = needle.replace("\u00a0", " ").replace("\u202f", " ")
    spans, start = [], 0
    while True:
        index = flat.find(target, start)
        if index < 0:
            return spans
        spans.append((index, index + len(target)))
        start = index + len(target)


def compute_spans(
    before: str, after: str, actions: Iterable[Action], changed: Optional[bool] = None
) -> List[Dict[str, object]]:
    """Empans à surligner dans ``after`` : ``[{"start", "end", "kind"}]``.

    Les empans sont triés, sans recouvrement ; les empans contigus de même cas
    sont fusionnés.
    """
    actions = list(actions)
    raw: List[tuple] = []
    if any(a.kind == ActionKind.CORRECTED for a in actions) or changed:
        raw += _corrected_spans(before, after)
    if any(a.kind == ActionKind.PLACEHOLDER for a in actions):
        markers = {get_config().temperature_placeholder}
        for marker in markers:
            raw += [(s, e, "placeholder") for s, e in _find_all(after, marker)]
        raw += [(m.start(), m.end(), "placeholder") for m in _MARKER_RE.finditer(after)]
    for action in actions:
        if action.kind != ActionKind.FLAGGED:
            continue
        for excerpt in action.highlights:
            raw += [(s, e, "flagged") for s, e in _find_all(after, excerpt)]

    return _merge(raw, len(after))


def _merge(raw: List[tuple], length: int) -> List[Dict[str, object]]:
    """Empans triés, sans recouvrement (priorité), contigus de même cas fusionnés."""
    if not raw:
        return []
    kinds: List[Optional[str]] = [None] * length
    for start, end, kind in raw:
        for i in range(max(0, start), min(length, end)):
            if kinds[i] is None or _PRIORITY[kind] > _PRIORITY[kinds[i]]:
                kinds[i] = kind
    spans: List[Dict[str, object]] = []
    i = 0
    while i < length:
        if kinds[i] is None:
            i += 1
            continue
        j = i
        while j < length and kinds[j] == kinds[i]:
            j += 1
        spans.append({"start": i, "end": j, "kind": kinds[i]})
        i = j
    return spans


def _source_changes(source: str, target: str) -> set:
    """Positions de ``source`` modifiées ou supprimées pour obtenir ``target``.

    Une pure insertion marque les mots qui l'entourent (« J=8 » -> « J = 8 »).
    """
    if source == target:
        return set()
    old, new = _tokens(source), _tokens(target)
    matcher = difflib.SequenceMatcher(
        None, [m.group(0) for m in old], [m.group(0) for m in new], autojunk=False
    )
    positions: set = set()
    for tag, i1, i2, _, _ in matcher.get_opcodes():
        if tag in ("replace", "delete"):
            touched = old[i1:i2]
        elif tag == "insert":
            touched = old[max(0, i1 - 1):i1 + 1]
        else:
            continue
        for m in touched:
            positions.update(range(m.start(), m.end()))
    return positions


def source_spans(
    original: str, rule_input: str, rule_output: str, actions: Iterable[Action]
) -> List[Dict[str, object]]:
    """Empans à surligner dans le texte D'ORIGINE pour une règle (mode évaluation).

    Les règles s'appliquent en chaîne : ``rule_input`` est le texte reçu par la
    règle, ``rule_output`` celui qu'elle produit. Seules les positions de
    ``original`` que CETTE règle modifie sont ``corrected`` ; les extraits
    signalés retrouvés tels quels dans l'original sont ``flagged``. Un marqueur
    (donnée manquante) n'a pas de position dans l'original.
    """
    actions = list(actions)
    changed = _source_changes(original, rule_output) - _source_changes(original, rule_input)
    raw: List[tuple] = [(i, i + 1, "corrected") for i in changed]
    for action in actions:
        if action.kind == ActionKind.FLAGGED:
            for excerpt in action.highlights:
                raw += [(s, e, "flagged") for s, e in _find_all(original, excerpt)]
    return _merge(raw, len(original))
