"""Base commune des règles de section RMN (``1H NMR``, ``13C NMR``…).

Une règle de section RMN localise SA section dans le paragraphe (en tête, ou
après un préfixe / une autre section collée), la reformate et laisse le reste
du paragraphe strictement intact. Format cible (exposant Unicode, gras sur le
label + la parenthèse, delta italique)::

    ¹H NMR (<fréquence> MHz, <solvant>, <température> K) δ <signaux>

Garde-fous (on ne supprime ni n'invente jamais de texte) :

- entre le label et la parenthèse, seuls une ponctuation ou une fréquence
  (``400 MHz``) sont acceptés ; un autre texte -> FLAGGED sans correction ;
- sans delta, ou si un texte non reconnu précède le delta, la parenthèse est
  normalisée mais la suite de la section est conservée telle quelle (FLAGGED) ;
- les signaux ne sont triés / reformatés que s'ils sont tous parsables sans
  perte (voir ``nmr_common.parse_signals``).

Une sous-classe fixe ``nucleus`` (motif regex du noyau, ex. ``"1H"``) et
``format_signal``.
"""

from __future__ import annotations

import re
from typing import List, Optional

from core.config import get_config
from core.rules import nmr_common
from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment

_KIND_MAP = {
    "corrected": ActionKind.CORRECTED,
    "placeholder": ActionKind.PLACEHOLDER,
    "flagged": ActionKind.FLAGGED,
}

# Texte autorisé entre le label et la parenthèse : ponctuation seule…
_SEP = r"[\s:,\-–]*"
_BETWEEN_PUNCT_RE = re.compile(_SEP)
# …ou une fréquence écrite hors de la parenthèse (déplacée à l'intérieur).
_BETWEEN_FREQ_RE = re.compile(
    _SEP + r"(?P<freq>\d+(?:\.\d+)?\s*MHz)" + _SEP, re.IGNORECASE
)


def _between_ok(between: str) -> bool:
    return bool(_BETWEEN_PUNCT_RE.fullmatch(between) or _BETWEEN_FREQ_RE.fullmatch(between))


# Symbole de constante de couplage : 'J' isolé suivi de '=' (J = 8.4 Hz).
_J_SYMBOL_RE = re.compile(r"(?<![A-Za-z])J(?=\s*=)")


def _signal_segments(text: str, italic_j: bool) -> List[StyledSegment]:
    """Découpe la liste des signaux en segments, avec chaque ``J`` en italique.

    Seule la mise en forme change : la concaténation des segments est égale à
    ``text``.
    """
    if not italic_j:
        return [StyledSegment(text)]
    segments: List[StyledSegment] = []
    last = 0
    for match in _J_SYMBOL_RE.finditer(text):
        if match.start() > last:
            segments.append(StyledSegment(text[last:match.start()]))
        segments.append(StyledSegment("J", italic=True))
        last = match.end()
    if last < len(text):
        segments.append(StyledSegment(text[last:]))
    return segments


