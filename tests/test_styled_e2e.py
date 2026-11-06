"""Tests end-to-end de la sortie stylisée (FEAT-002).

- Standardisation d'un docx : vérifie qu'au moins un run est gras ET un run
  italique dans la sortie.
- Smoke-test GUI offscreen (QT_QPA_PLATFORM=offscreen) : la fenêtre liste des
  cases pour '1H NMR' et '13C NMR'.
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


def test_gui_lists_1h_and_13c_rules():
    # Smoke-test GUI en mode offscreen : la fenêtre principale s'instancie et
    # expose une case par règle disponible (1H NMR et 13C NMR).
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from ui.main_window import MainWindow

    window = MainWindow()
    names = set(window.rule_checkboxes.keys())
    assert "1H NMR" in names
    assert "13C NMR" in names
    window.close()
    _ = app
