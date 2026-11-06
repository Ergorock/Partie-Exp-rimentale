"""Règle de standardisation des paragraphes ``1H NMR``.

Format cible::

    1H NMR (<fréquence> MHz, <solvant>, <température> K) ...

La parenthèse qui suit immédiatement ``1H NMR`` doit contenir exactement trois
éléments séparés par deux virgules, dans l'ordre : fréquence en MHz, solvant,
température en Kelvin.

Corrections automatiques appliquées (cas déductibles) :
    - espace manquant entre le nombre et ``MHz`` (``400.18MHz`` -> ``400.18 MHz``) ;
    - unité ``MHz`` manquante quand le premier élément est un simple nombre ;
    - unité ``K`` manquante sur la température (``298`` -> ``298 K``) ;
    - fréquence écrite hors de la parenthèse, déplacée à l'intérieur en tête.

Quand une donnée ne peut pas être déduite (température totalement absente), un
marqueur visible ``[??? K]`` est inséré. Quand le paragraphe n'a pas de
parenthèse exploitable, il est signalé sans correction.
"""

from __future__ import annotations

import re

from core.rules.base import Action, ActionKind, Rule, RuleResult

# Marqueur inséré lorsqu'une température est attendue mais introuvable.
TEMPERATURE_PLACEHOLDER = "[??? K]"

# Préfixe reconnu en tête de paragraphe (insensible aux espaces de début).
_PREFIX_RE = re.compile(r"^\s*1H\s*NMR\b", re.IGNORECASE)

# Capture : "1H NMR" + éventuel texte avant la parenthèse + contenu de la 1re parenthèse + reste.
_STRUCTURE_RE = re.compile(
    r"^(?P<indent>\s*)(?P<label>1H\s*NMR)\b(?P<between>[^(]*)\((?P<inside>[^)]*)\)(?P<rest>.*)$",
    re.IGNORECASE | re.DOTALL,
)

# Un nombre (entier ou décimal).
_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")


def _normalize_spaces(text: str) -> str:
    """Remplace les espaces insécables par des espaces ordinaires."""
    return text.replace("\xa0", " ")


def _normalize_frequency(freq: str) -> tuple[str, bool]:
    """Normalise l'élément fréquence vers ``<nombre> MHz``.

    Returns:
        (texte_normalisé, modifié).
    """
    original = freq
    freq = freq.strip()
    # Ajoute l'espace manquant entre le nombre et MHz : 400.18MHz -> 400.18 MHz.
    freq = re.sub(r"(\d)\s*(MHz)", r"\1 \2", freq, flags=re.IGNORECASE)
    # Uniformise la casse de l'unité.
    freq = re.sub(r"\bmhz\b", "MHz", freq, flags=re.IGNORECASE)
    # Si c'est un simple nombre sans unité, on ajoute MHz.
    if _NUMBER_RE.fullmatch(freq):
        freq = f"{freq} MHz"
    freq = re.sub(r"\s+", " ", freq).strip()
    return freq, freq != original.strip()


def _normalize_temperature(temp: str) -> tuple[str, bool]:
    """Normalise l'élément température vers ``<nombre> K``.

    Returns:
        (texte_normalisé, modifié).
    """
    original = temp
    temp = temp.strip()
    number = _NUMBER_RE.search(temp)
    if not number:
        return temp, False
    normalized = f"{number.group()} K"
    return normalized, normalized != original.strip()


def _looks_like_frequency(segment: str) -> bool:
    """Indique si un segment ressemble à une fréquence RMN (nombre + MHz)."""
    return bool(re.search(r"\d+(?:\.\d+)?\s*MHz", segment, re.IGNORECASE))


