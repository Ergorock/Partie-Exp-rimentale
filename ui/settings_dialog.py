"""Dialogue modal PySide6 d'édition des paramètres des règles RMN.

Ce dialogue lit et écrit ``rules_config.json`` via ``core/config.py`` : il
remplit ses widgets depuis la configuration chargée, permet de la modifier, puis
sur validation l'enregistre (``save_config``) et l'applique immédiatement au
processus (``set_config``). Le cœur de traitement reste indépendant de Qt ; seul
ce module (et ``main_window``) importe PySide6.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from core import config as config_module
from core.config import (
    RmnConfig,
    config_from_dict,
    load_config,
    save_config,
    set_config,
)

# Libellés affichés dans la combo du sens de tri, mappés sur les valeurs internes.
_SORT_LABELS = (
    ("Décroissant (champs faibles → forts)", "desc"),
    ("Croissant", "asc"),
    ("Aucun tri", "none"),
)
_TEMPERATURE_UNIT_CHOICES = ("K", "\u00b0C")  # 'K' | '°C'


class SettingsDialog(QDialog):
    """Fenêtre modale d'édition des paramètres des règles RMN."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paramètres des règles RMN")
        self.setModal(True)
        self.resize(560, 520)

        layout = QVBoxLayout(self)

        # --- Multiplicités reconnues (entrée -> normalisée) ---
        layout.addWidget(QLabel("Multiplicités reconnues (entrée → normalisée) :"))
        self.multiplicities_table = QTableWidget(0, 2)
        self.multiplicities_table.setHorizontalHeaderLabels(["Entrée", "Normalisée"])
        self.multiplicities_table.horizontalHeader().setStretchLastSection(True)
        layout.addWidget(self.multiplicities_table)

        table_buttons = QHBoxLayout()
        self.add_row_button = QPushButton("Ajouter")
        self.add_row_button.clicked.connect(self._add_empty_row)
        self.remove_row_button = QPushButton("Retirer")
        self.remove_row_button.clicked.connect(self._remove_selected_row)
        table_buttons.addWidget(self.add_row_button)
        table_buttons.addWidget(self.remove_row_button)
        table_buttons.addStretch(1)
        layout.addLayout(table_buttons)

        # --- Autres paramètres ---
        form = QFormLayout()
        self.placeholder_edit = QLineEdit()
        form.addRow("Marqueur de donnée manquante :", self.placeholder_edit)

        self.sort_combo = QComboBox()
        for label, _value in _SORT_LABELS:
            self.sort_combo.addItem(label)
        form.addRow("Sens du tri des signaux :", self.sort_combo)

        self.temperature_unit_combo = QComboBox()
        for unit in _TEMPERATURE_UNIT_CHOICES:
            self.temperature_unit_combo.addItem(unit)
        form.addRow("Unité de température :", self.temperature_unit_combo)

        self.bold_label_check = QCheckBox("Label et parenthèse en gras")
        form.addRow(self.bold_label_check)

        self.italic_delta_check = QCheckBox("Symbole δ en italique")
        form.addRow(self.italic_delta_check)

        layout.addLayout(form)

        # --- Boutons OK / Annuler / Réinitialiser ---
        self.button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel | QDialogButtonBox.Reset
        )
        self.button_box.button(QDialogButtonBox.Ok).setText("OK")
        self.button_box.button(QDialogButtonBox.Cancel).setText("Annuler")
        self.button_box.button(QDialogButtonBox.Reset).setText("Réinitialiser")
        self.button_box.accepted.connect(self._on_ok)
        self.button_box.rejected.connect(self._on_cancel)
        self.button_box.button(QDialogButtonBox.Reset).clicked.connect(self._on_reset)
        layout.addWidget(self.button_box)

        # État initial depuis le fichier de préférences (ou défauts).
        self._load_into_widgets(load_config())

    # ------------------------------------------------------------------ #
    # Table des multiplicités
    # ------------------------------------------------------------------ #
    def _add_empty_row(self) -> None:
        row = self.multiplicities_table.rowCount()
        self.multiplicities_table.insertRow(row)
        self.multiplicities_table.setItem(row, 0, QTableWidgetItem(""))
        self.multiplicities_table.setItem(row, 1, QTableWidgetItem(""))

    def _remove_selected_row(self) -> None:
        row = self.multiplicities_table.currentRow()
        if row >= 0:
            self.multiplicities_table.removeRow(row)

    # ------------------------------------------------------------------ #
    # Synchronisation widgets <-> RmnConfig
    # ------------------------------------------------------------------ #
    def _load_into_widgets(self, config: RmnConfig) -> None:
        """Remplit tous les widgets depuis ``config``."""
        # Table des multiplicités.
        self.multiplicities_table.setRowCount(0)
        for key, value in config.multiplicities.items():
            row = self.multiplicities_table.rowCount()
            self.multiplicities_table.insertRow(row)
            self.multiplicities_table.setItem(row, 0, QTableWidgetItem(key))
            self.multiplicities_table.setItem(row, 1, QTableWidgetItem(value))

        self.placeholder_edit.setText(config.temperature_placeholder)

        sort_index = next(
            (i for i, (_label, value) in enumerate(_SORT_LABELS) if value == config.sort_order),
            0,
        )
        self.sort_combo.setCurrentIndex(sort_index)

        unit_index = next(
            (i for i, unit in enumerate(_TEMPERATURE_UNIT_CHOICES) if unit == config.temperature_unit),
            0,
        )
        self.temperature_unit_combo.setCurrentIndex(unit_index)

        self.bold_label_check.setChecked(config.bold_label)
        self.italic_delta_check.setChecked(config.italic_delta)

    def _collect_from_widgets(self) -> RmnConfig:
        """Construit une ``RmnConfig`` à partir de l'état courant des widgets."""
        multiplicities: dict[str, str] = {}
        for row in range(self.multiplicities_table.rowCount()):
            key_item = self.multiplicities_table.item(row, 0)
            value_item = self.multiplicities_table.item(row, 1)
            key = key_item.text().strip() if key_item else ""
            if not key:
                continue
            value = value_item.text().strip() if value_item else ""
            multiplicities[key] = value if value else key

        data = {
            "multiplicities": multiplicities,
            "temperature_placeholder": self.placeholder_edit.text(),
            "sort_order": _SORT_LABELS[self.sort_combo.currentIndex()][1],
            "bold_label": self.bold_label_check.isChecked(),
            "italic_delta": self.italic_delta_check.isChecked(),
            "temperature_unit": _TEMPERATURE_UNIT_CHOICES[
                self.temperature_unit_combo.currentIndex()
            ],
        }
        return config_from_dict(data)

    # ------------------------------------------------------------------ #
    # Actions OK / Annuler / Réinitialiser
    # ------------------------------------------------------------------ #
    def _on_ok(self) -> None:
        config = self._collect_from_widgets()
        # Résolution du chemin au moment de l'appel : respecte un éventuel
        # monkeypatch de ``DEFAULT_CONFIG_PATH`` (tests) et la configuration
        # courante du processus.
        save_config(config, config_module.DEFAULT_CONFIG_PATH)
        set_config(config)
        self.accept()

    def _on_cancel(self) -> None:
        self.reject()

    def _on_reset(self) -> None:
        # Remet les champs aux défauts dans le dialogue, sans écrire ni appliquer
        # tant que l'utilisateur n'a pas validé via OK.
        self._load_into_widgets(RmnConfig())
