"""Règle « Unités » : espace insécable nombre-unité, forme seulement."""

import pytest
from docx import Document

from core.processor import available_rules, build_registry, process_texts, standardize_file
from core.rules.base import ActionKind
from core.rules.units import UnitsRule

NB = "\u00a0"
RULE = UnitsRule()


def _flags(result):
    return [a.message for a in result.actions if a.kind == ActionKind.FLAGGED]


@pytest.mark.parametrize("written, expected", [
    ("220 mg", f"220{NB}mg"),
    ("220mg", f"220{NB}mg"),
    ("0.9 mmol", f"0.9{NB}mmol"),
    ("6,3 mL", f"6,3{NB}mL"),
    ("300 µL", f"300{NB}µL"),
    ("12 min", f"12{NB}min"),
    ("2 h", f"2{NB}h"),
    ("5 g", f"5{NB}g"),
    ("1 equiv.", f"1{NB}equiv."),
    ("77 %", f"77{NB}%"),
    ("77%", f"77{NB}%"),
    ("25 °C", f"25{NB}°C"),
    ("25°C", f"25{NB}°C"),
    ("25 ºC", f"25{NB}°C"),
    ("25 ˚C", f"25{NB}°C"),
    ("10 mol %", f"10{NB}mol%"),
    ("10 mol%", f"10{NB}mol%"),
    ("5 wt %", f"5{NB}wt%"),
    ("0.5 M", f"0.5{NB}M"),
])
def test_number_and_unit(written, expected):
    result = RULE.apply(f"Stirred {written} here.")
    assert result.new_text == f"Stirred {expected} here."


def test_full_procedure_sentence():
    text = ("A solution of I2 (220 mg, 0.9 mmol, 10 mol %) in toluene (300mL) "
            "was cooled to 0°C for 12 min.")
    assert RULE.apply(text).new_text == (
        f"A solution of I2 (220{NB}mg, 0.9{NB}mmol, 10{NB}mol%) in toluene "
        f"(300{NB}mL) was cooled to 0{NB}°C for 12{NB}min."
    )


def test_output_is_idempotent_and_values_unchanged():
    once = RULE.apply("Add 220 mg and 6.3 mL at 25°C (77 %).").new_text
    again = RULE.apply(once)
    assert again.new_text == once
    assert [a.kind for a in again.actions] == [ActionKind.UNCHANGED]
    digits = lambda s: [c for c in s if c.isdigit()]  # noqa: E731
    assert digits(once) == digits("Add 220 mg and 6.3 mL at 25°C (77 %).")


def test_no_unit_is_added_and_words_are_untouched():
    for text in ("5 minutes later", "10-mL flask", "compound 5g and 7h", "300 grams",
                 "Table 2 shows 3 entries", "step 5 (see below)"):
        assert RULE.apply(text).new_text == text, text


def test_single_letter_units_need_an_existing_space():
    assert RULE.apply("compound 5g").new_text == "compound 5g"
    assert RULE.apply("5 g").new_text == f"5{NB}g"


def test_narrow_no_break_space_is_kept():
    text = "5\u202fmg"
    assert RULE.apply(text).new_text == text


def test_analysis_text_is_left_to_the_analysis_rules():
    text = "Stirred 5 mL. 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H), 2 mL"
    result = RULE.apply(text)
    assert result.new_text == f"Stirred 5{NB}mL. 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H), 2 mL"
    assert not RULE.applies("1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)")
    assert not RULE.applies("Rf = 0.38 (SiO2; heptane/EtOAc 4:1, 20 %)")
    assert not RULE.applies("mp 120 °C")


def test_yield_with_decimal_is_flagged_value_kept():
    result = RULE.apply("gave 25 (843 mg, 77.5 %) as needles")
    assert "77.5" in result.new_text
    assert [m for m in _flags(result) if m.startswith("Rendement avec décimale : ")]
    assert not _flags(RULE.apply("gave 25 (843 mg, 77 %) as needles"))


def test_flag_survives_on_conform_text():
    result = RULE.apply(f"gave 25 (843{NB}mg, 77.5{NB}%)")
    assert _flags(result) and ActionKind.UNCHANGED not in [a.kind for a in result.actions]


def test_message_fixed_part():
    message = [a.message for a in RULE.apply("Add 5 mL").actions][0]
    assert message.split(" : ")[0] == "Espace insécable entre nombre et unité"


def test_prose_without_quantity_is_ignored():
    assert not RULE.applies("Le mélange a été agité toute la nuit.")


def test_chain_does_not_touch_nmr_frequency_or_loop():
    text = f"Stirred 5 mL. 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)"
    final = process_texts([text], build_registry()).paragraphs[0].new_text
    assert final == (
        f"Stirred 5{NB}mL. ¹H NMR (400 MHz, CDCl₃, 298 K) δ (ppm) = 7.26 (s, 1{NB}H)"
    )
    # Retraiter la sortie ne change plus rien.
    assert process_texts([final], build_registry()).paragraphs[0].new_text == final


def test_rule_is_in_the_catalog():
    assert "Unités" in [r.name for r in available_rules()]


def test_docx_text_edit_keeps_run_formatting(tmp_path):
    src, out = tmp_path / "in.docx", tmp_path / "out.docx"
    doc = Document()
    p = doc.add_paragraph()
    p.add_run("Stirred ")
    p.add_run("5 mL").italic = True
    p.add_run(" for 2 h.")
    doc.save(src)
    standardize_file(str(src), str(out))
    paragraph = Document(out).paragraphs[0]
    assert paragraph.text == f"Stirred 5{NB}mL for 2{NB}h."
    assert any(r.italic for r in paragraph.runs)
