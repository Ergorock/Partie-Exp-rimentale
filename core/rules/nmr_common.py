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
from dataclasses import dataclass, field
from typing import List, Optional, Tuple

from core.config import RmnConfig, get_config

# Symbole delta standard produit en sortie (italique géré par la règle).
DELTA = "\u03b4"  # δ
# Espace insécable : entre un nombre et son unité / son symbole (``5 H``) et
# autour du tiret demi-cadratin d'une plage (``7.41 – 7.50``).
NBSP = "\u00a0"
RANGE_SEP = f"{NBSP}\u2013{NBSP}"

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

    Exemples : ``CDCl3`` -> ``CDCl₃``, ``CH2`` -> ``CH₂``,
    ``(CD3)2SO`` -> ``(CD₃)₂SO``. On ne convertit que les chiffres qui suivent
    immédiatement une lettre ou une parenthèse fermante (indices
    stœchiométriques) pour ne pas toucher aux nombres isolés (déplacements,
    intégrations).
    """
    def repl(match: re.Match) -> str:
        return "".join(_SUBSCRIPTS[c] for c in match.group(0))

    return re.sub(r"(?<=[A-Za-z)])\d+", repl, text)


# Token d'attribution : suite de lettres, chiffres, parenthèses et primes.
_ATTRIBUTION_TOKEN_RE = re.compile(r"[A-Za-z0-9()'′″]+")

# Numéro de position : UN symbole d'élément suivi d'un numéro, éventuellement
# d'une lettre minuscule et de primes (``H4``, ``C3``, ``C4'``, ``H4a``). Ce
# n'est pas une formule : il ne faut pas le mettre en indice.
_POSITION_RE = re.compile(r"[A-Z][a-z]?\d+[a-z]?['′″]*")


def subscript_attribution(text: str) -> str:
    """Met en indices les groupes chimiques d'une attribution, pas les positions.

    ``OCH3`` -> ``OCH₃`` et ``N(CH3)2`` -> ``N(CH₃)₂``, mais ``H4``, ``C3`` ou
    ``C4'`` (numérotation des atomes) restent inchangés.
    """
    def repl(match: re.Match) -> str:
        token = match.group(0)
        if _POSITION_RE.fullmatch(token):
            return token
        return subscript_formula(token)

    return _ATTRIBUTION_TOKEN_RE.sub(repl, text)


# Jeton qui n'est PAS une formule (C18, F254, UV254) : jamais mis en indice.
_NOT_FORMULA_RE = re.compile(r"[A-Z]{1,2}\d{2,3}")
_TOKEN_RE = re.compile(r"[A-Za-z0-9()]+")


def subscript_text(text: str) -> str:
    """Indices Unicode des formules d'un texte libre (éluant, solvant…).

    Comme ``subscript_formula`` mais jeton par jeton, sans toucher à ``C18`` /
    ``F254`` / ``UV254`` (lettres + 2 ou 3 chiffres : ce ne sont pas des
    formules).
    """

    def repl(match: re.Match) -> str:
        token = match.group(0)
        if _NOT_FORMULA_RE.fullmatch(token):
            return token
        return subscript_formula(token)

    return _TOKEN_RE.sub(repl, text)


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
    # Séparateur avant le mot d'entrée normalisé en une espace
    # ('1H-NMR' / '1HNMR' -> '1H NMR') ; le mot lui-même est conservé.
    label = re.sub(r"[\s\-–]*(NMR|RMN)$", r" \1", label, flags=re.IGNORECASE)
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
    r"[\s\-–]*(?:NMR|RMN)\b",                   # séparateur : espace ou tiret
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
    # On cherche le prochain label de section (RMN ou autre analyse)
    # strictement après celui de départ.
    first = _SECTION_LABEL_RE.match(text, start)
    search_from = first.end() if first else start + 1
    ends = [
        nxt.start()
        for pattern in (_SECTION_LABEL_RE, _OTHER_ANALYSIS_RE)
        for nxt in [pattern.search(text, search_from)]
        if nxt
    ]
    return start, min(ends, default=len(text))


# Label d'une autre analyse qui termine une section RMN collée devant elle
# (``… δ 77.0. HRMS (ESI) …``). À compléter pour chaque nouvelle règle.
# Motifs stricts (pas de lettre collée) pour ne pas couper une attribution.
_OTHER_ANALYSIS_RE = re.compile(
    r"(?<![A-Za-z])(?:(?:HRMS|IR|Rf)(?![A-Za-z])|[mMbB]\.?\s?[pP]\.?(?=\s*[:=]?\s*\d))"
)


def next_analysis_start(text: str, search_from: int) -> int:
    """Position du prochain label d'analyse (RMN ou autre) après ``search_from``.

    Retourne ``len(text)`` s'il n'y en a pas. Sert aux règles à structure fixe
    (IR…) pour délimiter leur segment dans un paragraphe qui en contient
    plusieurs collés.
    """
    ends = [
        nxt.start()
        for pattern in (_SECTION_LABEL_RE, _OTHER_ANALYSIS_RE)
        for nxt in [pattern.search(text, search_from)]
        if nxt
    ]
    return min(ends, default=len(text))


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

#: Pièce de texte stylisée : (texte, italique).
Piece = Tuple[str, bool]

#: Début (partie fixe, avant ``' : '``) du signalement d'un solvant hors table.
UNKNOWN_SOLVENT_MESSAGE = "Solvant absent de la table"


def parse_solvent_markup(markup: str) -> List[Piece]:
    """Découpe un balisage de solvant en pièces (texte, italique).

    ``*…*`` met en italique ; les marqueurs ne figurent jamais dans le texte.
    Les indices Unicode sont appliqués sur le texte COMPLET (un chiffre en
    début de pièce suit la lettre de la pièce précédente : ``DMSO-*d*6`` ->
    ``DMSO-`` + *d* + ``₆``) puis le résultat est redécoupé. Un nombre impair
    de ``*`` est traité littéralement (aucune pièce en italique).
    """
    if markup.count("*") % 2:
        return [(subscript_formula(markup), False)]
    plain: List[str] = []
    italic: List[bool] = []
    state = False
    for char in markup:
        if char == "*":
            state = not state
            continue
        plain.append(char)
        italic.append(state)
    # Remplacement caractère pour caractère : les positions restent valables.
    text = subscript_formula("".join(plain))
    pieces: List[Piece] = []
    for char, flag in zip(text, italic):
        if pieces and pieces[-1][1] == flag:
            pieces[-1] = (pieces[-1][0] + char, flag)
        else:
            pieces.append((char, flag))
    return pieces


def lookup_solvent(element: str, config: Optional[RmnConfig] = None) -> Optional[List[Piece]]:
    """Pièces de sortie du solvant ``element`` d'après la table, ou ``None``.

    Correspondance sur l'élément entier, insensible à la casse et aux espaces
    multiples. La forme DÉJÀ rendue (``DMSO-d₆``) est aussi reconnue, pour
    l'idempotence.
    """
    config = config or get_config()
    key = " ".join(element.split()).lower()
    if not key:
        return None
    markup = config.solvents.get(key)
    if markup is not None:
        return parse_solvent_markup(markup)
    for candidate in config.solvents.values():
        pieces = parse_solvent_markup(candidate)
        if "".join(text for text, _ in pieces).lower() == key:
            return pieces
    return None


@dataclass
class ParenResult:
    """Résultat de la normalisation de la parenthèse d'une section RMN."""

    text: str  # contenu normalisé de la parenthèse (sans les parenthèses)
    actions: List[Tuple[str, str]]  # (kind, message) à transformer en Action
    #: Pièces stylisées du solvant (2e élément) s'il figure dans la table.
    solvent_pieces: Optional[List[Piece]] = None
    #: Solvant (2e élément) signalé comme absent de la table (pour le surlignage).
    unknown_solvent: Optional[str] = None


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


