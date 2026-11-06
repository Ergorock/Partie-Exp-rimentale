"""Tests de l'API exposée à l'interface web (pywebview), sans fenêtre.

Les boîtes de dialogue de fichiers sont remplacées par un faux : l'API se teste
entièrement sans pywebview ni WebView2.
"""

import os
import re
from pathlib import Path

from docx import Document as NewDocument

from core import config as cfg
from core.config import RmnConfig
from ui.controller import report_to_dict, suggest_output_path
from ui.web_api import Api, web_root

FLAGGED = "1H NMR (400 MHz, CDCl3, 298 K) δ 2.3 (s, 3H), bizarre, 7.5 (m, 1H)"
CORRECT_ONLY = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)"


class FakeDialogs:
    def __init__(self, open_path=None, save_path=None):
        self.open_path = open_path
        self.save_path = save_path
        self.save_default = None

    def open_docx(self):
        return self.open_path

    def save_docx(self, default_path):
        self.save_default = default_path
        return self.save_path


def _docx(tmp_path, *paragraphs, name="in.docx"):
    path = os.path.join(tmp_path, name)
    doc = NewDocument()
    for text in paragraphs:
        doc.add_paragraph(text)
    doc.save(path)
    return path


# --- État initial ---------------------------------------------------------------

def test_initial_state_lists_rules_and_settings():
    state = Api(FakeDialogs()).get_state()
    assert [r["name"] for r in state["rules"]] == ["1H NMR", "13C NMR"]
    assert state["settings"]["sort_order"] == "desc"
    assert state["defaults"] == cfg.config_to_dict(RmnConfig())


# --- Choix des fichiers ---------------------------------------------------------

def test_choose_input_suggests_output():
    api = Api(FakeDialogs(open_path="C:/x/A.docx"))
    assert api.choose_input("", "") == {
        "input": "C:/x/A.docx",
        "output": suggest_output_path("C:/x/A.docx"),
    }


def test_choose_input_replaces_output_of_previous_file():
    api = Api(FakeDialogs(open_path="C:/x/B.docx"))
    result = api.choose_input("C:/x/A.docx", "C:/x/A_standardise.docx")
    assert result["output"] == suggest_output_path("C:/x/B.docx")


def test_choose_input_cancelled_returns_none():
    assert Api(FakeDialogs(open_path=None)).choose_input("", "") is None


def test_set_input_from_drop_uses_same_logic():
    api = Api(FakeDialogs())
    result = api.set_input("C:/x/B.docx", "C:/x/A.docx", "C:/x/A_standardise.docx")
    assert result["output"] == suggest_output_path("C:/x/B.docx")
    assert api.set_input("C:/x/notes.txt", "", "") is None


def test_choose_output_adds_extension_and_passes_default():
    dialogs = FakeDialogs(save_path="C:/x/resultat")
    assert Api(dialogs).choose_output("C:/x/A_standardise.docx") == "C:/x/resultat.docx"
    assert dialogs.save_default == "C:/x/A_standardise.docx"


# --- Standardisation et rapport -------------------------------------------------

def test_run_returns_structured_report(tmp_path):
    src = _docx(tmp_path, "Introduction", FLAGGED, CORRECT_ONLY)
    out = os.path.join(tmp_path, "out.docx")

    result = Api(FakeDialogs()).run(src, out, ["1H NMR", "13C NMR"], True)

    assert result["success"] is True
    assert result["output_path"] == out
    report = result["report"]
    assert report["counts"] == {"corrected": 2, "flagged": 1, "placeholder": 0}
    assert report["comments"] == 1
    assert [p["label"] for p in report["paragraphs"]] == ["Paragraphe 2", "Paragraphe 3"]
    flagged = report["paragraphs"][0]
    assert flagged["needs_review"] is True
    assert flagged["after"].startswith("¹H NMR")
    assert {"kind": "flagged", "label": "À vérifier"} == {
        k: flagged["actions"][-1][k] for k in ("kind", "label")
    }
    assert report["paragraphs"][1]["needs_review"] is False


def test_run_reports_errors_without_raising(tmp_path):
    src = _docx(tmp_path, CORRECT_ONLY)
    result = Api(FakeDialogs()).run(src, src, ["1H NMR"], True)
    assert result["success"] is False
    assert "entrée" in result["message"]
    assert result["report"] is None


def test_run_with_no_rule_selected(tmp_path):
    src = _docx(tmp_path, CORRECT_ONLY)
    result = Api(FakeDialogs()).run(src, os.path.join(tmp_path, "o.docx"), [], True)
    assert result["success"] is False


def test_report_to_dict_empty_report():
    from core.processor import ProcessingReport

    data = report_to_dict(ProcessingReport())
    assert data["paragraphs"] == []
    assert data["counts"] == {"corrected": 0, "flagged": 0, "placeholder": 0}


# --- Paramètres -----------------------------------------------------------------

def test_save_settings_writes_applies_and_normalizes():
    api = Api(FakeDialogs())
    saved = api.save_settings(
        {
            "multiplicities": {"Td": "td", "s": "s"},
            "temperature_placeholder": "[??? °C]",
            "sort_order": "n'importe quoi",
            "bold_label": False,
            "italic_delta": True,
            "temperature_unit": "°C",
        }
    )
    assert saved["multiplicities"] == {"td": "td", "s": "s"}
    assert saved["sort_order"] == "desc"  # valeur invalide -> défaut
    assert cfg.get_config().temperature_unit == "°C"
    assert cfg.load_config().bold_label is False


# --- Ouverture du résultat ------------------------------------------------------

def test_open_output_refuses_missing_file(tmp_path):
    assert Api(FakeDialogs()).open_output(os.path.join(tmp_path, "absent.docx")) is False


# --- Fichiers de l'interface ------------------------------------------------------

def test_web_assets_are_local_only():
    root = Path(web_root())
    html = (root / "index.html").read_text(encoding="utf-8")
    for asset in re.findall(r'(?:src|href)="([^"]+)"', html):
        assert not asset.startswith(("http:", "https:", "//")), asset
        assert (root / asset).exists(), asset


def test_api_exposes_no_public_window_attribute():
    # pywebview expose au JavaScript tous les attributs publics de l'API.
    api = Api(FakeDialogs())
    public = [n for n in vars(api) if not n.startswith("_")]
    assert public == []


# --- Glisser-déposer --------------------------------------------------------------

def test_dropped_path_reads_pywebview_full_path():
    from ui.web_api import dropped_path

    event = {"dataTransfer": {"files": [{"name": "a.docx", "pywebviewFullPath": "C:/x/a.docx"}]}}
    assert dropped_path(event) == "C:/x/a.docx"
    assert dropped_path({"dataTransfer": {"files": []}}) is None
    assert dropped_path({}) is None
