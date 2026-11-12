"""Couche de configuration des règles RMN, indépendante de l'interface.

Ce module centralise les paramètres éditables des règles RMN (multiplicités
reconnues, marqueur de température, ordre de tri, gras/italique, unité de
température) dans une dataclass ``RmnConfig`` dont les DÉFAUTS reproduisent
EXACTEMENT le comportement actuel de ``core/rules/nmr_common.py`` et des règles
``nmr_1h`` / ``nmr_13c``.

Le module n'importe aucune bibliothèque graphique : il est entièrement testable sans
interface graphique. Il expose :

- la dataclass ``RmnConfig`` et sa valeur par défaut ;
- ``config_to_dict`` / ``config_from_dict`` (sérialisation tolérante) ;
- ``load_config`` / ``save_config`` (persistance JSON UTF-8, sans exception à la
  lecture d'un fichier absent ou corrompu) ;
- un état de processus (singleton) via ``get_config`` / ``set_config`` /
  ``reset_config``.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Mapping, Optional


# Valeurs autorisées pour certains champs.
_SORT_ORDERS = ("desc", "asc", "none")
_TEMPERATURE_UNITS = ("K", "\u00b0C")  # 'K' | '°C'


def _default_multiplicities() -> Dict[str, str]:
    """Multiplicités reconnues par défaut : écrit dans le document -> sortie.

    Couvre les multiplicités simples, les multiplicités composées usuelles
    (``dd``, ``td``, ``ddd``…), les signaux larges (``br``) et apparents
    (``app``). Les variantes d'écriture (``bs``, ``br. s``, ``bd``) sont
    ramenées à la forme ``br x``.
    """
    simple = ["s", "d", "t", "q", "quint", "sext", "sept", "hept", "septic", "m"]
    composite = [
        "dd", "dt", "td", "tt", "dq", "qd", "ddd", "ddt", "dtd", "tdd",
        "dddd", "qt", "tq",
    ]
    table = {m: m for m in simple + composite}
    for base in ("s", "d", "t", "q", "m", "dd"):
        table[f"br {base}"] = f"br {base}"
        table[f"br. {base}"] = f"br {base}"
    for base in ("s", "d", "t", "q"):  # abréviations usuelles 'bs', 'bd'…
        table[f"b{base}"] = f"br {base}"
    for base in ("d", "t", "q", "quint", "dd", "dt", "td"):
        table[f"app {base}"] = f"app {base}"
    return table


def _default_solvents() -> Dict[str, str]:
    """Solvants RMN reconnus par défaut : écrit dans le document -> sortie.

    La sortie est un balisage léger : ``*…*`` met le texte en italique (le *d*
    des solvants deutérés), les indices Unicode des chiffres sont ajoutés
    automatiquement (``DMSO-*d*6`` -> ``DMSO-`` + *d* italique + ``₆``). Les
    clés sont en minuscules, espaces réduits.
    """
    table = {
        "cdcl3": "CDCl3",
        "dmso-d6": "DMSO-*d*6",
        "dmso d6": "DMSO-*d*6",
        "d6-dmso": "DMSO-*d*6",
        "(cd3)2so": "(CD3)2SO",
        "cd3od": "CD3OD",
        "meod": "CD3OD",
        "c6d6": "C6D6",
        "acetone-d6": "acetone-*d*6",
        "d2o": "D2O",
        "cd3cn": "CD3CN",
        "cd2cl2": "CD2Cl2",
        "thf-d8": "THF-*d*8",
        "pyridine-d5": "pyridine-*d*5",
        "toluene-d8": "toluene-*d*8",
        "cd3cooh": "CD3COOH",
        "cd3cod": "CD3COOD",
        "tfa-d": "TFA-*d*",
    }
    return table


def valid_solvent_markup(markup: str) -> bool:
    """Vrai si le balisage ``*…*`` d'un solvant est apparié (nombre pair de ``*``)."""
    return markup.count("*") % 2 == 0


#: Notes du mode évaluation, de la meilleure à la moins bonne (hors « Mauvais »).
EVALUATION_GRADES = ("parfait", "tres_bon", "bon", "correct")