# Unité de température explicitement écrite dans l'entrée.
_CELSIUS_RE = re.compile(r"[°º˚]\s*C|\d\s*C\b", re.IGNORECASE)  # °C, ºC, ˚C, 25C
_KELVIN_RE = re.compile(r"\d\s*K\b|\bK\b", re.IGNORECASE)


def temperature_unit_of(temp: str) -> Optional[str]:
    """Retourne l'unité écrite dans l'élément température (``'K'`` / ``'°C'``), ou None."""
    if _CELSIUS_RE.search(temp):
        return "°C"
    if _KELVIN_RE.search(temp):
        return "K"
    return None


def _normalize_temperature(
    temp: str, config: Optional[RmnConfig] = None
) -> Tuple[str, bool]:
    """Normalise l'élément température vers ``<nombre> <unité>``.

    L'unité est lue dans la configuration (``config.temperature_unit``). La
    valeur numérique (signe compris) n'est jamais convertie : l'appelant doit
    vérifier au préalable que l'unité éventuellement écrite dans l'entrée est
    bien l'unité configurée (voir ``normalize_parenthesis``).
    """
    config = config or get_config()
    original = temp
    temp = temp.strip()
    number = re.search(r"-?\d+(?:\.\d+)?", temp)
    if not number:
        return temp, False
    normalized = f"{number.group()} {config.temperature_unit}"
    return normalized, normalized != original.strip()


