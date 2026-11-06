"""Tests du processor (Task 4)."""

import os

from core import docx_io, processor
from core.processor import build_default_registry, process_texts, standardize_file

EXAMPLE_DOCX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "partie exp.docx")


def test_process_texts_corrects_targeted_paragraph():
    texts = [
        "Introduction sans règle.",
        "1H NMR (400.18MHz, DMF-d7, 298 ): δ (ppm) = 9.18",
        "Autre paragraphe quelconque.",
    ]
    registry = build_default_registry()
    report = process_texts(texts, registry)

    # Un seul paragraphe ciblé.
    assert len(report.paragraphs) == 1
    pr = report.paragraphs[0]
    assert pr.index == 1
    assert "400.18 MHz" in pr.new_text
    assert "298 K" in pr.new_text
    assert pr.changed is True


def test_process_texts_leaves_others_untouched():
    texts = ["Rien à corriger ici."]
    report = process_texts(texts, build_default_registry())
    assert report.paragraphs == []


def test_standardize_file_writes_output(tmp_path):
    output = os.path.join(tmp_path, "sortie.docx")
    report = standardize_file(EXAMPLE_DOCX, output)

    assert os.path.exists(output)
    assert report.action_count >= 1

    # Vérifie que le fichier de sortie contient bien la correction.
    produced = docx_io.load(output)
    full_text = "\n".join(docx_io.paragraph_texts(produced))
    assert "400.18 MHz" in full_text
    assert "298 K" in full_text


def test_report_summary_is_readable():
    texts = ["1H NMR (400 MHz, CDCl3): δ = 1.0"]
    report = process_texts(texts, build_default_registry())
    summary = report.summary()
    assert "[??? K]" in report.paragraphs[0].new_text
    assert "MARQUEUR" in summary


# --- Préservation de la mise en forme à travers le processor ---

from docx import Document as NewDocument  # noqa: E402

from core.processor import process_document  # noqa: E402


def test_process_document_styles_1h_segment():
    # La règle 1H produit désormais une sortie stylisée : le segment label +
    # parenthèse est réécrit en gras et le δ en italique. Le style interne des
    # runs d'origine du segment 1H est volontairement remplacé par ce style
    # cible (ancienne assertion « run MHz reste italique » devenue obsolète).
    doc = NewDocument()
    p = doc.add_paragraph()
    p.add_run("1H NMR (400.18")
    p.add_run("MHz")
    p.add_run(", DMF-d7, 298 ): δ = 9.18 (s, 1H)")

    registry = build_default_registry()
    report = process_document(doc, registry)

    # La correction a bien eu lieu.
    assert report.changed_count == 1
    assert "400.18 MHz" in p.text
    assert "298 K" in p.text
    # Sortie stylisée : au moins un run gras et un run italique.
    assert any(r.bold is True for r in p.runs)
    assert any(r.italic is True for r in p.runs)


def test_process_document_preserves_runs_of_untouched_paragraph():
    # Un paragraphe hors règles conserve intégralement ses runs et leur style.
    doc = NewDocument()
    p = doc.add_paragraph()
    p.add_run("Texte ")
    r = p.add_run("important")
    r.bold = True
    p.add_run(" sans règle.")

    before = [(run.text, run.bold, run.italic) for run in p.runs]
    process_document(doc, build_default_registry())
    after = [(run.text, run.bold, run.italic) for run in p.runs]
    assert before == after
