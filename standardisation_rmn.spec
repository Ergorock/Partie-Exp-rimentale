# -*- mode: python ; coding: utf-8 -*-
"""Construction des exécutables Windows avec PyInstaller.

Usage (depuis la racine du projet, dans le venv qui contient PyInstaller) :

    python -m PyInstaller standardisation_rmn.spec --noconfirm

Produit dans ``dist/`` deux exécutables autonomes (un seul fichier chacun) :

- ``StandardisationRMN.exe``     : interface graphique, sans console ;
- ``StandardisationRMN-cli.exe`` : ligne de commande, SANS Qt (plus léger).

Les modèles internes de python-docx (``docx/templates``) sont embarqués : ils
sont nécessaires pour créer les commentaires Word et les en-têtes.
"""

from PyInstaller.utils.hooks import collect_data_files

docx_data = collect_data_files("docx")

# Modules jamais utilisés : exclus pour réduire la taille.
COMMON_EXCLUDES = ["tkinter", "unittest", "pytest", "_pytest", "pydoc"]

# --- Interface graphique ---------------------------------------------------
gui = Analysis(
    ["app.py"],
    pathex=["."],
    datas=docx_data,
    excludes=COMMON_EXCLUDES,
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

# --- Ligne de commande (sans Qt) --------------------------------------------
cli = Analysis(
    ["cli.py"],
    pathex=["."],
    datas=docx_data,
    excludes=COMMON_EXCLUDES + ["PySide6", "shiboken6", "ui"],
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
