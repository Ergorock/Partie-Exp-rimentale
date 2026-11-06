"""Tests de la couche de configuration des règles RMN (FEAT-001).

Entièrement indépendants de l'interface. Les défauts de ``RmnConfig`` doivent
reproduire exactement le comportement actuel, et la persistance JSON doit être
tolérante (fichier absent / corrompu / partiel -> défauts champ par champ).
"""

import json
from pathlib import Path

import pytest

from core import config as cfg
from core.config import RmnConfig


# --- Défauts ---

def test_defaults_match_current_behaviour():
    c = RmnConfig()
    assert c.multiplicities == {
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
    assert c.temperature_placeholder == "[??? K]"
    assert c.sort_order == "desc"
    assert c.bold_label is True
    assert c.italic_delta is True
    assert c.temperature_unit == "K"


def test_default_multiplicities_are_independent_instances():
    a = RmnConfig()
    b = RmnConfig()
    a.multiplicities["x"] = "x"
    assert "x" not in b.multiplicities


# --- Round-trip save/load ---

def test_save_then_load_roundtrip_preserves_all_fields(tmp_path):
    path = tmp_path / "rules_config.json"
    original = RmnConfig(
        multiplicities={"s": "s", "sext": "sext"},
        temperature_placeholder="[MANQUANT]",
        sort_order="asc",
        bold_label=False,
        italic_delta=False,
        temperature_unit="\u00b0C",
    )
    cfg.save_config(original, path)
    loaded = cfg.load_config(path)
    assert loaded == original


def test_save_writes_utf8_without_ascii_escapes(tmp_path):
    path = tmp_path / "rules_config.json"
    cfg.save_config(RmnConfig(temperature_unit="\u00b0C"), path)
    raw = path.read_text(encoding="utf-8")
    assert "\u00b0C" in raw


# --- Lecture tolérante ---

def test_load_missing_file_returns_defaults(tmp_path):
    path = tmp_path / "does_not_exist.json"
    assert cfg.load_config(path) == RmnConfig()


def test_load_corrupt_json_returns_defaults(tmp_path):
    path = tmp_path / "rules_config.json"
    path.write_text("{ this is not valid json", encoding="utf-8")
    assert cfg.load_config(path) == RmnConfig()


def test_load_non_dict_json_returns_defaults(tmp_path):
    path = tmp_path / "rules_config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert cfg.load_config(path) == RmnConfig()


def test_load_partial_json_applies_field_and_defaults_rest(tmp_path):
    path = tmp_path / "rules_config.json"
    path.write_text(json.dumps({"sort_order": "asc"}), encoding="utf-8")
    loaded = cfg.load_config(path)
    assert loaded.sort_order == "asc"
    # Les autres champs restent aux défauts.
    assert loaded.temperature_placeholder == "[??? K]"
    assert loaded.bold_label is True
    assert loaded.multiplicities == RmnConfig().multiplicities


def test_config_from_dict_rejects_invalid_values():
    data = {
        "sort_order": "sideways",
        "temperature_unit": "Fahrenheit",
        "bold_label": "yes",
        "temperature_placeholder": 42,
        "multiplicities": {"s": 1, "ok": "ok", 3: "x"},
    }
    c = cfg.config_from_dict(data)
    assert c.sort_order == "desc"
    assert c.temperature_unit == "K"
    assert c.bold_label is True
    assert c.temperature_placeholder == "[??? K]"
    # Seules les paires str->str valides sont gardées.
    assert c.multiplicities == {"ok": "ok"}


def test_config_from_dict_empty_multiplicity_value_uses_key():
    c = cfg.config_from_dict({"multiplicities": {"sext": "   "}})
    assert c.multiplicities == {"sext": "sext"}


# --- Singleton get/set/reset ---

def test_set_then_get_returns_same_object():
    custom = RmnConfig(sort_order="none")
    cfg.set_config(custom)
    try:
        assert cfg.get_config() is custom
    finally:
        cfg.reset_config()


def test_reset_forces_reload():
    custom = RmnConfig(sort_order="asc")
    cfg.set_config(custom)
    assert cfg.get_config() is custom
    cfg.reset_config()
    reloaded = cfg.get_config()
    assert reloaded is not custom
    cfg.reset_config()


# --- Chemin par défaut résolu à l'appel (isolation des tests, dialogue) ---

def test_default_path_is_resolved_at_call_time(tmp_path, monkeypatch):
    path = tmp_path / "prefs.json"
    path.write_text('{"sort_order": "asc"}', encoding="utf-8")
    monkeypatch.setattr(cfg, "DEFAULT_CONFIG_PATH", path)

    assert cfg.load_config().sort_order == "asc"
    cfg.reset_config()
    assert cfg.get_config().sort_order == "asc"

    cfg.save_config(RmnConfig(sort_order="none"))
    assert cfg.load_config(path).sort_order == "none"
    cfg.reset_config()


def test_tests_never_read_project_config():
    # Garde-fou : conftest.py redirige la config vers un fichier temporaire.
    from pathlib import Path

    project_file = Path(__file__).resolve().parent.parent / "rules_config.json"
    assert cfg.DEFAULT_CONFIG_PATH != project_file
    assert cfg.LEGACY_CONFIG_PATH != project_file
    assert cfg.get_config() == RmnConfig()


# --- Emplacement du fichier de préférences (dossier utilisateur) ---

def test_user_config_path_windows():
    path = cfg.user_config_path({"APPDATA": "C:/Users/x/AppData/Roaming"}, "win32")
    assert path == Path("C:/Users/x/AppData/Roaming") / "StandardisationRMN" / "rules_config.json"


def test_user_config_path_linux_xdg_and_home():
    assert cfg.user_config_path({"XDG_CONFIG_HOME": "/cfg"}, "linux") == (
        Path("/cfg") / "standardisation-rmn" / "rules_config.json"
    )
    assert cfg.user_config_path({"HOME": "/home/x"}, "linux") == (
        Path("/home/x") / ".config" / "standardisation-rmn" / "rules_config.json"
    )


def test_user_config_path_env_override():
    env = {"APPDATA": "C:/a", "STANDARDISATION_RMN_CONFIG": "D:/portable/prefs.json"}
    assert cfg.user_config_path(env, "win32") == Path("D:/portable/prefs.json")


def test_save_config_creates_parent_directory(tmp_path):
    path = tmp_path / "nouveau" / "dossier" / "rules_config.json"
    cfg.save_config(RmnConfig(sort_order="asc"), path)
    assert cfg.load_config(path).sort_order == "asc"


def test_legacy_project_file_is_read_when_user_file_absent(tmp_path, monkeypatch):
    legacy = tmp_path / "ancien.json"
    legacy.write_text('{"sort_order": "none"}', encoding="utf-8")
    monkeypatch.setattr(cfg, "LEGACY_CONFIG_PATH", legacy)
    monkeypatch.setattr(cfg, "DEFAULT_CONFIG_PATH", tmp_path / "user" / "rules_config.json")

    assert cfg.load_config().sort_order == "none"
    # Le prochain enregistrement va dans le dossier utilisateur.
    cfg.save_config(RmnConfig(sort_order="asc"))
    assert cfg.load_config().sort_order == "asc"
    assert legacy.read_text(encoding="utf-8") == '{"sort_order": "none"}'
