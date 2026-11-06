# -*- mode: python ; coding: utf-8 -*-
"""Construction des exécutables Windows avec PyInstaller.

Usage (depuis la racine du projet, dans le venv qui contient PyInstaller) :

    python -m PyInstaller standardisation_rmn.spec --noconfirm

Produit dans ``dist/`` deux exécutables autonomes (un seul fichier chacun) :

- ``StandardisationRMN.exe``     : interface graphique (HTML/CSS dans une
  fenêtre native WebView2, via pywebview), sans console ;
- ``StandardisationRMN-cli.exe`` : ligne de commande, sans interface.

Embarqués : les fichiers de l'interface (``ui/web``) et les modèles internes de
python-docx (``docx/templates``, nécessaires aux commentaires Word et aux
en-têtes). Les moteurs d'interface inutilisés (Qt, GTK, CEF) sont exclus.
"""

from PyInstaller.utils.hooks import collect_data_files

docx_data = collect_data_files("docx")

# Modules jamais utilisés : exclus pour réduire la taille.
COMMON_EXCLUDES = ["tkinter", "unittest", "pytest", "_pytest", "pydoc"]
UNUSED_GUI_BACKENDS = ["PySide6", "shiboken6", "PyQt5", "PyQt6", "qtpy", "gi", "cefpython3"]

# --- Interface graphique ---------------------------------------------------
gui = Analysis(
    ["app.py"],
    pathex=["."],
    datas=docx_data + [("ui/web", "ui/web")],
    excludes=COMMON_EXCLUDES + UNUSED_GUI_BACKENDS,
    noarchive=False,
)
gui_pyz = PYZ(gui.pure)
gui_exe = EXE(
    gui_pyz,
    gui.scripts,
    gui.binaries,
    gui.datas,
    [],
    name="StandardisationRMN",
    console=False,
    upx=False,
)

# --- Ligne de commande (sans interface) --------------------------------------
cli = Analysis(
    ["cli.py"],
    pathex=["."],
    datas=docx_data,
    excludes=COMMON_EXCLUDES + UNUSED_GUI_BACKENDS + ["webview", "clr", "pythonnet", "ui"],
    noarchive=False,
)
cli_pyz = PYZ(cli.pure)
cli_exe = EXE(
    cli_pyz,
    cli.scripts,
    cli.binaries,
    cli.datas,
    [],
    name="StandardisationRMN-cli",
    console=True,
    upx=False,
)
