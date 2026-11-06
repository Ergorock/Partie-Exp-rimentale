"""Configuration pytest : rend la racine du projet importable et isole la
configuration RMN.

Les règles lisent une configuration de processus chargée depuis
``rules_config.json`` (préférences enregistrées par l'UI). Sans isolation, un
fichier local (ex. tri croissant) ferait échouer des tests qui supposent les
défauts. Chaque test part donc des défauts, avec un fichier de préférences
redirigé vers un dossier temporaire : le fichier réel n'est jamais lu ni écrit.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(__file__))

from core import config as _config  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_rmn_config(tmp_path, monkeypatch):
    monkeypatch.setattr(_config, "DEFAULT_CONFIG_PATH", tmp_path / "rules_config.json")
    _config.reset_config()
    yield
    _config.reset_config()
