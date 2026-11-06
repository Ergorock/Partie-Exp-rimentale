"""Logique commune aux règles RMN (1H et 13C).

Ce module regroupe les helpers partagés par les règles ``1H NMR`` et
``13C NMR`` afin d'éviter la duplication :

- conversion des chiffres en exposants / indices Unicode ;
- normalisation des espaces (insécables) ;
- normalisation de la parenthèse à trois éléments
  (fréquence MHz, solvant, température K), avec insertion du marqueur
  ``[??? K]`` si la température manque ;
- délimitation du segment d'une section RMN dans un paragraphe qui en
  contient plusieurs collées (``1H NMR … 13C NMR … 19F{1H} NMR …``) ;
- parsing, tri (du déplacement le plus grand au plus petit, avec règle de
  sûreté) et formatage des signaux.

Conventions de décision utilisateur appliquées ici :

- les exposants et indices sont écrits en Unicode (jamais en superscript
  Word) ;
- le mot d'entrée (``NMR`` ou ``RMN``) est conservé tel quel : on n'ajoute que
  l'exposant Unicode au chiffre du noyau et le gras au niveau de la règle ;
- aucune chimie n'est inventée ; le tri n'est effectué que si TOUS les signaux
  sont parsables, sinon on ne réordonne pas et la règle émet une action
  FLAGGED.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

# Marqueur inséré lorsqu'une température est attendue mais introuvable.
TEMPERATURE_PLACEHOLDER = "[??? K]"

# Symbole delta standard produit en sortie (italique géré par la règle).
DELTA = "\u03b4"  # δ

# Variantes de delta acceptées en entrée : δ (U+03B4) et ẟ (U+1E9F).
_DELTA_VARIANTS = "\u03b4\u1e9f"

# Un nombre (entier ou décimal), éventuellement signé.
_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")

# Tables de conversion chiffre -> exposant / indice Unicode.
_SUPERSCRIPTS = {
    "0": "\u2070", "1": "\u00b9", "2": "\u00b2", "3": "\u00b3", "4": "\u2074",
    "5": "\u2075", "6": "\u2076", "7": "\u2077", "8": "\u2078", "9": "\u2079",
}
_SUBSCRIPTS = {
    "0": "\u2080", "1": "\u2081", "2": "\u2082", "3": "\u2083", "4": "\u2084",
    "5": "\u2085", "6": "\u2086", "7": "\u2087", "8": "\u2088", "9": "\u2089",
}


def to_superscript(digits: str) -> str:
    """Convertit une suite de chiffres en exposants Unicode (``13`` -> ``¹³``)."""
    return "".join(_SUPERSCRIPTS.get(c, c) for c in digits)


def subscript_formula(text: str) -> str:
    """Met en indices Unicode les chiffres suivant une lettre dans un token chimique.

    Exemples : ``CDCl3`` -> ``CDCl₃``, ``CH2`` -> ``CH₂``. On ne convertit que
    les chiffres qui suivent immédiatement une lettre (indices stœchiométriques)
    pour ne pas toucher aux nombres isolés (déplacements, intégrations).
    """
    def repl(match: re.Match) -> str:
        return "".join(_SUBSCRIPTS[c] for c in match.group(0))

    return re.sub(r"(?<=[A-Za-z])\d+", repl, text)


def normalize_spaces(text: str) -> str:
    """Remplace les espaces insécables (``\\xa0``) par des espaces ordinaires."""
    return text.replace("\xa0", " ")


# --------------------------------------------------------------------------- #
# Label et exposant du noyau
# --------------------------------------------------------------------------- #

def superscript_label(label: str) -> str:
    """Transforme un label d'entrée en label à exposant Unicode.

    Le mot ``NMR`` / ``RMN`` et le symbole de l'élément sont conservés tels
    quels : seul le nombre de masse en tête (``1``, ``13``, ``19``…) passe en
    exposant Unicode. Exemples : ``1H NMR`` -> ``¹H NMR``,
    ``13C RMN`` -> ``¹³C RMN``, ``19F{1H} NMR`` -> ``¹⁹F{¹H} NMR``.
    """
    label = normalize_spaces(label).strip()
    # Nombre de masse initial -> exposant.
    label = re.sub(r"^(\d+)", lambda m: to_superscript(m.group(1)), label)
    # Nombres de masse à l'intérieur d'accolades (ex. {1H}).
    label = re.sub(
        r"\{(\d+)",
        lambda m: "{" + to_superscript(m.group(1)),
        label,
    )
    return label


# --------------------------------------------------------------------------- #
# Délimitation du segment d'une section RMN
# --------------------------------------------------------------------------- #

# Motif d'un label de section RMN : nombre(s) + élément + accolade optionnelle
# + espace + ('NMR' | 'RMN'). Accepte l'entrée classique ('13C NMR') comme la
# forme déjà stylisée en exposants ('¹³C NMR').
_SECTION_LABEL_RE = re.compile(
    r"[0-9\u2070\u00b9\u00b2\u00b3\u2074-\u2079]+"  # nombre de masse (ascii ou exposant)
    r"[A-Za-z]+"                                     # symbole de l'élément
    r"(?:\{[^}]*\})?"                                # couplage optionnel {1H}
    r"\s*(?:NMR|RMN)\b",
    re.IGNORECASE,
)


def section_span(text: str, start: int = 0) -> Tuple[int, int]:
    """Délimite le segment de la section RMN qui commence à ``start``.

    Le segment court du label de section situé à ``start`` jusqu'au début du
    prochain label de section RMN (``13C NMR``, ``19F{1H} NMR``, ``31P RMN``…),
    ou jusqu'à la fin du texte s'il n'y en a pas d'autre. Permet à chaque règle
    de ne traiter QUE son segment en laissant le reste du paragraphe intact.

    Args:
        text: le texte du paragraphe.
        start: position du label de la section courante (début du segment).

    Returns:
        Le couple ``(start, end)`` délimitant le segment (``end`` exclu).
    """
    # On cherche le prochain label de section strictement après celui de départ.
    first = _SECTION_LABEL_RE.match(text, start)
    search_from = first.end() if first else start + 1
    nxt = _SECTION_LABEL_RE.search(text, search_from)
    end = nxt.start() if nxt else len(text)
    return start, end


def section_separator(segment: str, suffix: str) -> str:
    """Retourne l'espace à réinsérer entre un segment reformaté et la suite.

    Quand un paragraphe contient plusieurs sections RMN collées, le segment
    reformaté est reconstruit à partir de ses éléments et perd l'espace qui le
    séparait de la section suivante dans le texte d'origine. Pour éviter un
    collage disgracieux (``2H)13C NMR``), on réinsère un espace unique dès lors
    que le segment d'origine se terminait par un espace et que le suffixe
    commence par un caractère non-espace.

    Args:
        segment: le segment de section d'origine (avant reformatage).
        suffix: le reste du paragraphe qui suit le segment.

    Returns:
        ``" "`` si un espace séparateur doit être réinséré, ``""`` sinon.
    """
    if not suffix:
        return ""
    segment_had_trailing_space = segment != segment.rstrip()
    suffix_starts_without_space = suffix[:1] not in (" ", "\t", "\n")
    if segment_had_trailing_space and suffix_starts_without_space:
        return " "
    return ""


# --------------------------------------------------------------------------- #
# Parenthèse à trois éléments (fréquence, solvant, température)
# --------------------------------------------------------------------------- #

@dataclass
class ParenResult:
    """Résultat de la normalisation de la parenthèse d'une section RMN."""

    text: str  # contenu normalisé de la parenthèse (sans les parenthèses)
    actions: List[Tuple[str, str]]  # (kind, message) à transformer en Action


