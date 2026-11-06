"""Tests : portée du traitement (tableaux, en-têtes, pieds de page), protection
du fichier d'entrée et casse des multiplicités configurées.
"""

import os

import pytest
from docx import Document as NewDocument

from core import config as cfg
from core import docx_io
from core.config import RmnConfig, config_from_dict
from core.processor import build_default_registry, process_document, standardize_file
from core.rules.nmr_1h import OneHNmrRule

RAW = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)"
DONE = "¹H NMR (400 MHz, CDCl₃, 298 K) δ 7.26 (s, 1H)"


@pytest.fixture(autouse=True)
def _default_config():
    cfg.set_config(RmnConfig())
    yield
    cfg.reset_config()


# --- Tableaux, en-têtes, pieds de page ----------------------------------------

def test_paragraph_in_table_is_processed():
    doc = NewDocument()
    table = doc.add_table(rows=1, cols=2)
    table.cell(0, 1).paragraphs[0].text = RAW

    report = process_document(doc, build_default_registry())

    assert table.cell(0, 1).paragraphs[0].text == DONE
    assert "Tableau 1" in report.summary()


def test_nested_table_is_processed():
    doc = NewDocument()
    outer = doc.add_table(rows=1, cols=1)
    inner = outer.cell(0, 0).add_table(rows=1, cols=1)
    inner.cell(0, 0).paragraphs[0].text = RAW

    process_document(doc, build_default_registry())

    assert inner.cell(0, 0).paragraphs[0].text == DONE


def test_merged_cells_processed_once():
    doc = NewDocument()
    table = doc.add_table(rows=1, cols=2)
    merged = table.cell(0, 0).merge(table.cell(0, 1))
    merged.paragraphs[0].text = RAW

    report = process_document(doc, build_default_registry())

    assert merged.paragraphs[0].text == DONE
    assert len(report.paragraphs) == 1


def test_header_and_footer_are_processed():
    doc = NewDocument()
    section = doc.sections[0]
    section.header.paragraphs[0].text = RAW
    section.footer.paragraphs[0].text = RAW

    report = process_document(doc, build_default_registry())

    assert section.header.paragraphs[0].text == DONE
    assert section.footer.paragraphs[0].text == DONE
    summary = report.summary()
    assert "En-tête" in summary and "Pied de page" in summary


def test_body_paragraph_label_unchanged():
    doc = NewDocument()
    doc.add_paragraph("Introduction")
    doc.add_paragraph(RAW)
    report = process_document(doc, build_default_registry())
    assert report.paragraphs[0].index == 1
    assert "Paragraphe 2 :" in report.summary()


# --- Protection du fichier d'entrée -------------------------------------------

def _make_docx(path):
    doc = NewDocument()
    doc.add_paragraph(RAW)
    doc.save(path)


def test_standardize_file_refuses_to_overwrite_input(tmp_path):
    src = os.path.join(tmp_path, "in.docx")
    _make_docx(src)
    with pytest.raises(ValueError):
        standardize_file(src, src)
    # L'entrée est intacte.
    assert docx_io.paragraph_texts(docx_io.load(src)) == [RAW]


def test_standardize_file_refuses_same_file_other_spelling(tmp_path):
    src = os.path.join(tmp_path, "in.docx")
    _make_docx(src)
    other = os.path.join(tmp_path, ".", "IN.docx") if os.name == "nt" else os.path.join(
        tmp_path, ".", "in.docx"
    )
    with pytest.raises(ValueError):
        standardize_file(src, other)


def test_controller_reports_overwrite_attempt(tmp_path):
    from ui.controller import run_standardization

    src = os.path.join(tmp_path, "in.docx")
    _make_docx(src)
    outcome = run_standardization(src, src)
    assert outcome.success is False
    assert "entrée" in outcome.message.lower()


def test_cli_refuses_to_overwrite_input(tmp_path, capsys):
    import cli

    src = os.path.join(tmp_path, "in.docx")
    _make_docx(src)
    assert cli.main(["cli.py", src, src]) == 1
    assert docx_io.paragraph_texts(docx_io.load(src)) == [RAW]


# --- Casse des multiplicités configurées --------------------------------------

def test_multiplicity_keys_are_case_insensitive():
    config = config_from_dict({"multiplicities": {"Td": "td", " BR S ": "br s"}})
    assert "td" in config.multiplicities
    assert "br s" in config.multiplicities

    cfg.set_config(config)
    result = OneHNmrRule().apply("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (td, J = 7.5 Hz, 1H)")
    assert result.new_text.endswith("δ 7.26 (td, J = 7.5 Hz, 1H)")
    assert all(a.kind.value != "flagged" for a in result.actions)
