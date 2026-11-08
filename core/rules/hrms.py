"""Règle de standardisation des entrées HRMS (sortie stylisée).

Format cible (usage ACS / J. Org. Chem.)::

    HRMS (<ionisation>) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0912.

- label et méthode d'ionisation en gras (``config.bold_label``), ``m/z`` en
  italique ;
- ion normalisé (``[M+H]+`` -> ``[M + H]⁺``, ``[M-H]-`` -> ``[M − H]⁻``,
  ``M+•`` -> ``[M]⁺•``) et placé avant ``Calcd for`` ;
- formule en indices Unicode ; ``calcd`` / ``found`` -> ``Calcd`` / ``Found``.

Les masses ne sont JAMAIS modifiées. La règle les vérifie seulement :

- la masse calculée est recalculée à partir de la formule (formule de l'ion
  OU formule neutre + ion, avec ou sans la masse de l'électron) ; incohérente
  -> FLAGGED avec la valeur attendue ;
- l'écart masse trouvée / calculée au-delà de ``config.hrms_ppm_tolerance``
  ppm -> FLAGGED.

Une entrée dont la structure n'est pas reconnue (virgule décimale, ordre
inhabituel, texte inconnu…) est laissée telle quelle et signalée.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

from core.config import get_config
from core.rules import mass, nmr_common
from core.rules.base import Action, ActionKind, Rule, RuleResult, StyledSegment

_SUPERSCRIPT_DIGITS = "⁰¹²³⁴⁵⁶⁷⁸⁹"
_TO_ASCII = str.maketrans(_SUPERSCRIPT_DIGITS + "₀₁₂₃₄₅₆₇₈₉", "0123456789" * 2)

# Fragment de formule (lettres, chiffres ASCII ou indices, parenthèses).
_FORMULA_CHAR = r"[A-Za-z0-9\u2080-\u2089()]"
_FORMULA = _FORMULA_CHAR + "+"
_PLUS = "+\u207a"            # + et ⁺
_MINUS = "\\-\u2212\u2013\u207b"  # -, −, – et ⁻


def _ion_pattern(named: bool) -> str:
    """Motif d'un ion (``[M + H]+``, ``[2M + Na]+``, ``[M − H]−``, ``M+•``)."""
    def g(name: str, body: str) -> str:
        return f"(?P<{name}>{body})" if named else f"(?:{body})"

    term = rf"\s*[{_PLUS}{_MINUS}]\s*\d*\s*[A-Z]{_FORMULA_CHAR}*"
    sign = rf"[{_PLUS}{_MINUS}]"
    # Ion moléculaire avec la charge DANS les crochets : (M+), [M+•], (M−).
    inner_charge = (
        r"[\[(]\s*M\s*" + g("rad_in", r"[•·]?") + r"\s*" + g("sign_in", sign)
        + r"\s*" + g("rad_in2", r"[•·]?") + r"\s*[\])]"
    )
    outer_charge = (
        r"(?:[\[(]\s*" + g("n", r"\d*") + r"\s*M" + g("terms", rf"(?:{term})*")
        + r"\s*[\])]|M)"
        + r"\s*" + g("rad1", r"[•·]?")
        + r"\s*" + g("z", rf"[0-9{_SUPERSCRIPT_DIGITS}]*")
        + r"\s*" + g("sign", sign)
        + g("rad2", r"[•·]?")
    )
    return f"(?:{inner_charge}|{outer_charge})"


_ION_RE = re.compile(_ion_pattern(True))
_ION = _ion_pattern(False)
_TERM_RE = re.compile(rf"([{_PLUS}{_MINUS}])\s*(\d*)\s*([A-Z]{_FORMULA_CHAR}*)")

