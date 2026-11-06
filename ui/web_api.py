"""API Python exposée à l'interface web (pywebview).

L'interface (``ui/web/index.html``) appelle ces méthodes via
``window.pywebview.api.<méthode>(...)``. Chaque méthode renvoie des données
JSON-compatibles et ne lève pas d'exception pour une erreur attendue : le
message est renvoyé pour être affiché.

pywebview expose au JavaScript tous les attributs PUBLICS de l'objet API : la
fenêtre et les boîtes de dialogue sont donc rangées dans des attributs privés.
Les boîtes de dialogue sont injectables (``dialogs``) pour tester l'API sans
fenêtre ; ``WebviewDialogs`` est l'implémentation réelle.
"""

from __future__ import annotations

import os
import sys
from typing import List, Optional

from core import config as config_module
from core.config import config_from_dict, config_to_dict, get_config, set_config
from ui.controller import (
    list_rules,
    output_path_for_new_input,
    report_to_dict,
    run_standardization,
)

DOCX_FILTER = "Documents Word (*.docx)"


def web_root() -> str:
    """Dossier des fichiers de l'interface (``ui/web``), y compris dans l'exécutable."""
    base = getattr(sys, "_MEIPASS", None)  # exécutable PyInstaller
    if base:
        return os.path.join(base, "ui", "web")
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")


def dropped_path(event: dict) -> Optional[str]:
    """Chemin complet du premier fichier d'un événement ``drop`` pywebview.

    Le JavaScript ne connaît pas le chemin d'un fichier déposé ; pywebview
    l'ajoute côté Python dans ``dataTransfer.files[i].pywebviewFullPath``.
    """
    files = ((event or {}).get("dataTransfer") or {}).get("files") or []
    for file in files:
        path = file.get("pywebviewFullPath") if isinstance(file, dict) else None
        if path:
            return path
    return None


class WebviewDialogs:
    """Boîtes de dialogue de fichiers natives, via la fenêtre pywebview."""

    def __init__(self) -> None:
        self._window = None

    def attach(self, window) -> None:
        self._window = window

    def open_docx(self) -> Optional[str]:
        import webview

        result = self._window.create_file_dialog(
            webview.FileDialog.OPEN, file_types=(DOCX_FILTER,)
        )
        return result[0] if result else None

    def save_docx(self, default_path: str) -> Optional[str]:
        import webview

        directory, filename = os.path.split(default_path) if default_path else ("", "")
        result = self._window.create_file_dialog(
            webview.FileDialog.SAVE,
            directory=directory,
            save_filename=filename,
            file_types=(DOCX_FILTER,),
        )
        if not result:
            return None
        return result if isinstance(result, str) else result[0]


class Api:
    """Méthodes appelées par l'interface web."""

    def __init__(self, dialogs) -> None:
        self._dialogs = dialogs

    # ------------------------------------------------------------------ #
    # État initial
    # ------------------------------------------------------------------ #
    def get_state(self) -> dict:
        """Règles disponibles, paramètres actifs et paramètres par défaut."""
        return {
            "rules": [{"name": r.name, "description": r.description} for r in list_rules()],
            "settings": config_to_dict(get_config()),
            "defaults": config_to_dict(config_module.RmnConfig()),
        }

    # ------------------------------------------------------------------ #
    # Fichiers
    # ------------------------------------------------------------------ #
    def choose_input(self, previous_input: str, current_output: str) -> Optional[dict]:
        """Ouvre le sélecteur de fichier d'entrée ; ``None`` si annulé."""
        path = self._dialogs.open_docx()
        if not path:
            return None
        return self.set_input(path, previous_input, current_output)

    def set_input(
        self, path: str, previous_input: str, current_output: str
    ) -> Optional[dict]:
        """Définit le fichier d'entrée (choisi ou déposé) et la sortie proposée.

        Renvoie ``None`` si le fichier n'est pas un ``.docx``.
        """
        if not path or not path.lower().endswith(".docx"):
            return None
        return {
            "input": path,
            "output": output_path_for_new_input(previous_input, current_output, path),
        }

    def choose_output(self, current_output: str) -> Optional[str]:
        """Ouvre le sélecteur de fichier de sortie ; ``None`` si annulé."""
        path = self._dialogs.save_docx(current_output)
        if not path:
            return None
        return path if path.lower().endswith(".docx") else f"{path}.docx"

    # ------------------------------------------------------------------ #
    # Standardisation
    # ------------------------------------------------------------------ #
    def run(
        self, input_path: str, output_path: str, enabled: List[str], annotate: bool
    ) -> dict:
        """Standardise le document ; renvoie succès, message et rapport structuré."""
        outcome = run_standardization(
            input_path, output_path, set(enabled), annotate=bool(annotate)
        )
        return {
            "success": outcome.success,
            "message": outcome.message,
            "output_path": outcome.output_path,
            "report": report_to_dict(outcome.report) if outcome.report else None,
        }

    def open_output(self, path: str) -> bool:
        """Ouvre le fichier produit dans l'application associée (Word)."""
        if not path or not os.path.exists(path) or not hasattr(os, "startfile"):
            return False
        os.startfile(path)  # noqa: S606 - fichier choisi par l'utilisateur
        return True

    # ------------------------------------------------------------------ #
    # Paramètres
    # ------------------------------------------------------------------ #
    def save_settings(self, data: dict) -> dict:
        """Valide, enregistre et applique les paramètres ; renvoie la version retenue."""
        config = config_from_dict(data)
        config_module.save_config(config)
        set_config(config)
        return config_to_dict(config)