def normalize_parenthesis(
    inside: str, config: Optional[RmnConfig] = None
) -> ParenResult:
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
    config = config or get_config()
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

    # Solvant (2e élément) : table configurée (remplacement, indices, italique) ;
    # absent de la table -> indices automatiques + signalement, sans remplacement.
    solvent_pieces: Optional[List[Piece]] = None
    unknown_solvent: Optional[str] = None
    if len(elements) >= 2 and elements[1]:
        solvent_pieces = lookup_solvent(elements[1], config)
        if solvent_pieces is not None:
            new_solvent = "".join(text for text, _ in solvent_pieces)
        else:
            new_solvent = subscript_formula(elements[1])
            unknown_solvent = new_solvent
            actions.append(
                (
                    "flagged",
                    f"{UNKNOWN_SOLVENT_MESSAGE} : {new_solvent} ; "
                    "vérification manuelle requise.",
                )
            )
        if new_solvent != elements[1]:
            # Seuls les indices changent : message historique ; sinon la table
            # a remplacé la chaîne écrite.
            label = (
                "Solvant en indices Unicode"
                if new_solvent == subscript_formula(elements[1])
                else "Solvant remplacé"
            )
            actions.append(("corrected", f"{label} : '{elements[1]}' -> '{new_solvent}'."))
        elements[1] = new_solvent

    # Température (3e élément). Contrôle désactivé (``check_temperature``) :
    # l'élément est laissé tel quel (ni marqueur, ni unité, ni signalement) ;
    # seule la structure de la parenthèse reste vérifiée.
    if not config.check_temperature:
        if len(elements) > 3:
            actions.append(
                ("flagged", f"La parenthèse contient {len(elements)} éléments au lieu de 3.")
            )
        elif len(elements) < 2:
            actions.append(
                ("flagged", "Parenthèse incomplète (moins de 2 éléments) : vérification manuelle requise.")
            )
    elif len(elements) >= 3:
        if elements[2] == config.temperature_placeholder:
            # Marqueur déjà présent (document déjà traité) : toujours à compléter.
            actions.append(
                ("placeholder", f"Température manquante : marqueur '{elements[2]}' à compléter.")
            )
        elif not re.search(r"\d+(?:\.\d+)?", elements[2]):
            elements[2] = config.temperature_placeholder
            actions.append(("placeholder", "Température illisible : marqueur inséré."))
        elif (
            temperature_unit_of(elements[2]) is not None
            and temperature_unit_of(elements[2]) != config.temperature_unit
        ):
            # Unité écrite différente de l'unité configurée : on ne réétiquette
            # pas la valeur (ce serait une donnée fausse) et on ne convertit pas.
            actions.append(
                (
                    "flagged",
                    f"Température '{elements[2]}' exprimée en "
                    f"{temperature_unit_of(elements[2])} alors que l'unité configurée "
                    f"est {config.temperature_unit} : laissée telle quelle, "
                    "vérification manuelle requise.",
                )
            )
        else:
            new_temp, changed = _normalize_temperature(elements[2], config)
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
        elements.append(config.temperature_placeholder)
        actions.append(
            ("placeholder", f"Température absente : marqueur '{config.temperature_placeholder}' inséré.")
        )
    else:
        actions.append(
            ("flagged", "Parenthèse incomplète (moins de 2 éléments) : vérification manuelle requise.")
        )

    return ParenResult(
        text=", ".join(elements),
        actions=actions,
        solvent_pieces=solvent_pieces,
        unknown_solvent=unknown_solvent,
    )


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
    located = locate_delta(after_paren)
    return None if located is None else located[1]


