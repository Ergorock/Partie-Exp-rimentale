"""Tests du module docx_io (Task 1)."""

import os

import pytest

from core import docx_io

EXAMPLE_DOCX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "partie exp.docx")


@pytest.fixture
def example_document():
    return docx_io.load(EXAMPLE_DOCX)


def test_load_returns_document(example_document):
    assert example_document is not None


def test_paragraph_texts_not_empty(example_document):
    texts = docx_io.paragraph_texts(example_document)
    assert isinstance(texts, list)
    assert any(t.strip() for t in texts), "Le document devrait contenir du texte"


def test_contains_1h_nmr_paragraph(example_document):
    texts = docx_io.paragraph_texts(example_document)
    assert any(t.strip().startswith("1H NMR") for t in texts), (
        "Au moins un paragraphe devrait commencer par '1H NMR'"
    )


# --- Préservation de la mise en forme : apply_text_edit ---

from docx import Document as NewDocument  # noqa: E402


def _para_with_runs(specs):
    """Crée un paragraphe avec des runs (texte, bold, italic) pour les tests."""
    doc = NewDocument()
    p = doc.add_paragraph()
    for text, bold, italic in specs:
        r = p.add_run(text)
        r.bold = bold
        r.italic = italic
    return p


def test_apply_text_edit_preserves_untouched_run_formatting():
    # "1H NMR (400.18" | "MHz" (italic) | ", DMF-d7, 298 )"
    p = _para_with_runs(
        [
            ("1H NMR (400.18", None, None),
            ("MHz", None, True),
            (", DMF-d7, 298 )", None, None),
        ]
    )
    old = p.text
    new = old.replace("400.18MHz", "400.18 MHz").replace("298 )", "298 K)")

    docx_io.apply_text_edit(p, old, new)

    assert p.text == new
    # Le run "MHz" doit rester italique.
    italic_runs = [r for r in p.runs if r.text.strip() == "MHz"]
    assert italic_runs and italic_runs[0].italic is True


def test_apply_text_edit_handles_insertion_inside_run():
    p = _para_with_runs([("298 )", True, None)])
    old = p.text
    new = "298 K)"
    docx_io.apply_text_edit(p, old, new)
    assert p.text == "298 K)"
    # Le style gras du run d'origine est conservé.
    assert p.runs[0].bold is True


def test_apply_text_edit_noop_when_text_unchanged():
    p = _para_with_runs([("hello ", True, None), ("world", None, True)])
    runs_before = [(r.text, r.bold, r.italic) for r in p.runs]
    docx_io.apply_text_edit(p, p.text, p.text)
    runs_after = [(r.text, r.bold, r.italic) for r in p.runs]
    assert runs_before == runs_after


# --- Moteur de sortie stylisée : apply_styled_edit (FEAT-001) ---

from core.rules.base import StyledSegment  # noqa: E402


def test_apply_styled_edit_replaces_substring_and_preserves_around():
    # "avant " | "PORTION" | " apres"
    p = _para_with_runs(
        [
            ("avant ", None, None),
            ("PORTION", None, None),
            (" apres", None, None),
        ]
    )
    old = p.text  # "avant PORTION apres"
    segments = [
        StyledSegment("gras", bold=True),
        StyledSegment("ital", italic=True),
    ]
    new = old.replace("PORTION", "grasital")

    docx_io.apply_styled_edit(p, old, new, "PORTION", segments)

    assert p.text == "avant grasital apres"
    # Le texte avant et après la portion est conservé.
    assert p.runs[0].text == "avant "
    assert p.runs[-1].text == " apres"


def test_apply_styled_edit_segment_bold_italic_flags():
    p = _para_with_runs([("X", None, None)])
    segments = [
        StyledSegment("B", bold=True),
        StyledSegment("I", italic=True),
    ]
    docx_io.apply_styled_edit(p, "X", "BI", "X", segments)

    by_text = {r.text: r for r in p.runs}
    assert by_text["B"].bold is True
    assert by_text["I"].italic is True


def test_apply_styled_edit_fallback_when_replaced_text_not_found():
    p = _para_with_runs([("texte initial", None, None)])
    segments = [
        StyledSegment("Gras", bold=True),
        StyledSegment(" normal", bold=False),
    ]
    # "ABSENT" n'existe pas -> repli : tout le paragraphe est réécrit.
    docx_io.apply_styled_edit(p, "texte initial", "Gras normal", "ABSENT", segments)

    assert p.text == "Gras normal"
    bold_runs = [r for r in p.runs if r.bold is True]
    assert bold_runs and bold_runs[0].text == "Gras"


def test_apply_styled_edit_replaces_whole_paragraph_when_replaced_none():
    p = _para_with_runs([("ancien", None, None)])
    segments = [StyledSegment("nouveau", italic=True)]
    docx_io.apply_styled_edit(p, "ancien", "nouveau", None, segments)

    assert p.text == "nouveau"
    assert p.runs[0].italic is True
