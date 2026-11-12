"""Tests end-to-end de la sortie stylisée (FEAT-002).

- Standardisation d'un docx : vérifie qu'au moins un run est gras ET un run
  italique dans la sortie.
"""

import os

from docx import Document as NewDocument

from core import docx_io, processor


def test_styled_docx_output_has_bold_and_italic_runs(tmp_path):
    # Document construit avec un paragraphe 1H NMR à reformater.
    doc = NewDocument()
    doc.add_paragraph(
        "1H NMR (400.18MHz, DMF-d7, 298) δ 9.18 (dd, J = 4.7 Hz, 2H), 8.35 (bs, 2H)"
    )
    src = os.path.join(tmp_path, "in.docx")
    out = os.path.join(tmp_path, "out.docx")
    doc.save(src)

    report = processor.standardize_file(src, out)
    assert report.action_count >= 1

    produced = docx_io.load(out)
    runs = [r for p in produced.paragraphs for r in p.runs]
    assert any(r.bold is True for r in runs), "Au moins un run doit être gras"
    assert any(r.italic is True for r in runs), "Au moins un run doit être italique"


def test_ir_docx_only_label_is_bold(tmp_path):
    doc = NewDocument()
    doc.add_paragraph("IR (ATR) 1715, 3420 cm-1")
    src = os.path.join(tmp_path, "in.docx")
    out = os.path.join(tmp_path, "out.docx")
    doc.save(src)

    processor.standardize_file(src, out)

    paragraph = docx_io.load(out).paragraphs[0]
    assert paragraph.text == "IR (ATR): ν\u0303(cm⁻¹) = 3420, 1715"
    assert "".join(r.text for r in paragraph.runs if r.bold) == "IR"
    assert not any(r.italic for r in paragraph.runs)
