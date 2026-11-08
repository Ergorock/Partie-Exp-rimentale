"""Tests de non-régression : sections collées, préfixes, mise en forme Word,
multiplicités inconnues, J multiples et encodage du CLI.
"""

import io
import sys

import pytest
from docx import Document as NewDocument
from docx.shared import Pt

from core import config as cfg
from core import docx_io
from core.config import RmnConfig
from core.processor import build_default_registry, process_document, process_texts
from core.rules.base import ActionKind, StyledSegment
from core.rules.nmr_13c import ThirteenCNmrRule
from core.rules.nmr_1h import OneHNmrRule

RULE_1H = OneHNmrRule()
RULE_13C = ThirteenCNmrRule()


@pytest.fixture(autouse=True)
def _default_config():
    cfg.set_config(RmnConfig())
    yield
    cfg.reset_config()


def _flagged(result) -> bool:
    return any(a.kind == ActionKind.FLAGGED for a in result.actions)


def _process_one(text: str):
    report = process_texts([text], build_default_registry())
    return report.paragraphs[0] if report.paragraphs else None


# --- Mise en forme Word préservée ---------------------------------------------

def test_styled_edit_keeps_font_of_paragraph():
    doc = NewDocument()
    p = doc.add_paragraph()
    r = p.add_run("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")
    r.font.name = "Times New Roman"
    r.font.size = Pt(12)

    process_document(doc, build_default_registry())

    assert p.text.startswith("¹H NMR")
    for run in p.runs:
        assert run.font.name == "Times New Roman"
        assert run.font.size == Pt(12)


def test_styled_edit_keeps_formatting_of_surrounding_runs():
    doc = NewDocument()
    p = doc.add_paragraph()
    before = p.add_run("Composé 3 : ")
    before.font.name = "Arial"
    before.italic = True
    p.add_run("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")

    process_document(doc, build_default_registry())

    first = p.runs[0]
    assert first.text == "Composé 3 : "
    assert first.font.name == "Arial"
    assert first.italic is True


def test_styled_segments_do_not_inherit_word_superscript():
    # '1' saisi en exposant Word : la sortie utilise l'exposant Unicode
    # uniquement, jamais le superscript Word.
    doc = NewDocument()
    p = doc.add_paragraph()
    sup = p.add_run("1")
    sup.font.superscript = True
    p.add_run("H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")

    process_document(doc, build_default_registry())

    assert p.text.startswith("¹H NMR")
    assert all(not run.font.superscript for run in p.runs)


def test_styled_edit_fallback_never_drops_rest_of_paragraph():
    doc = NewDocument()
    p = doc.add_paragraph("avant X apres")
    segments = [StyledSegment("GRAS", bold=True)]
    docx_io.apply_styled_edit(p, "avant X apres", "avant GRAS apres", "ABSENT", segments)
    assert p.text == "avant GRAS apres"


# --- Sections collées et préfixes ---------------------------------------------

MULTI = (
    "1H NMR (400 MHz, CDCl3, 298 K) δ 1.2 (s, 3H), 7.2 (s, 1H) "
    "13C NMR (101 MHz, CDCl3, 298 K) δ 20.1, 130.5"
)
MULTI_EXPECTED = (
    "¹H NMR (400 MHz, CDCl₃, 298 K) δ 7.2 (s, 1H), 1.2 (s, 3H) "
    "¹³C NMR (101 MHz, CDCl₃, 298 K) δ 130.5, 20.1"
)


def test_collated_13c_section_is_processed_in_texts():
    pr = _process_one(MULTI)
    assert pr.new_text == MULTI_EXPECTED


def test_collated_13c_section_is_processed_in_document():
    doc = NewDocument()
    p = doc.add_paragraph(MULTI)
    report = process_document(doc, build_default_registry())
    assert p.text == MULTI_EXPECTED
    assert report.paragraphs[0].new_text == p.text
    assert len([r for r in p.runs if r.bold]) == 2