# Texte toléré entre la parenthèse de section et le delta (ponctuation seule).
_BEFORE_DELTA_RE = re.compile(r"[\s:;,.=\-–]*")


def locate_delta(after_paren: str) -> Optional[Tuple[str, str]]:
    """Localise le delta : retourne ``(texte_avant_delta, corps_des_signaux)``.

    Retourne ``None`` si aucun delta n'est trouvé.
    """
    match = _DELTA_RE.search(after_paren)
    if not match:
        return None
    return after_paren[: match.start()], match.group("body").strip()


def is_punctuation_only(text: str) -> bool:
    """Vrai si ``text`` ne contient que des espaces / ponctuation (``': '``…)."""
    return bool(_BEFORE_DELTA_RE.fullmatch(text))


# --------------------------------------------------------------------------- #
# Parsing / tri / formatage des signaux
# --------------------------------------------------------------------------- #

# Champ qui ressemble à une multiplicité (td, dt, ddd, dq, sext…) sans figurer
# dans la table configurée : on ne sait pas l'interpréter, le signal devient
# non parsable (l'utilisateur peut l'ajouter dans les paramètres).
_MULTIPLICITY_LIKE_RE = re.compile(
    r"(?:br\.?\s*)?(?:[sdtqm]+|quint(?:et)?|sext(?:et)?|sept(?:et)?|hept(?:et)?|septic)"
)


@dataclass
class Signal:
    """Un signal RMN parsé."""

    shift: str  # déplacement chimique : valeur unique OU plage 'a-b'
    shift_high: float  # borne haute numérique (pour le tri)
    multiplicity: Optional[str] = None  # normalisée (None pour le 13C simple)
    j: Optional[str] = None  # constante(s) de couplage brute(s) (ex '4.7' ou '8.4, 2.1')
    extra_j: List[str] = field(default_factory=list)  # champs 'J = … Hz' suivants
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


# Signe moins accepté devant un déplacement : trait d'union, signe moins
# Unicode (U+2212) ou tiret demi-cadratin (souvent inséré par Word). Le signe
# est conservé tel qu'écrit en sortie.
_MINUS = r"\-" + "\u2212\u2013"

# Déplacement chimique : valeur unique ou plage 'a-b' / 'a–b'.
_SHIFT_RE = re.compile(
    rf"^\s*([{_MINUS}]?\d+(?:\.\d+)?)"
    rf"(?:\s*[-\u2013]\s*([{_MINUS}]?\d+(?:\.\d+)?))?"
)


def _to_float(value: str) -> float:
    """Valeur numérique d'un déplacement, quel que soit le signe moins écrit."""
    return float(re.sub(rf"^[{_MINUS}]", "-", value))


# Après le déplacement, un signal ne peut contenir qu'une parenthèse simple
# (sans parenthèse imbriquée) et rien d'autre : c'est la condition pour pouvoir
# le reconstruire sans perte.
_PAREN_RE = re.compile(r"\(([^()]*)\)")

# Virgule décimale (ex. '7,26') : rend le découpage sur les virgules ambigu.
_DECIMAL_COMMA_RE = re.compile(r"\d,\d")

