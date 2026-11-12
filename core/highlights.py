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

    if not raw:
        return []
    kinds: List[Optional[str]] = [None] * len(after)
    for start, end, kind in raw:
        for i in range(max(0, start), min(len(after), end)):
            if kinds[i] is None or _PRIORITY[kind] > _PRIORITY[kinds[i]]:
                kinds[i] = kind
    spans: List[Dict[str, object]] = []
    i = 0
    while i < len(after):
        if kinds[i] is None:
            i += 1
            continue
        j = i
        while j < len(after) and kinds[j] == kinds[i]:
            j += 1
        spans.append({"start": i, "end": j, "kind": kinds[i]})
        i = j
    return spans
