"""Fenêtre principale PySide6 de l'outil de standardisation."""

from __future__ import annotations

import os

from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.controller import (
    list_rules,
    output_path_for_new_input,
    run_standardization,
    suggest_output_path,
)


class MainWindow(QMainWindow):
    """Fenêtre : charger un docx, choisir la sortie, standardiser, voir le rapport."""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Standardisation partie expérimentale")
        self.resize(820, 600)

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Fichier d'entrée ---
        layout.addWidget(QLabel("Fichier d'entrée (.docx) :"))
        input_row = QHBoxLayout()
        self.input_edit = QLineEdit()
        self.input_edit.setPlaceholderText("Sélectionnez un fichier .docx à standardiser…")
        self.input_edit.setReadOnly(True)
        browse_in = QPushButton("Charger…")
        browse_in.clicked.connect(self._choose_input)
        input_row.addWidget(self.input_edit)
        input_row.addWidget(browse_in)
        layout.addLayout(input_row)

        # --- Fichier de sortie ---
        layout.addWidget(QLabel("Fichier de sortie (.docx) :"))
        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("Chemin du fichier standardisé…")
        browse_out = QPushButton("Parcourir…")
        browse_out.clicked.connect(self._choose_output)
        output_row.addWidget(self.output_edit)
        output_row.addWidget(browse_out)
        layout.addLayout(output_row)

        # --- Gestion des règles (activer / désactiver) ---
        rules_box = QGroupBox("Règles à appliquer")
        rules_layout = QVBoxLayout(rules_box)
        self.rule_checkboxes: dict[str, QCheckBox] = {}
        for info in list_rules():
            cb = QCheckBox(info.name)
            cb.setChecked(True)
            if info.description:
                cb.setToolTip(info.description)
                # Petite description sous la case pour la lisibilité.
                sub = QLabel(info.description)
                sub.setWordWrap(True)
                sub.setStyleSheet("color: gray; margin-left: 20px;")
                rules_layout.addWidget(cb)
                rules_layout.addWidget(sub)
            else:
                rules_layout.addWidget(cb)
            self.rule_checkboxes[info.name] = cb
        layout.addWidget(rules_box)

        # --- Commentaires Word sur les points à vérifier ---
        self.annotate_check = QCheckBox(
            "Ajouter un commentaire Word sur chaque paragraphe à vérifier"
        )
        self.annotate_check.setChecked(True)
        self.annotate_check.setToolTip(
            "Les signalements (« à vérifier », marqueurs insérés) apparaissent "
            "dans le fichier de sortie, en commentaire sur le paragraphe concerné."
        )
        layout.addWidget(self.annotate_check)

        # --- Bouton Paramètres ---
        self.settings_button = QPushButton("Paramètres")
        self.settings_button.clicked.connect(self._open_settings)
        layout.addWidget(self.settings_button)

        # --- Bouton Standardiser ---
        self.run_button = QPushButton("Standardiser")
        self.run_button.setMinimumHeight(40)
        self.run_button.clicked.connect(self._run)
        layout.addWidget(self.run_button)

        # --- Rapport ---
        layout.addWidget(QLabel("Rapport des corrections :"))
        self.report_view = QPlainTextEdit()
        self.report_view.setReadOnly(True)
        self.report_view.setFont(QFont("Consolas", 10))
        layout.addWidget(self.report_view, stretch=1)

    # ------------------------------------------------------------------ #
    # Actions UI
    # ------------------------------------------------------------------ #
    def _choose_input(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Choisir un fichier .docx", "", "Documents Word (*.docx)"
        )
        if path:
            previous = self.input_edit.text()
            self.input_edit.setText(path)
            self.output_edit.setText(
                output_path_for_new_input(previous, self.output_edit.text(), path)
            )

    def _choose_output(self) -> None:
        start = self.output_edit.text() or (
            suggest_output_path(self.input_edit.text()) if self.input_edit.text() else ""
        )
        path, _ = QFileDialog.getSaveFileName(
            self, "Enregistrer sous", start, "Documents Word (*.docx)"
        )
        if path:
            if not path.lower().endswith(".docx"):
                path += ".docx"
            self.output_edit.setText(path)

    def _open_settings(self) -> None:
        # Import local pour éviter tout import circulaire au chargement du module.
        from ui.settings_dialog import SettingsDialog

        dialog = SettingsDialog(self)
        dialog.exec()

    def _selected_rule_names(self) -> set[str]:
        """Noms des règles cochées dans l'interface."""
        return {name for name, cb in self.rule_checkboxes.items() if cb.isChecked()}

    def _run(self) -> None:
        input_path = self.input_edit.text().strip()
        output_path = self.output_edit.text().strip()
        if input_path and not output_path:
            output_path = suggest_output_path(input_path)
            self.output_edit.setText(output_path)

        enabled = self._selected_rule_names()
        outcome = run_standardization(
            input_path, output_path, enabled, annotate=self.annotate_check.isChecked()
        )
        if not outcome.success:
            QMessageBox.warning(self, "Impossible de standardiser", outcome.message)
            return

        summary = outcome.report.summary() if outcome.report else ""
        self.report_view.setPlainText(f"{outcome.message}\n\n{summary}")
        QMessageBox.information(self, "Standardisation terminée", outcome.message)