# Virgule décimale SANS ambiguïté : entier de 1 à 3 chiffres, virgule, 1 à 2
# décimales, puis une parenthèse, ``Hz``, un tiret de plage ou la fin. Une
# liste collée (``170,165 (``), une 3e décimale ou un point déjà présent
# (``8.4,2.1``) ne correspondent pas : la liste reste alors non parsable.
_FIXABLE_COMMA_RE = re.compile(
    rf"(?<![\d.,])(\d{{1,3}}),(\d{{1,2}})(?!\d)(?=\s*(?:\(|Hz\b|[{_MINUS}]|$))"
)


def convert_decimal_commas(body: str) -> Tuple[str, List[Tuple[str, str]]]:
    """Remplace les virgules décimales non ambiguës par un point.

    Retourne ``(texte, [(avant, après), …])``. Seule la virgule change : les
    chiffres sont recopiés tels quels.
    """
    changes: List[Tuple[str, str]] = []

    def _fix(match: re.Match) -> str:
        before = match.group(0)
        after = f"{match.group(1)}.{match.group(2)}"
        changes.append((before, after))
        return after

    return _FIXABLE_COMMA_RE.sub(_fix, body), changes


# Ponctuation terminale de la liste des signaux (ex. point final).
_TRAILING_PUNCT_RE = re.compile(r"\s*([.;])\s*$")


def split_trailing_punctuation(body: str) -> Tuple[str, str]:
    """Sépare la ponctuation finale (``.`` ou ``;``) de la liste des signaux.

    Exemple : ``'7.26 (s, 1H).'`` -> ``('7.26 (s, 1H)', '.')``. La ponctuation
    est réinsérée telle quelle après les signaux reformatés.
    """
    match = _TRAILING_PUNCT_RE.search(body)
    if not match:
        return body, ""
    return body[: match.start()], match.group(1)

# Constante de couplage dans un contenu de parenthèse.
# Une ou plusieurs valeurs : 'J = 4.7 Hz' ou 'J = 8.4, 2.1 Hz'.
_J_RE = re.compile(
    r"J\s*=\s*(-?\d+(?:\.\d+)?(?:\s*,\s*-?\d+(?:\.\d+)?)*)\s*Hz", re.IGNORECASE
)

# Marqueur provisoire d'une constante de couplage extraite avant le découpage
# des champs sur les virgules (les virgules de 'J = 8.4, 2.1 Hz' ne séparent
# pas des champs).
_J_TOKEN = "\x00J{}\x00"
_J_TOKEN_RE = re.compile(r"\x00J(\d+)\x00")

# Intégration (ex '2H', '1H', '3F').
_INTEG_RE = re.compile(r"\b(\d+\s*[A-Za-z])\b")


def _parse_multiplicity(
    token: str, config: Optional[RmnConfig] = None
) -> Optional[str]:
    """Reconnaît une multiplicité autorisée dans un token, ou None."""
    config = config or get_config()
    token = " ".join(token.split()).lower()
    return config.multiplicities.get(token)


