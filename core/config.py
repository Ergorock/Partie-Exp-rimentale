"""Couche de configuration des règles RMN, indépendante de Qt.

Ce module centralise les paramètres éditables des règles RMN (multiplicités
reconnues, marqueur de température, ordre de tri, gras/italique, unité de
température) dans une dataclass ``RmnConfig`` dont les DÉFAUTS reproduisent
EXACTEMENT le comportement actuel de ``core/rules/nmr_common.py`` et des règles
``nmr_1h`` / ``nmr_13c``.

Le module n'importe aucun composant PySide6 : il est entièrement testable sans
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
    """Multiplicités reconnues par défaut (copie exacte de ``_MULTIPLICITIES``)."""
    return {
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
class RmnConfig:
    """Paramètres éditables des règles RMN.

    Les défauts reproduisent exactement le comportement actuel afin que la suite
    de tests existante reste verte lorsque aucun fichier de préférences n'est
    présent.
    """

    multiplicities: Dict[str, str] = field(default_factory=_default_multiplicities)
    temperature_placeholder: str = "[??? K]"
    sort_order: str = "desc"  # 'desc' | 'asc' | 'none'
    bold_label: bool = True
    italic_delta: bool = True
    temperature_unit: str = "K"  # 'K' | '°C'


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
        "temperature_placeholder": config.temperature_placeholder,
        "sort_order": config.sort_order,
        "bold_label": config.bold_label,
        "italic_delta": config.italic_delta,
        "temperature_unit": config.temperature_unit,
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

    return RmnConfig(
        multiplicities=multiplicities,
        temperature_placeholder=temperature_placeholder,
        sort_order=sort_order,
        bold_label=bold_label,
        italic_delta=italic_delta,
        temperature_unit=temperature_unit,
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
