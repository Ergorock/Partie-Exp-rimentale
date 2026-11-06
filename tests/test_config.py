"""Tests de la couche de configuration des règles RMN (FEAT-001).

Entièrement indépendants de PySide6. Les défauts de ``RmnConfig`` doivent
reproduire exactement le comportement actuel, et la persistance JSON doit être
tolérante (fichier absent / corrompu / partiel -> défauts champ par champ).
"""

import json

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