def _normalize_frequency(freq: str) -> Tuple[str, bool]:
    """Normalise l'élément fréquence vers ``<nombre> MHz``."""
    original = freq
    freq = freq.strip()
    freq = re.sub(r"(\d)\s*(MHz)", r"\1 \2", freq, flags=re.IGNORECASE)
    freq = re.sub(r"\bmhz\b", "MHz", freq, flags=re.IGNORECASE)
    if re.fullmatch(r"\d+(?:\.\d+)?", freq):
        freq = f"{freq} MHz"
    freq = re.sub(r"\s+", " ", freq).strip()
    return freq, freq != original.strip()


def _normalize_temperature(temp: str) -> Tuple[str, bool]:
    """Normalise l'élément température vers ``<nombre> K``."""
    original = temp
    temp = temp.strip()
    number = re.search(r"\d+(?:\.\d+)?", temp)
    if not number:
        return temp, False
    normalized = f"{number.group()} K"
    return normalized, normalized != original.strip()


def normalize_parenthesis(inside: str) -> ParenResult:
    """Normalise le contenu d'une parenthèse de section RMN à trois éléments.

    Attend ``fréquence, solvant, température`` séparés par deux virgules :

    - la fréquence est normalisée en ``<nombre> MHz`` ;
    - le solvant passe en indices Unicode (``CDCl3`` -> ``CDCl₃``) ;
    - la température est normalisée en ``<nombre> K`` ; absente ou illisible,
      le marqueur ``[??? K]`` est inséré ;
    - une parenthèse à moins de deux éléments est signalée (FLAGGED) ;
    - un nombre d'éléments supérieur à trois est signalé.

    Args:
        inside: le contenu de la parenthèse (sans les parenthèses).

    Returns:
        Un ``ParenResult`` : texte normalisé + actions (kind, message).
    """
    actions: List[Tuple[str, str]] = []
    elements = [e.strip() for e in inside.split(",")]

    # Fréquence (1er élément).
    if elements and elements[0]:
        new_freq, changed = _normalize_frequency(elements[0])
        if changed:
            actions.append(
                ("corrected", f"Fréquence normalisée : '{elements[0]}' -> '{new_freq}'.")
            )
        elements[0] = new_freq

    # Solvant (2e élément) -> indices Unicode.
    if len(elements) >= 2 and elements[1]:
        new_solvent = subscript_formula(elements[1])
        if new_solvent != elements[1]:
            actions.append(
                ("corrected", f"Solvant en indices Unicode : '{elements[1]}' -> '{new_solvent}'.")
            )
        elements[1] = new_solvent

    # Température (3e élément).
    if len(elements) >= 3:
        if not re.search(r"\d+(?:\.\d+)?", elements[2]):
            elements[2] = TEMPERATURE_PLACEHOLDER
            actions.append(("placeholder", "Température illisible : marqueur inséré."))
        else:
            new_temp, changed = _normalize_temperature(elements[2])
            if changed:
                actions.append(
                    ("corrected", f"Température normalisée : '{elements[2]}' -> '{new_temp}'.")
                )
            elements[2] = new_temp
        if len(elements) > 3:
            actions.append(
                ("flagged", f"La parenthèse contient {len(elements)} éléments au lieu de 3.")
            )
    elif len(elements) == 2:
        elements.append(TEMPERATURE_PLACEHOLDER)
        actions.append(
            ("placeholder", "Température absente : marqueur '[??? K]' inséré.")
        )
    else:
        actions.append(
            ("flagged", "Parenthèse incomplète (moins de 2 éléments) : vérification manuelle requise.")
        )

    return ParenResult(text=", ".join(elements), actions=actions)