def parse_signals(
    body: str, config: Optional[RmnConfig] = None
) -> Tuple[List[Signal], bool]:
    """Parse la liste des signaux d'une section RMN.

    Args:
        body: liste brute des signaux (après le delta).

    Returns:
        ``(signaux, all_parsable)`` où ``all_parsable`` est ``False`` dès qu'un
        signal ne peut pas être reconstruit sans perte : déplacement illisible,
        texte en dehors de la parenthèse, parenthèse imbriquée, ou virgule
        décimale dans la liste (découpage ambigu). Dans ce cas l'appelant ne
        doit pas réécrire la liste.
    """
    config = config or get_config()
    raw_signals = _split_top_level(body)
    signals: List[Signal] = []
    all_parsable = bool(raw_signals) and not _DECIMAL_COMMA_RE.search(body)

    for raw in raw_signals:
        shift_match = _SHIFT_RE.match(raw)
        if not shift_match:
            all_parsable = False
            signals.append(Signal(shift=raw, shift_high=float("-inf")))
            continue

        low = shift_match.group(1)
        high = shift_match.group(2)
        if high is not None:
            shift_text = f"{low}{RANGE_SEP}{high}"  # tiret demi-cadratin entouré d'espaces
            shift_high = max(_to_float(low), _to_float(high))
        else:
            shift_text = low
            shift_high = _to_float(low)

        rest = raw[shift_match.end():].strip()
        multiplicity = None
        j = None
        integration = None
        attribution = None

        paren_match = _PAREN_RE.fullmatch(rest) if rest else None
        if rest and not paren_match:
            # Texte hors parenthèse ou parenthèse imbriquée : on ne saurait
            # pas le reconstruire, on garde le signal brut.
            all_parsable = False
            signals.append(Signal(shift=raw, shift_high=float("-inf")))
            continue
        extra_j: List[str] = []
        lossless = True
        if paren_match:
            # Les constantes de couplage sont extraites AVANT le découpage
            # (leurs virgules internes ne séparent pas des champs).
            j_values: List[str] = []

            def _stash_j(match: re.Match) -> str:
                j_values.append(re.sub(r"\s*,\s*", ", ", match.group(1)))
                return _J_TOKEN.format(len(j_values) - 1)

            inner = _J_RE.sub(_stash_j, paren_match.group(1))
            # Séparateurs de champs : virgule, ou point-virgule avant l'attribution
            # (``m, 5 H; OCH3``).
            fields = [f.strip() for f in re.split(r"[;,]", inner)]
            remaining_fields: List[str] = []
            for fld in fields:
                mult = _parse_multiplicity(fld, config)
                j_token = _J_TOKEN_RE.fullmatch(fld)
                if mult and multiplicity is None:
                    recognized = True
                    multiplicity = mult
                elif j_token:
                    recognized = True
                    value = j_values[int(j_token.group(1))]
                    if j is None:
                        j = value
                    else:
                        extra_j.append(value)
                elif integration is None and _INTEG_RE.fullmatch(fld.replace(" ", "")):
                    recognized = True
                    integration = fld.replace(" ", "")
                else:
                    recognized = False
                    if _J_TOKEN_RE.search(fld) or _MULTIPLICITY_LIKE_RE.fullmatch(fld):
                        # J mêlée à du texte, ou multiplicité hors table (td…).
                        lossless = False
                    remaining_fields.append(fld)
                if recognized and remaining_fields:
                    # Un champ inconnu précède un champ reconnu : la sortie
                    # (multiplicité, J, intégration, attribution) le déplacerait.
                    lossless = False
            if remaining_fields:
                attribution = ", ".join(remaining_fields)

        if not lossless:
            all_parsable = False
            signals.append(Signal(shift=raw, shift_high=float("-inf")))
            continue

        signals.append(
            Signal(
                shift=shift_text,
                shift_high=shift_high,
                multiplicity=multiplicity,
                j=j,
                extra_j=extra_j,
                integration=integration,
                attribution=attribution,
            )
        )

    return signals, all_parsable


def sort_signals(
    signals: List[Signal],
    all_parsable: bool,
    config: Optional[RmnConfig] = None,
) -> List[Signal]:
    """Trie les signaux selon l'ordre configuré (``config.sort_order``).

    - ``desc`` : du déplacement le plus grand au plus petit ;
    - ``asc`` : du plus petit au plus grand ;
    - ``none`` : aucun tri (ordre d'entrée conservé).

    Règle de sûreté inchangée : si ``all_parsable`` est faux, on ne réordonne
    jamais (quel que soit ``sort_order``). Pour une plage, la borne haute sert
    de clé.
    """
    config = config or get_config()
    if not all_parsable or config.sort_order == "none":
        return signals
    reverse = config.sort_order == "desc"
    return sorted(signals, key=lambda s: s.shift_high, reverse=reverse)


def format_integration(integration: str) -> str:
    """Intégration avec espace insécable : ``2H`` -> ``2 H`` (espace U+00A0)."""
    match = re.fullmatch(r"(\d+)\s*([A-Za-z])", integration)
    return f"{match.group(1)}{NBSP}{match.group(2)}" if match else integration


def _decimals(number: str) -> int:
    """Nombre de décimales écrites d'un nombre (``7.26`` -> 2, ``128`` -> 0)."""
    return len(number.split(".")[1]) if "." in number else 0