class OneHNmrRule(Rule):
    """Valide et standardise les paragraphes ``1H NMR``."""

    name = "1H NMR"
    description = (
        "Fréquence (MHz), solvant et température (K) entre parenthèses après "
        "'1H NMR' ; corrige espaces/unités, insère [??? K] si la température "
        "manque."
    )

    def applies(self, paragraph_text: str) -> bool:
        return bool(_PREFIX_RE.match(paragraph_text))

    def apply(self, paragraph_text: str) -> RuleResult:
        text = _normalize_spaces(paragraph_text)
        match = _STRUCTURE_RE.match(text)

        if not match:
            # Pas de parenthèse après "1H NMR" : on ne peut pas corriger sûrement.
            return RuleResult(
                new_text=paragraph_text,
                actions=[
                    Action(
                        ActionKind.FLAGGED,
                        "Aucune parenthèse exploitable après '1H NMR' : "
                        "vérification manuelle requise.",
                        self.name,
                    )
                ],
            )

        indent = match.group("indent")
        between = match.group("between")
        inside = match.group("inside")
        rest = match.group("rest")

        actions: list[Action] = []

        # Fréquence placée hors de la parenthèse -> on la déplace à l'intérieur.
        if _looks_like_frequency(between):
            freq_segment = between.strip()
            inside = f"{freq_segment}, {inside.strip()}"
            between = " "
            actions.append(
                Action(
                    ActionKind.CORRECTED,
                    "Fréquence déplacée à l'intérieur de la parenthèse.",
                    self.name,
                )
            )

        # Découpe les éléments de la parenthèse.
        elements = [e.strip() for e in inside.split(",")]

        # Normalise la fréquence (1er élément).
        if elements and elements[0]:
            new_freq, changed = _normalize_frequency(elements[0])
            if changed:
                actions.append(
                    Action(
                        ActionKind.CORRECTED,
                        f"Fréquence normalisée : '{elements[0]}' -> '{new_freq}'.",
                        self.name,
                    )
                )
            elements[0] = new_freq

        # Gère le nombre d'éléments pour la température (3e élément).
        if len(elements) >= 3:
            new_temp, changed = _normalize_temperature(elements[2])
            if not _NUMBER_RE.search(elements[2]):
                # 3e élément présent mais sans nombre -> placeholder.
                elements[2] = TEMPERATURE_PLACEHOLDER
                actions.append(
                    Action(
                        ActionKind.PLACEHOLDER,
                        "Température illisible : marqueur inséré.",
                        self.name,
                    )
                )
            else:
                if changed:
                    actions.append(
                        Action(
                            ActionKind.CORRECTED,
                            f"Température normalisée : '{elements[2]}' -> '{new_temp}'.",
                            self.name,
                        )
                    )
                elements[2] = new_temp
            # Éléments surnuméraires (>3) : signalés.
            if len(elements) > 3:
                actions.append(
                    Action(
                        ActionKind.FLAGGED,
                        f"La parenthèse contient {len(elements)} éléments au lieu de 3.",
                        self.name,
                    )
                )
        elif len(elements) == 2:
            # Température absente -> placeholder.
            elements.append(TEMPERATURE_PLACEHOLDER)
            actions.append(
                Action(
                    ActionKind.PLACEHOLDER,
                    "Température absente : marqueur '[??? K]' inséré.",
                    self.name,
                )
            )
        else:
            # 0 ou 1 élément : trop incomplet pour corriger sûrement.
            actions.append(
                Action(
                    ActionKind.FLAGGED,
                    "Parenthèse incomplète (moins de 2 éléments) : "
                    "vérification manuelle requise.",
                    self.name,
                )
            )

        new_inside = ", ".join(elements)
        new_text = f"{indent}{match.group('label')}{between.rstrip()} ({new_inside}){rest}"
        # Nettoyage d'un éventuel double espace avant la parenthèse.
        new_text = re.sub(r"\s+\(", " (", new_text, count=1)

        if new_text == paragraph_text:
            return RuleResult(
                new_text=paragraph_text,
                actions=[
                    Action(ActionKind.UNCHANGED, "Paragraphe déjà conforme.", self.name)
                ],
            )

        if not actions:
            actions.append(
                Action(ActionKind.UNCHANGED, "Paragraphe déjà conforme.", self.name)
            )

        return RuleResult(new_text=new_text, actions=actions)