def test_paragraph_with_prefix_is_processed():
    pr = _process_one("Compound 3: 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")
    assert pr.new_text == "Compound 3: ¹H NMR (400 MHz, CDCl₃, 298 K) δ 7.26 (s, 1H)"


def test_leading_space_is_processed_not_flagged():
    result = RULE_1H.apply(" 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")
    assert result.new_text == " ¹H NMR (400 MHz, CDCl₃, 298 K) δ 7.26 (s, 1H)"
    assert not _flagged(result)


def test_prose_mentioning_nmr_is_untouched():
    text = "The 1H NMR spectrum was recorded (see SI) and matches the literature."
    pr = _process_one(text)
    assert pr is None or pr.new_text == text


def test_nbsp_in_prefix_kept_consistent_in_document():
    text = "Compound\xa03: 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)"
    doc = NewDocument()
    p = doc.add_paragraph(text)
    report = process_document(doc, build_default_registry())
    assert p.text == report.paragraphs[0].new_text
    assert p.text.startswith("Compound\xa03: ¹H NMR")


def test_missing_delta_keeps_signals_and_adds_nothing():
    result = RULE_1H.apply("1H NMR (400 MHz, CDCl3, 298 K): 7.26 (s, 1H)")
    assert "7.26 (s, 1H)" in result.new_text
    assert "δ" not in result.new_text
    assert _flagged(result)


def test_text_before_delta_is_kept():
    result = RULE_1H.apply("1H NMR (400 MHz, CDCl3, 298 K) recorded at rt: δ 7.26 (s, 1H)")
    assert "recorded at rt: δ 7.26 (s, 1H)" in result.new_text
    assert _flagged(result)


def test_prose_between_label_and_parenthesis_is_not_dropped():
    text = "1H NMR spectrum at 400 MHz (CDCl3, 298 K) δ 7.26 (s, 1H)"
    result = RULE_1H.apply(text)
    assert result.new_text == text
    assert _flagged(result)


# --- Multiplicités inconnues et J multiples -----------------------------------

def test_unknown_multiplicity_is_flagged_and_kept():
    body = "7.26 (ddq, J = 7.5 Hz, 1H), 1.20 (t, 3H)"
    result = RULE_1H.apply(f"1H NMR (400 MHz, CDCl3, 298 K) δ {body}")
    assert result.new_text.endswith(f"δ {body}")
    assert _flagged(result)


def test_unknown_field_before_known_one_is_flagged():
    body = "7.26 (d, 2.0 Hz, 1H)"
    result = RULE_1H.apply(f"1H NMR (400 MHz, CDCl3, 298 K) δ {body}")
    assert result.new_text.endswith(f"δ {body}")
    assert _flagged(result)


def test_multiple_j_values_in_one_field():
    result = RULE_1H.apply("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (dd, J = 8.4, 2.1 Hz, 1H)")
    assert result.new_text.endswith("δ 7.26 (dd, J = 8.4, 2.1 Hz, 1H)")
    assert not _flagged(result)


def test_multiple_j_fields():
    result = RULE_1H.apply(
        "1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (dd, J = 8.4 Hz, J = 2.1 Hz, 1H)"
    )
    assert result.new_text.endswith("δ 7.26 (dd, J = 8.4 Hz, J = 2.1 Hz, 1H)")
    assert not _flagged(result)


def test_13c_attribution_still_accepted():
    result = RULE_13C.apply("13C NMR (101 MHz, CDCl3, 298 K) δ 21.7 (CH3), 140.2 (Cq)")
    assert result.new_text.endswith("δ 140.2 (Cq), 21.7 (CH₃)")
    assert not _flagged(result)


# --- CLI : console Windows (cp1252) -------------------------------------------

def test_cli_does_not_crash_on_cp1252_console(tmp_path, monkeypatch):
    import cli

    src = tmp_path / "in.docx"
    doc = NewDocument()
    doc.add_paragraph("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")
    doc.save(src)

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", stream)

    assert cli.main(["cli.py", str(src), str(tmp_path / "out.docx")]) == 0
    stream.flush()
    assert "¹H NMR".encode("utf-8") in buffer.getvalue()