# --------------------------------------------------------------------------- #
# Delta : détection en entrée
# --------------------------------------------------------------------------- #

# Capture le delta d'entrée (δ ou ẟ) suivi d'un éventuel '(ppm)' et '=' avant
# la liste des signaux. Le groupe 'body' est la liste brute des signaux.
_DELTA_RE = re.compile(
    rf"[{_DELTA_VARIANTS}]\s*(?:\(ppm\))?\s*=?\s*(?P<body>.*)$",
    re.DOTALL,
)


def split_delta_body(after_paren: str) -> Optional[str]:
    """Isole la liste des signaux après le delta.

    ``after_paren`` est le texte qui suit la parenthèse de section (ex.
    ``': ẟ (ppm) = 9.18 (dd, …), 8.90 (m, 2H)'``). Retourne le corps brut des
    signaux (après le delta), ou ``None`` si aucun delta n'est trouvé.
    """
    match = _DELTA_RE.search(after_paren)
    if not match:
        return None
    return match.group("body").strip()


# --------------------------------------------------------------------------- #
# Parsing / tri / formatage des signaux
# --------------------------------------------------------------------------- #

# Multiplicités autorisées (ordre important : les plus longues d'abord pour le
# matching). 'bs' est accepté en entrée et normalisé en 'br s'.
_MULTIPLICITIES = {
    "br s": "br s",
    "bs": "br s",
    "dd": "dd",
    "quint": "quint",
    "septic": "septic",
    "s": "s",
    "d": "d",
    "t": "t",
    "q": "q",
    "m": "m",
}


@dataclass
class Signal:
    """Un signal RMN parsé."""

    shift: str  # déplacement chimique : valeur unique OU plage 'a-b'
    shift_high: float  # borne haute numérique (pour le tri)
    multiplicity: Optional[str] = None  # normalisée (None pour le 13C simple)
    j: Optional[str] = None  # constante de couplage brute (ex '4.7')
    integration: Optional[str] = None  # ex '2H'
    attribution: Optional[str] = None  # texte libre (attribution)


def _split_top_level(body: str) -> List[str]:
    """Découpe une liste de signaux sur les virgules de premier niveau.

    Les virgules à l'intérieur des parenthèses (ex. ``(dd, J = 4.7 Hz, 2H)``)
    ne sont pas des séparateurs de signaux. On ignore donc les virgules dont la
    profondeur de parenthèses est > 0.
    """
    parts: List[str] = []
    depth = 0
    current = ""
    for ch in body:
        if ch in "([":
            depth += 1
            current += ch
        elif ch in ")]":
            depth = max(0, depth - 1)
            current += ch
        elif ch == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current)
    return [p.strip() for p in parts if p.strip()]