# Structure complète d'une entrée HRMS, à partir du label.
_ENTRY_RE = re.compile(
    r"HRMS"
    r"\s*(?:\((?P<method>[^()]*)\))?"
    r"[\s:,]*"
    r"(?:m/z\s*:?\s*)?"
    rf"(?:(?P<ion1>{_ION})\s*[,:;]?\s*)?"
    r"(?i:calcd|calc|calculated)\.?\s+(?i:for)\s+"
    rf"(?P<formula>{_FORMULA})"
    rf"(?P<fcharge>[{_PLUS}{_MINUS}])?"
    rf"(?:\s*(?P<ion2>{_ION}))?"
    r"\s*[:,]?\s*(?:m/z\s*:?\s*)?"
    r"(?P<calcd>\d+\.\d+)"
    r"\s*[;,.]\s*"
    r"(?i:found)\s*:?\s*"
    r"(?P<found>\d+\.\d+)"
    r"(?P<end>\.(?!\d))?"
)

# Label HRMS isolé (pas au milieu d'un mot).
_LABEL_RE = re.compile(r"(?<![A-Za-z])HRMS(?![A-Za-z])")
# Indice qu'une mention de HRMS ouvre une vraie entrée de données.
_DATA_HINT_RE = re.compile(r"calc|found", re.IGNORECASE)


def _superscript(text: str) -> str:
    return "".join(_SUPERSCRIPT_DIGITS[int(c)] for c in text)


class _Ion:
    """Ion analysé : multiplicateur de M, termes ajoutés / retirés, charge."""

    def __init__(self, match: re.Match) -> None:
        self.n = int(match.group("n") or 1)
        self.terms: List[Tuple[int, int, str]] = []
        for sign, count, formula in _TERM_RE.findall(match.group("terms") or ""):
            self.terms.append(
                (1 if sign in _PLUS else -1, int(count or 1), formula.translate(_TO_ASCII))
            )
        magnitude = int((match.group("z") or "1").translate(_TO_ASCII) or 1)
        sign = match.group("sign") or match.group("sign_in")
        self.charge = magnitude if sign in _PLUS else -magnitude
        radicals = ("rad1", "rad2", "rad_in", "rad_in2")
        self.radical = "•" if any(match.group(r) for r in radicals) else ""

    def text(self) -> str:
        inner = ("" if self.n == 1 else str(self.n)) + "M"
        for sign, count, formula in self.terms:
            op = "+" if sign > 0 else "\u2212"
            num = "" if count == 1 else str(count)
            inner += f" {op} {num}{nmr_common.subscript_formula(formula)}"
        magnitude = abs(self.charge)
        charge = (_superscript(str(magnitude)) if magnitude > 1 else "") + (
            "\u207a" if self.charge > 0 else "\u207b"
        )
        return f"[{inner}]{charge}{self.radical}"


def _parse_ion(text: Optional[str]) -> Optional[_Ion]:
    if not text:
        return None
    match = _ION_RE.fullmatch(text.strip())
    return _Ion(match) if match else None


def _candidates(
    formula: str, ion: Optional[_Ion]
) -> Optional[List[Tuple[float, bool]]]:
    """Valeurs de m/z acceptables ``(m/z, électron compté)``, ou None si non calculable.

    Deux conventions d'écriture de la formule sont admises (formule de l'ion,
    ou formule neutre M combinée à l'ion), chacune avec ou sans la masse de
    l'électron. Sans ion connu, la formule est prise comme celle de l'ion,
    de charge ±1.
    """
    base = mass.monoisotopic_mass(formula)
    if base is None:
        return None
    charges = [ion.charge] if ion else [1, -1]
    values = []
    for charge in charges:
        for electron in (True, False):
            values.append((mass.ion_mz(base, charge, electron), electron))
            if ion:
                extra = mass.adduct_mass(ion.terms)
                if extra is not None:
                    values.append((mass.ion_mz(ion.n * base + extra, charge, electron), electron))
    return values