def _default_evaluation_thresholds() -> Dict[str, float]:
    """Seuils par défaut des notes (pourcentage de sections conformes)."""
    return {"parfait": 100.0, "tres_bon": 90.0, "bon": 75.0, "correct": 50.0}


def _valid_thresholds(raw) -> Optional[Dict[str, float]]:
    """Seuils valides (4 nombres dans [0, 100], décroissants), ou None."""
    if not isinstance(raw, dict) or set(raw) != set(EVALUATION_GRADES):
        return None
    values = []
    for key in EVALUATION_GRADES:
        value = raw[key]
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            return None
        if not 0 <= value <= 100:
            return None
        values.append(float(value))
    if any(a < b for a, b in zip(values, values[1:])):
        return None
    return dict(zip(EVALUATION_GRADES, values))


@dataclass
class RmnConfig:
    """Paramètres éditables des règles RMN.

    Les défauts reproduisent exactement le comportement actuel afin que la suite
    de tests existante reste verte lorsque aucun fichier de préférences n'est
    présent.
    """

    multiplicities: Dict[str, str] = field(default_factory=_default_multiplicities)
    #: Table des solvants RMN : écrit (minuscules) -> sortie balisée ``*italique*``.
    solvents: Dict[str, str] = field(default_factory=_default_solvents)
    temperature_placeholder: str = "[??? K]"
    sort_order: str = "desc"  # 'desc' | 'asc' | 'none'
    bold_label: bool = True
    italic_delta: bool = True
    temperature_unit: str = "K"  # 'K' | '°C'
    #: Contrôle de la température (obligatoire, marqueur, unité) ; désactivé :
    #: le 3e élément de la parenthèse est laissé tel quel.
    check_temperature: bool = True
    italic_j: bool = True  # constante de couplage J en italique (usage ACS/RSC)
    hrms_ppm_tolerance: float = 5.0  # écart HRMS trouvé / calculé toléré (ppm)
    hrms_abs_tolerance: float = 0.003  # écart HRMS absolu toléré (Da), en plus des ppm
    #: Seuils (pourcentage minimal de sections conformes) des notes du mode
    #: évaluation ; en dessous de ``correct`` : « Mauvais ».
    evaluation_thresholds: Dict[str, float] = field(
        default_factory=_default_evaluation_thresholds
    )


CONFIG_FILENAME = "rules_config.json"

#: Variable d'environnement qui impose le chemin du fichier de préférences
#: (installation portable, tests…).
CONFIG_ENV_VAR = "STANDARDISATION_RMN_CONFIG"


def user_config_path(
    environ: Optional[Mapping[str, str]] = None, platform: Optional[str] = None
) -> Path:
    """Chemin du fichier de préférences dans le dossier de l'utilisateur.

    - ``STANDARDISATION_RMN_CONFIG`` s'il est défini ;
    - Windows : ``%APPDATA%\\StandardisationRMN\\rules_config.json`` ;
    - autres systèmes : ``$XDG_CONFIG_HOME`` (ou ``~/.config``)
      ``/standardisation-rmn/rules_config.json``.

    Le dossier d'installation de l'application peut être en lecture seule :
    les préférences n'y sont donc jamais écrites. Fonction pure (``environ``
    et ``platform`` injectables) pour être testable sur tout système.
    """
    environ = os.environ if environ is None else environ
    platform = sys.platform if platform is None else platform
    override = environ.get(CONFIG_ENV_VAR)
    if override:
        return Path(override)
    if platform.startswith("win"):
        base = environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "StandardisationRMN" / CONFIG_FILENAME
    base = environ.get("XDG_CONFIG_HOME") or str(
        Path(environ.get("HOME") or Path.home()) / ".config"
    )
    return Path(base) / "standardisation-rmn" / CONFIG_FILENAME


#: Fichier de préférences actif (dossier utilisateur).
DEFAULT_CONFIG_PATH = user_config_path()