# Nombre de décimales des constantes de couplage J (usage JOC / Angewandte).
J_DECIMALS = 1


def decimal_issues(
    signals: List[Signal], shift_decimals: int
) -> List[Tuple[str, List[Signal]]]:
    """Contrôle le nombre de décimales des déplacements et des constantes J.

    ``shift_decimals`` décimales sont attendues pour δ ; une décimale de plus
    est tolérée (cas ambigu). J s'écrit avec une décimale. Les valeurs ne sont
    jamais modifiées : le résultat est la liste des ``(message, signaux en
    cause)`` à signaler (FLAGGED), vide si tout est conforme. Seuls les signaux
    analysés sont contrôlés.
    """
    bad_shifts: List[str] = []
    bad_j: List[str] = []
    shift_signals: List[Signal] = []
    j_signals: List[Signal] = []
    for signal in signals:
        if signal.shift_high == float("-inf"):
            continue  # signal conservé brut (non parsable) : déjà signalé
        for value in re.findall(r"\d+(?:\.\d+)?", signal.shift):
            if _decimals(value) not in (shift_decimals, shift_decimals + 1):
                bad_shifts.append(f"{value} ({_decimals(value)})")
                if signal not in shift_signals:
                    shift_signals.append(signal)
        for group in ([signal.j] if signal.j else []) + list(signal.extra_j):
            for value in re.findall(r"\d+(?:\.\d+)?", group):
                if _decimals(value) != J_DECIMALS:
                    bad_j.append(f"{value} ({_decimals(value)})")
                    if signal not in j_signals:
                        j_signals.append(signal)
    issues: List[Tuple[str, List[Signal]]] = []
    if bad_shifts:
        issues.append((
            "Nombre de décimales du déplacement chimique inattendu : "
            f"{', '.join(bad_shifts)} ; {shift_decimals} attendues "
            f"({shift_decimals + 1} tolérées), valeurs conservées.",
            shift_signals,
        ))
    if bad_j:
        issues.append((
            "Nombre de décimales de la constante de couplage J inattendu : "
            f"{', '.join(bad_j)} ; {J_DECIMALS} attendue, valeurs conservées.",
            j_signals,
        ))
    return issues


def check_decimals(signals: List[Signal], shift_decimals: int) -> List[str]:
    """Messages seuls de ``decimal_issues``."""
    return [message for message, _ in decimal_issues(signals, shift_decimals)]


def _format_j(signal: Signal) -> List[str]:
    """Champs 'J = … Hz' d'un signal, dans l'ordre d'entrée."""
    values = ([signal.j] if signal.j else []) + list(signal.extra_j)
    return [f"J = {value} Hz" for value in values]


def format_signal_1h(signal: Signal) -> str:
    """Formate un signal 1H : déplacement, multiplicité, J, intégration, attribution."""
    parts: List[str] = []
    if signal.multiplicity:
        parts.append(signal.multiplicity)
    parts.extend(_format_j(signal))
    if signal.integration:
        parts.append(format_integration(signal.integration))
    text = ', '.join(parts)
    if signal.attribution:
        # Point-virgule entre les données du signal et l'attribution.
        attribution = subscript_attribution(signal.attribution)
        text = f"{text}; {attribution}" if text else attribution
    if text:
        return f"{signal.shift} ({text})"
    return signal.shift


def format_signal_13c(signal: Signal) -> str:
    """Formate un signal 13C : déplacement (+ multiplicité / J / attribution).

    Le carbone est généralement découplé (singulet) : on indique le déplacement
    puis l'attribution optionnelle entre parenthèses. La multiplicité et la
    constante ``J`` sont conservées si un couplage est présent (ex. ``d`` pour
    un couplage C–F).
    """
    parts: List[str] = []
    if signal.multiplicity:
        parts.append(signal.multiplicity)
    parts.extend(_format_j(signal))
    if signal.integration:
        parts.append(format_integration(signal.integration))
    if signal.attribution:
        parts.append(subscript_attribution(signal.attribution))
    if parts:
        return f"{signal.shift} ({', '.join(parts)})"
    return signal.shift