class NmrSectionRule(Rule):
    """Règle générique de section RMN (sortie stylisée)."""

    #: Motif regex du noyau en entrée (ex. ``"1H"``, ``"13C"``).
    nucleus: str = ""

    def __init__(self) -> None:
        # Label ASCII du noyau, non précédé d'un chiffre / d'une lettre / d'une
        # accolade (évite '{1H} NMR' dans '19F{1H} NMR'). Accepte un découplage
        # optionnel ('13C{1H} NMR') et un tiret avant le mot ('1H-NMR').
        # La forme déjà stylisée ('¹H NMR', '¹⁹F{¹H} NMR') est aussi reconnue :
        # une section conforme est ainsi évaluée (UNCHANGED) au lieu d'être
        # ignorée.
        nucleus = re.escape(self.nucleus)
        styled = re.escape(
            re.sub(r"^\d+", lambda m: nmr_common.to_superscript(m.group()), self.nucleus)
        )
        label = rf"(?:{nucleus}|{styled})(?:\{{(?:1|¹)H\}})?[\s\-–]*(?:NMR|RMN)"
        self._label_re = re.compile(
            rf"(?<![0-9A-Za-z{{⁰¹²³⁴⁵⁶⁷⁸⁹]){label}\b", re.IGNORECASE
        )
        self._structure_re = re.compile(
            rf"^(?P<label>{label})\b"
            # Parenthèse de section : un niveau d'imbrication toléré pour un
            # solvant comme '(CD3)2SO'.
            r"(?P<between>[^(]*)\((?P<inside>(?:[^()]|\([^()]*\))*)\)(?P<rest>.*)$",
            re.IGNORECASE | re.DOTALL,
        )

    # ------------------------------------------------------------------ #
    # À fournir par les sous-classes
    # ------------------------------------------------------------------ #
    def format_signal(self, signal: nmr_common.Signal) -> str:
        raise NotImplementedError

    # ------------------------------------------------------------------ #
    # Localisation de la section
    # ------------------------------------------------------------------ #
    def _find_label(self, text: str) -> Optional[re.Match]:
        """Premier label du noyau qui ouvre une vraie section RMN.

        Un label en tête de paragraphe est toujours retenu (même sans
        parenthèse : il sera alors signalé). Ailleurs, il doit être suivi d'une
        parenthèse, avec seulement une ponctuation ou une fréquence entre les
        deux, pour ne pas toucher à une phrase qui mentionne « 1H NMR ».
        """
        leading = None
        for match in self._label_re.finditer(text):
            paren = text.find("(", match.end())
            if paren >= 0 and _between_ok(text[match.end():paren]):
                return match
            if leading is None and not text[: match.start()].strip():
                leading = match
        return leading

    def applies(self, paragraph_text: str) -> bool:
        return self._find_label(nmr_common.normalize_spaces(paragraph_text)) is not None

    # ------------------------------------------------------------------ #
    # Application
    # ------------------------------------------------------------------ #
    def _flag_only(self, paragraph_text: str, message: str) -> RuleResult:
        return RuleResult(
            new_text=paragraph_text,
            actions=[Action(ActionKind.FLAGGED, message, self.name)],
        )

    def apply(self, paragraph_text: str) -> RuleResult:
        config = get_config()
        # normalize_spaces remplace caractère pour caractère : les positions
        # dans ``text`` et ``paragraph_text`` coïncident. Préfixe, suffixe et
        # replaced_text sont pris dans le texte ORIGINAL (avec ses \xa0) pour
        # que le document et le rapport restent identiques.
        text = nmr_common.normalize_spaces(paragraph_text)
        label_match = self._find_label(text)
        if label_match is None:
            return self._flag_only(
                paragraph_text, f"Section '{self.name}' introuvable : vérification manuelle requise."
            )

        seg_start, seg_end = nmr_common.section_span(text, label_match.start())
        segment = text[seg_start:seg_end]
        original_segment = paragraph_text[seg_start:seg_end]
        prefix = paragraph_text[:seg_start]
        suffix = paragraph_text[seg_end:]

        match = self._structure_re.match(segment)
        if not match:
            return self._flag_only(
                paragraph_text,
                f"Aucune parenthèse exploitable après '{self.name}' : "
                "vérification manuelle requise.",
            )
        between = match.group("between")
        if not _between_ok(between):
            return self._flag_only(
                paragraph_text,
                f"Texte non reconnu entre '{self.name}' et la parenthèse "
                f"('{between.strip()}') : vérification manuelle requise.",
            )

        inside = match.group("inside")
        actions: List[Action] = []

        # 1) Fréquence placée hors de la parenthèse -> déplacée à l'intérieur.
        freq = _BETWEEN_FREQ_RE.fullmatch(between)
        if freq:
            inside = f"{freq.group('freq')}, {inside.strip()}"
            actions.append(
                Action(
                    ActionKind.CORRECTED,
                    "Fréquence déplacée à l'intérieur de la parenthèse.",
                    self.name,
                )
            )

        # 2) Parenthèse à trois éléments.
        paren = nmr_common.normalize_parenthesis(inside, config)
        for kind, message in paren.actions:
            actions.append(Action(_KIND_MAP[kind], message, self.name))

        # 3) Label stylisé (exposant Unicode, mot d'entrée conservé).
        label_paren = f"{nmr_common.superscript_label(match.group('label'))} ({paren.text})"
        segments = [StyledSegment(label_paren, bold=config.bold_label)]
        segment_plain = label_paren

        # 4) Signaux après le delta.
        rest = match.group("rest")
        original_rest = original_segment[match.start("rest"):]
        located = nmr_common.locate_delta(rest)
        if located is None or not nmr_common.is_punctuation_only(located[0]):
            # Pas de delta, ou texte inconnu avant lui : la suite est
            # conservée telle quelle (aucun δ ajouté, rien supprimé).
            actions.append(
                Action(
                    ActionKind.FLAGGED,
                    "Liste de signaux introuvable (symbole δ absent ou précédé "
                    "d'un texte non reconnu) : suite laissée telle quelle, "
                    "vérification manuelle requise.",
                    self.name,
                )
            )
            if original_rest:
                segments.append(StyledSegment(original_rest))
                segment_plain += original_rest
        else:
            signals_text = self._signals_text(located[1], config, actions)
            segments += [
                StyledSegment(" "),
                StyledSegment(nmr_common.DELTA, italic=config.italic_delta),
            ]
            segment_plain += f" {nmr_common.DELTA}"
            if signals_text:
                segments += _signal_segments(f" {signals_text}", config.italic_j)
                segment_plain += f" {signals_text}"
            # Réinsère l'espace séparateur perdu avant une section collée.
            separator = nmr_common.section_separator(original_segment, suffix)
            if separator:
                segments.append(StyledSegment(separator))
                segment_plain += separator

        new_text = f"{prefix}{segment_plain}{suffix}"
        if new_text == paragraph_text:
            # Texte déjà conforme : les signalements (marqueur présent, signaux
            # non analysables…) restent valables et sont conservés.
            kept = [
                a for a in actions
                if a.kind in (ActionKind.FLAGGED, ActionKind.PLACEHOLDER)
            ]
            return RuleResult(
                new_text=paragraph_text,
                actions=kept
                or [Action(ActionKind.UNCHANGED, "Paragraphe déjà conforme.", self.name)],
            )
        if not actions:
            actions.append(Action(ActionKind.CORRECTED, "Paragraphe reformaté.", self.name))
        return RuleResult(
            new_text=new_text,
            actions=actions,
            segments=segments,
            replaced_text=original_segment,
        )

    def _signals_text(self, body: str, config, actions: List[Action]) -> str:
        """Trie et reformate les signaux, ou les laisse tels quels si non parsables."""
        body, terminal = nmr_common.split_trailing_punctuation(body)
        signals, all_parsable = nmr_common.parse_signals(body, config)
        if not all_parsable:
            # Règle de sûreté : liste conservée telle quelle, rien n'est réécrit.
            actions.append(
                Action(
                    ActionKind.FLAGGED,
                    "Un ou plusieurs signaux n'ont pas pu être analysés : "
                    "liste des signaux laissée telle quelle, vérification manuelle.",
                    self.name,
                )
            )
            return body + terminal
        ordered = nmr_common.sort_signals(signals, all_parsable, config)
        return ", ".join(self.format_signal(s) for s in ordered) + terminal