#: Ancien emplacement, à la racine du projet : encore LU (jamais écrit) tant
#: que le fichier du dossier utilisateur n'existe pas, pour ne pas perdre les
#: préférences enregistrées par une version précédente.
LEGACY_CONFIG_PATH = Path(__file__).resolve().parent.parent / CONFIG_FILENAME


def config_to_dict(config: RmnConfig) -> dict:
    """Sérialise une ``RmnConfig`` en dictionnaire JSON-compatible."""
    return {
        "multiplicities": dict(config.multiplicities),
        "solvents": dict(config.solvents),
        "temperature_placeholder": config.temperature_placeholder,
        "sort_order": config.sort_order,
        "bold_label": config.bold_label,
        "italic_delta": config.italic_delta,
        "temperature_unit": config.temperature_unit,
        "check_temperature": config.check_temperature,
        "italic_j": config.italic_j,
        "hrms_ppm_tolerance": config.hrms_ppm_tolerance,
        "hrms_abs_tolerance": config.hrms_abs_tolerance,
        "evaluation_thresholds": dict(config.evaluation_thresholds),
    }


def config_from_dict(data: dict) -> RmnConfig:
    """Reconstruit une ``RmnConfig`` de manière TOLÉRANTE, champ par champ.

    Chaque champ absent ou du mauvais type retombe sur le défaut de
    ``RmnConfig()``. ``sort_order`` et ``temperature_unit`` sont validés contre
    leurs ensembles autorisés. Pour ``multiplicities``, seules les paires
    ``str -> str`` sont conservées ; la clé est normalisée (espaces retirés,
    minuscules) car la recherche se fait sur le token en minuscules, et une
    valeur normalisée vide prend la clé comme valeur.
    """
    defaults = RmnConfig()

    if not isinstance(data, dict):
        return defaults

    # multiplicities : ne garder que les paires str->str.
    multiplicities = defaults.multiplicities
    raw_mult = data.get("multiplicities")
    if isinstance(raw_mult, dict):
        cleaned: Dict[str, str] = {}
        for key, value in raw_mult.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            key = " ".join(key.split()).lower()
            if not key:
                continue
            normalized = value.strip()
            cleaned[key] = normalized if normalized else key
        if cleaned:
            multiplicities = cleaned

    # solvents : paires str->str ; clé normalisée, valeur vide ou balisage '*'
    # non apparié -> la clé elle-même ; table vide -> défauts.
    solvents = defaults.solvents
    raw_solvents = data.get("solvents")
    if isinstance(raw_solvents, dict):
        cleaned_solvents: Dict[str, str] = {}
        for key, value in raw_solvents.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            key = " ".join(key.split()).lower()
            if not key:
                continue
            normalized = value.strip()
            if not normalized or not valid_solvent_markup(normalized):
                normalized = key
            cleaned_solvents[key] = normalized
        if cleaned_solvents:
            solvents = cleaned_solvents

    # temperature_placeholder : str.
    temperature_placeholder = defaults.temperature_placeholder
    raw_placeholder = data.get("temperature_placeholder")
    if isinstance(raw_placeholder, str):
        temperature_placeholder = raw_placeholder

    # sort_order : validé contre l'ensemble autorisé.
    sort_order = defaults.sort_order
    raw_sort = data.get("sort_order")
    if isinstance(raw_sort, str) and raw_sort in _SORT_ORDERS:
        sort_order = raw_sort

    # bold_label : bool.
    bold_label = defaults.bold_label
    raw_bold = data.get("bold_label")
    if isinstance(raw_bold, bool):
        bold_label = raw_bold

    # italic_delta : bool.
    italic_delta = defaults.italic_delta
    raw_italic = data.get("italic_delta")
    if isinstance(raw_italic, bool):
        italic_delta = raw_italic

    # temperature_unit : validé contre l'ensemble autorisé.
    temperature_unit = defaults.temperature_unit
    raw_unit = data.get("temperature_unit")
    if isinstance(raw_unit, str) and raw_unit in _TEMPERATURE_UNITS:
        temperature_unit = raw_unit

    # check_temperature : bool.
    check_temperature = defaults.check_temperature
    raw_check_temp = data.get("check_temperature")
    if isinstance(raw_check_temp, bool):
        check_temperature = raw_check_temp

    # italic_j : bool.
    italic_j = defaults.italic_j
    raw_italic_j = data.get("italic_j")
    if isinstance(raw_italic_j, bool):
        italic_j = raw_italic_j

    # hrms_ppm_tolerance : nombre strictement positif (un booléen est refusé).
    hrms_ppm_tolerance = defaults.hrms_ppm_tolerance
    raw_ppm = data.get("hrms_ppm_tolerance")
    if isinstance(raw_ppm, (int, float)) and not isinstance(raw_ppm, bool) and raw_ppm > 0:
        hrms_ppm_tolerance = float(raw_ppm)

    # hrms_abs_tolerance : nombre strictement positif (un booléen est refusé).
    hrms_abs_tolerance = defaults.hrms_abs_tolerance
    raw_abs = data.get("hrms_abs_tolerance")
    if isinstance(raw_abs, (int, float)) and not isinstance(raw_abs, bool) and raw_abs > 0:
        hrms_abs_tolerance = float(raw_abs)
    # evaluation_thresholds : 4 seuils valides, sinon tous les défauts.
    evaluation_thresholds = (
        _valid_thresholds(data.get("evaluation_thresholds"))
        or defaults.evaluation_thresholds
    )

    return RmnConfig(
        evaluation_thresholds=evaluation_thresholds,
        italic_j=italic_j,
        hrms_ppm_tolerance=hrms_ppm_tolerance,
        hrms_abs_tolerance=hrms_abs_tolerance,
        multiplicities=multiplicities,
        solvents=solvents,
        temperature_placeholder=temperature_placeholder,
        sort_order=sort_order,
        bold_label=bold_label,
        italic_delta=italic_delta,
        temperature_unit=temperature_unit,
        check_temperature=check_temperature,
    )


