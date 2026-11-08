"""Calcul de masse exacte (monoisotopique) d'une formule brute et d'un ion.

Fonctions pures utilisées par la règle HRMS pour VÉRIFIER une masse calculée
écrite dans le document. Elles ne servent jamais à réécrire une valeur : un
résultat incohérent produit seulement une action FLAGGED.

Masses : isotope le plus abondant de chaque élément (u). Un élément absent de
la table rend la formule non vérifiable (``None``), sans erreur.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

#: Masse de l'électron (u), retirée pour un cation et ajoutée pour un anion.
ELECTRON_MASS = 0.000548579909

#: Masses monoisotopiques (isotope le plus abondant).
MONOISOTOPIC_MASSES: Dict[str, float] = {
    "H": 1.00782503207,
    "D": 2.0141017778,
    "Li": 7.01600455,
    "B": 11.0093054,
    "C": 12.0,
    "N": 14.0030740048,
    "O": 15.99491461956,
    "F": 18.99840322,
    "Na": 22.9897692809,
    "Mg": 23.985041700,
    "Al": 26.98153863,
    "Si": 27.9769265325,
    "P": 30.97376163,
    "S": 31.97207100,
    "Cl": 34.96885268,
    "K": 38.96370668,
    "Ca": 39.96259098,
    "Ti": 47.9479463,
    "Cr": 51.9405075,
    "Mn": 54.9380451,
    "Fe": 55.9349375,
    "Co": 58.9331950,
    "Ni": 57.9353429,
    "Cu": 62.9295975,
    "Zn": 63.9291422,
    "Ge": 73.9211778,
    "As": 74.9215965,
    "Se": 79.9165213,
    "Br": 78.9183371,
    "Rb": 84.911789738,
    "Zr": 89.9047044,
    "Mo": 97.9054082,
    "Ru": 101.9043493,
    "Rh": 102.905504,
    "Pd": 105.903486,
    "Ag": 106.905097,
    "Sn": 119.9021947,
    "Te": 129.9062244,
    "I": 126.904473,
    "Cs": 132.905451933,
    "Ba": 137.9052472,
    "W": 183.9509312,
    "Os": 191.9614807,
    "Ir": 192.9629264,
    "Pt": 194.9647911,
    "Au": 196.9665687,
    "Hg": 201.970643,
    "Bi": 208.9803987,
}

# Indices Unicode -> chiffres ASCII (formule déjà stylisée).
_SUBSCRIPT_DIGITS = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")

# Élément (majuscule + minuscule optionnelle) suivi d'un nombre optionnel.
_TOKEN_RE = re.compile(r"([A-Z][a-z]?)(\d*)|(\()|(\))(\d*)")


def parse_formula(formula: str) -> Optional[Dict[str, int]]:
    """Décompose une formule brute en ``{élément: nombre}``.

    Accepte les groupes entre parenthèses (``C6H5(CH3)2``) et les indices
    Unicode (``C₁₀H₁₃O₂``). Retourne ``None`` si la formule est illisible ou
    contient un élément inconnu de ``MONOISOTOPIC_MASSES``.
    """
    text = formula.translate(_SUBSCRIPT_DIGITS).strip()
    if not text:
        return None
    stack: List[Dict[str, int]] = [{}]
    pos = 0
    while pos < len(text):
        match = _TOKEN_RE.match(text, pos)
        if not match:
            return None
        element, count, opening, closing, group_count = match.groups()
        if element:
            if element not in MONOISOTOPIC_MASSES:
                return None
            stack[-1][element] = stack[-1].get(element, 0) + int(count or 1)
        elif opening:
            stack.append({})
        else:
            if len(stack) == 1:
                return None
            group = stack.pop()
            factor = int(group_count or 1)
            for el, n in group.items():
                stack[-1][el] = stack[-1].get(el, 0) + n * factor
        pos = match.end()
    if len(stack) != 1 or not stack[0]:
        return None
    return stack[0]


def monoisotopic_mass(formula: str) -> Optional[float]:
    """Masse monoisotopique d'une formule (u), ou ``None`` si non calculable."""
    composition = parse_formula(formula)
    if composition is None:
        return None
    return sum(MONOISOTOPIC_MASSES[el] * n for el, n in composition.items())


def ion_mz(neutral_mass: float, charge: int, electron: bool = True) -> float:
    """``m/z`` d'un ion de masse ``neutral_mass`` (somme des atomes) et charge ``charge``.

    Avec ``electron``, la masse des électrons perdus (cation) ou gagnés
    (anion) est prise en compte ; certains logiciels l'ignorent.
    """
    z = charge or 1
    total = neutral_mass - (z * ELECTRON_MASS if electron else 0.0)
    return total / abs(z)


def adduct_mass(terms: List[Tuple[int, int, str]]) -> Optional[float]:
    """Masse algébrique des termes d'un ion (``[(signe, nombre, formule)]``)."""
    total = 0.0
    for sign, count, formula in terms:
        value = monoisotopic_mass(formula)
        if value is None:
            return None
        total += sign * count * value
    return total
