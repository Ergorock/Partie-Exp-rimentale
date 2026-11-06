"""Smoke-test GUI offscreen du dialogue Paramètres et de son câblage (FEAT-002)."""

import os

# Doit être défini AVANT l'import de QtWidgets, sinon les tests GUI plantent.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

from PySide6.QtWidgets import QApplication, QPushButton

from core import config as config_module
from core.config import RmnConfig, load_config, reset_config
from ui.main_window import MainWindow
from ui.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture(autouse=True)
def _reset_config_after_test():
    yield
    reset_config()


def test_main_window_has_settings_button(qapp):
    window = MainWindow()
    buttons = window.findChildren(QPushButton)
    assert any(b.text() == "Paramètres" for b in buttons)
    assert hasattr(window, "_open_settings")


def test_settings_dialog_builds_with_expected_widgets(qapp):
    dialog = SettingsDialog()
    assert dialog.isModal()
    assert dialog.multiplicities_table is not None
    assert dialog.placeholder_edit is not None
    assert dialog.sort_combo is not None
    assert dialog.temperature_unit_combo is not None
    assert dialog.bold_label_check is not None
    assert dialog.italic_delta_check is not None


def test_on_ok_writes_config_and_reloads(qapp, tmp_path, monkeypatch):
    config_path = tmp_path / "rules_config.json"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    dialog = SettingsDialog()
    # Modifier deux champs.
    dialog.bold_label_check.setChecked(False)
    dialog.placeholder_edit.setText("[MANQUANT]")
    dialog._on_ok()

    assert config_path.exists()
    reloaded = load_config(config_path)
    assert reloaded.bold_label is False
    assert reloaded.temperature_placeholder == "[MANQUANT]"


def test_on_reset_restores_defaults_without_writing(qapp, tmp_path, monkeypatch):
    config_path = tmp_path / "rules_config.json"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)

    dialog = SettingsDialog()
    dialog.bold_label_check.setChecked(False)
    dialog.placeholder_edit.setText("[MANQUANT]")

    dialog._on_reset()

    defaults = RmnConfig()
    assert dialog.bold_label_check.isChecked() is defaults.bold_label
    assert dialog.placeholder_edit.text() == defaults.temperature_placeholder
    assert not config_path.exists()