# Déplacement chimique : valeur unique ou plage 'a-b' / 'a–b'.
_SHIFT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)(?:\s*[-\u2013]\s*(-?\d+(?:\.\d+)?))?")

# Contenu optionnel entre parenthèses à la fin d'un signal.
_PAREN_RE = re.compile(r"\(([^)]*)\)\s*$")

# Constante de couplage dans un contenu de parenthèse.
_J_RE = re.compile(r"J\s*=\s*(-?\d+(?:\.\d+)?)\s*Hz", re.IGNORECASE)

# Intégration (ex '2H', '1H', '3F').
_INTEG_RE = re.compile(r"\b(\d+\s*[A-Za-z])\b")


def _parse_multiplicity(token: str) -> Optional[str]:
    """Reconnaît une multiplicité autorisée dans un token, ou None."""
    token = token.strip().lower()
    return _MULTIPLICITIES.get(token)


def parse_signals(body: str) -> Tuple[List[Signal], bool]:
    """Parse la liste des signaux d'une section RMN.

    Args:
        body: liste brute des signaux (après le delta).

    Returns:
        ``(signaux, all_parsable)`` où ``all_parsable`` est ``False`` dès qu'un
        signal n'a pas pu être parsé proprement (déplacement illisible).
    """
    raw_signals = _split_top_level(body)
    signals: List[Signal] = []
    all_parsable = bool(raw_signals)

    for raw in raw_signals:
        shift_match = _SHIFT_RE.match(raw)
        if not shift_match:
            all_parsable = False
            signals.append(Signal(shift=raw, shift_high=float("-inf")))
            continue

        low = shift_match.group(1)
        high = shift_match.group(2)
        if high is not None:
            shift_text = f"{low}\u2013{high}"  # tiret demi-cadratin
            shift_high = max(float(low), float(high))
        else:
            shift_text = low
            shift_high = float(low)

        rest = raw[shift_match.end():].strip()
        multiplicity = None
        j = None
        integration = None
        attribution = None

        paren_match = _PAREN_RE.search(rest)
        if paren_match:
            inner = paren_match.group(1)
            fields = [f.strip() for f in inner.split(",")]
            remaining_fields: List[str] = []
            for field in fields:
                mult = _parse_multiplicity(field)
                jm = _J_RE.search(field)
                if mult and multiplicity is None:
                    multiplicity = mult
                elif jm and j is None:
                    j = jm.group(1)
                elif integration is None and _INTEG_RE.fullmatch(field.replace(" ", "")):
                    integration = field.replace(" ", "")
                else:
                    remaining_fields.append(field)
            if remaining_fields:
                attribution = ", ".join(remaining_fields)

        signals.append(
            Signal(
                shift=shift_text,
                shift_high=shift_high,
                multiplicity=multiplicity,
                j=j,
                integration=integration,
                attribution=attribution,
            )
        )

    return signals, all_parsable


def sort_signals(signals: List[Signal], all_parsable: bool) -> List[Signal]:
    """Trie les signaux du déplacement le plus grand au plus petit.

    Le tri n'a lieu que si ``all_parsable`` est vrai (règle de sûreté : on ne
    réordonne jamais une liste dont un signal n'a pas pu être compris). Pour une
    plage, la borne haute sert de clé.
    """
    if not all_parsable:
        return signals
    return sorted(signals, key=lambda s: s.shift_high, reverse=True)


def format_signal_1h(signal: Signal) -> str:
    """Formate un signal 1H : déplacement, multiplicité, J, intégration, attribution."""
    parts: List[str] = []
    if signal.multiplicity:
        parts.append(signal.multiplicity)
    if signal.j:
        parts.append(f"J = {signal.j} Hz")
    if signal.integration:
        parts.append(signal.integration)
    if signal.attribution:
        parts.append(subscript_formula(signal.attribution))
    if parts:
        return f"{signal.shift} ({', '.join(parts)})"
    return signal.shift


def format_signal_13c(signal: Signal) -> str:
    """Formate un signal 13C : déplacement (+ attribution / J entre parenthèses).

    Le carbone est généralement découplé (singulet) : on indique le déplacement
    puis l'attribution optionnelle entre parenthèses. La constante ``J`` est
    conservée si un couplage est présent (ex. couplage F/P).
    """
    parts: List[str] = []
    if signal.j:
        parts.append(f"J = {signal.j} Hz")
    if signal.integration:
        parts.append(signal.integration)
    if signal.attribution:
        parts.append(subscript_formula(signal.attribution))
    if parts:
        return f"{signal.shift} ({', '.join(parts)})"
    return signal.shift