class HrmsRule(Rule):
    """Valide et standardise les entrées HRMS (sortie stylisée)."""

    name = "HRMS"
    description = (
        "Format ACS : HRMS (ionisation) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ "
        "165.0910; Found 165.0912. Masses jamais modifiées : masse calculée "
        "recalculée depuis la formule et écart en ppm vérifiés (signalés si "
        "incohérents)."
    )

    def _labels(self, text: str) -> List[re.Match]:
        found = []
        for match in _LABEL_RE.finditer(text):
            at_start = not text[: match.start()].strip()
            if at_start or _DATA_HINT_RE.search(text, match.end()):
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
            return RuleResult(
                new_text=paragraph_text,
                actions=[Action(
                    ActionKind.FLAGGED,
                    "Entrée HRMS non reconnue (ordre inhabituel, virgule décimale "
                    "ou texte inconnu) : laissée telle quelle, vérification manuelle.",
                    self.name,
                )],
            )

        flags: List[str] = []
        method = entry.group("method")
        if method is not None and method.strip():
            label = f"HRMS ({' '.join(method.split())})"
        else:
            label = "HRMS"
            flags.append("Méthode d'ionisation absente (ex. ESI, APCI, EI) : à compléter.")

        ion_text = entry.group("ion1") or entry.group("ion2")
        ion = _parse_ion(ion_text)
        if ion is None:
            flags.append("Ion absent (ex. [M + H]⁺) : à compléter.")

        formula_ascii = entry.group("formula").translate(_TO_ASCII)
        formula = nmr_common.subscript_formula(formula_ascii)
        fcharge = entry.group("fcharge")
        if fcharge:
            formula += "\u207a" if fcharge in _PLUS else "\u207b"

        calcd, found = entry.group("calcd"), entry.group("found")
        flags += self._check(formula_ascii, ion, calcd, found, config.hrms_ppm_tolerance)

        body = (
            (f"{ion.text()} " if ion else "")
            + f"Calcd for {formula} {calcd}; Found {found}"
            + (entry.group("end") or "")
        )
        segments = [
            StyledSegment(label, bold=config.bold_label),
            StyledSegment(" "),
            StyledSegment("m/z", italic=True),
            StyledSegment(f": {body}"),
        ]
        start, end = entry.span()
        new_segment = "".join(s.text for s in segments)
        new_text = paragraph_text[:start] + new_segment + paragraph_text[end:]
        actions = [Action(ActionKind.FLAGGED, f, self.name) for f in flags]
        if new_text == paragraph_text:
            return RuleResult(
                new_text=paragraph_text,
                actions=actions or [Action(ActionKind.UNCHANGED, "Entrée déjà conforme.", self.name)],
            )
        actions.insert(0, Action(ActionKind.CORRECTED, "Entrée HRMS reformatée.", self.name))
        return RuleResult(
            new_text=new_text,
            actions=actions,
            segments=segments,
            replaced_text=paragraph_text[start:end],
        )

    @staticmethod
    def _check(
        formula: str, ion: Optional[_Ion], calcd: str, found: str, tolerance: float
    ) -> List[str]:
        """Vérifie la masse calculée et l'écart en ppm (messages FLAGGED)."""
        flags: List[str] = []
        calcd_value, found_value = float(calcd), float(found)
        decimals = len(calcd.split(".")[1])
        candidates = _candidates(formula, ion)
        if candidates is None:
            flags.append(
                "Formule non calculable (élément inconnu ou formule illisible) : "
                f"{nmr_common.subscript_formula(formula)}, masse calculée à vérifier manuellement."
            )
        else:
            margin = 0.5 * 10 ** -decimals + 5e-6
            if all(abs(c - calcd_value) > margin for c, _ in candidates):
                # Valeur proposée : convention exacte (électron compté).
                closest = min(
                    (c for c, electron in candidates if electron),
                    key=lambda c: abs(c - calcd_value),
                )
                shown = nmr_common.subscript_formula(formula)
                flags.append(
                    "Masse calculée incohérente avec la formule : "
                    f"{calcd} écrit, {closest:.{decimals}f} attendu pour {shown} ; "
                    "valeur conservée, vérification manuelle requise."
                )
        ppm = abs(found_value - calcd_value) / calcd_value * 1e6
        if ppm > tolerance:
            flags.append(
                "Écart masse trouvée / calculée hors tolérance : "
                f"{ppm:.1f} ppm (tolérance {tolerance:g} ppm), vérification "
                "manuelle requise."
            )
        return flags
