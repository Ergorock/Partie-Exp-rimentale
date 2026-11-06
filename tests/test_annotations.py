"""Tests : commentaires Word posés sur les paragraphes à vérifier.

Les actions FLAGGED (à vérifier) et PLACEHOLDER (marqueur inséré) sont
reportées en commentaire Word sur le paragraphe concerné du fichier de sortie,
là où l'utilisateur corrige. Les corrections sûres (CORRECTED) n'en génèrent
pas.
"""

import os

from docx import Document as NewDocument
from docx.oxml.ns import qn

from core import docx_io
from core.processor import (
    COMMENT_AUTHOR,
    build_default_registry,
    process_document,
    standardize_file,
)

FLAGGED = "1H NMR (400 MHz, CDCl3, 298 K) δ 2.3 (s, 3H), bizarre, 7.5 (m, 1H)"
PLACEHOLDER = "1H NMR (400 MHz, CDCl3) δ 7.26 (s, 1H)"
CORRECT_ONLY = "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)"


def _comments(doc):
    return list(doc.comments)


def _has_reference(paragraph) -> bool:
    return bool(paragraph._p.findall(".//" + qn("w:commentReference")))


def test_flagged_paragraph_gets_comment():
    doc = NewDocument()
    p = doc.add_paragraph(FLAGGED)

    process_document(doc, build_default_registry(), annotate=True)

    comments = _comments(doc)
    assert len(comments) == 1
    assert comments[0].author == COMMENT_AUTHOR
    assert "À VÉRIFIER" in comments[0].text
    assert "signaux" in comments[0].text
    assert _has_reference(p)


def test_placeholder_paragraph_gets_comment():
    doc = NewDocument()
    doc.add_paragraph(PLACEHOLDER)
    process_document(doc, build_default_registry(), annotate=True)
    comments = _comments(doc)
    assert len(comments) == 1
    assert "MARQUEUR" in comments[0].text
    assert "Température absente" in comments[0].text


def test_corrected_only_paragraph_gets_no_comment():
    doc = NewDocument()
    doc.add_paragraph(CORRECT_ONLY)
    process_document(doc, build_default_registry(), annotate=True)
    assert _comments(doc) == []


def test_no_comment_when_annotation_disabled():
    doc = NewDocument()
    doc.add_paragraph(FLAGGED)
    process_document(doc, build_default_registry(), annotate=False)
    assert _comments(doc) == []


def test_header_paragraph_is_not_commented():
    # Word n'accepte de commentaires que dans le corps du document.
    doc = NewDocument()
    doc.sections[0].header.paragraphs[0].text = FLAGGED
    report = process_document(doc, build_default_registry(), annotate=True)
    assert _comments(doc) == []
    assert report.comment_count == 0


def test_second_pass_does_not_duplicate_comment():
    doc = NewDocument()
    p = doc.add_paragraph(FLAGGED)
    registry = build_default_registry()
    process_document(doc, registry, annotate=True)
    process_document(doc, registry, annotate=True)
    assert len(_comments(doc)) == 1
    assert _has_reference(p)


def test_existing_reviewer_comment_survives_correction():
    doc = NewDocument()
    p = doc.add_paragraph(CORRECT_ONLY)
    doc.add_comment(p.runs, text="Remarque du relecteur", author="Relecteur")

    process_document(doc, build_default_registry(), annotate=True)

    assert p.text.startswith("¹H NMR")
    assert _has_reference(p)
    assert [c.text for c in _comments(doc)] == ["Remarque du relecteur"]


def test_existing_comment_survives_text_edit():
    doc = NewDocument()
    p = doc.add_paragraph("avant")
    doc.add_comment(p.runs, text="note", author="Relecteur")
    assert docx_io.apply_text_edit(p, "avant", "avant !")
    assert p.text == "avant !"
    assert _has_reference(p)


def test_comments_saved_and_counted(tmp_path):
    src = os.path.join(tmp_path, "in.docx")
    out = os.path.join(tmp_path, "out.docx")
    doc = NewDocument()
    doc.add_paragraph(FLAGGED)
    doc.add_paragraph(CORRECT_ONLY)
    doc.save(src)

    report = standardize_file(src, out)

    assert report.comment_count == 1
    assert "1 commentaire(s) Word" in report.summary()
    assert len(_comments(docx_io.load(out))) == 1


def test_cli_option_disables_comments(tmp_path):
    import cli

    src = os.path.join(tmp_path, "in.docx")
    out = os.path.join(tmp_path, "out.docx")
    doc = NewDocument()
    doc.add_paragraph(FLAGGED)
    doc.save(src)

    assert cli.main(["cli.py", "--sans-commentaires", src, out]) == 0
    assert _comments(docx_io.load(out)) == []


def test_controller_annotate_option(tmp_path):
    from ui.controller import run_standardization

    src = os.path.join(tmp_path, "in.docx")
    doc = NewDocument()
    doc.add_paragraph(FLAGGED)
    doc.save(src)

    with_comments = os.path.join(tmp_path, "a.docx")
    without = os.path.join(tmp_path, "b.docx")
    assert run_standardization(src, with_comments).success
    assert run_standardization(src, without, annotate=False).success
    assert len(_comments(docx_io.load(with_comments))) == 1
    assert _comments(docx_io.load(without)) == []