def load_config(path: Optional[Path] = None) -> RmnConfig:
    """Lit la configuration depuis ``path`` (JSON UTF-8).

    Sans ``path``, lit ``DEFAULT_CONFIG_PATH`` tel qu'il vaut AU MOMENT DE
    L'APPEL (et non à la définition de la fonction) : les tests peuvent ainsi
    le rediriger vers un fichier temporaire. Si ce fichier n'existe pas encore,
    l'ancien emplacement (``LEGACY_CONFIG_PATH``, racine du projet) est lu à sa
    place.

    Renvoie ``RmnConfig()`` par défaut, SANS lever d'exception, si le fichier est
    absent, corrompu (JSON invalide) ou ne contient pas un objet JSON.
    """
    if path is None:
        path = DEFAULT_CONFIG_PATH
        if not Path(path).exists() and Path(LEGACY_CONFIG_PATH).exists():
            path = LEGACY_CONFIG_PATH
    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return RmnConfig()
    if not isinstance(data, dict):
        return RmnConfig()
    return config_from_dict(data)


def save_config(config: RmnConfig, path: Optional[Path] = None) -> None:
    """Écrit la configuration dans ``path`` (JSON UTF-8, indenté).

    Sans ``path``, écrit dans ``DEFAULT_CONFIG_PATH`` résolu à l'appel (jamais
    dans l'ancien emplacement). Le dossier parent est créé au besoin.
    """
    path = Path(path if path is not None else DEFAULT_CONFIG_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(config_to_dict(config), handle, ensure_ascii=False, indent=2)


# --------------------------------------------------------------------------- #
# État de processus (singleton)
# --------------------------------------------------------------------------- #

_active: Optional[RmnConfig] = None


def get_config() -> RmnConfig:
    """Retourne la configuration active du processus.

    Au premier appel (ou après ``reset_config``), charge la configuration depuis
    ``DEFAULT_CONFIG_PATH`` puis la mémorise.
    """
    global _active
    if _active is None:
        _active = load_config()
    return _active


def set_config(config: RmnConfig) -> None:
    """Remplace la configuration active du processus."""
    global _active
    _active = config


def reset_config() -> None:
    """Réinitialise l'état de processus (force un rechargement au prochain ``get``)."""
    global _active
    _active = None
