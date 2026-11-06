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


# Déplacement chimique : valeur unique ou plage 'a-b' / 'a–b'.
_SHIFT_RE = re.compile(r"^\s*(-?\d+(?:\.\d+)?)(?:\s*[-\u2013]\s*(-?\d+(?:\.\d+)?))?")

# Après le déplacement, un signal ne peut contenir qu'une parenthèse simple
# (sans parenthèse imbriquée) et rien d'autre : c'est la condition pour pouvoir
# le reconstruire sans perte.
_PAREN_RE = re.compile(r"\(([^()]*)\)")

# Virgule décimale (ex. '7,26') : rend le découpage sur les virgules ambigu.
_DECIMAL_COMMA_RE = re.compile(r"\d,\d")

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
    token = token.strip().lower()
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
            fields = [f.strip() for f in inner.split(",")]
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
        parts.append(signal.integration)
    if signal.attribution:
        parts.append(subscript_formula(signal.attribution))
    if parts:
        return f"{signal.shift} ({', '.join(parts)})"
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
        parts.append(signal.integration)
    if signal.attribution:
        parts.append(subscript_formula(signal.attribution))
    if parts:
        return f"{signal.shift} ({', '.join(parts)})"
    return signal.shift
