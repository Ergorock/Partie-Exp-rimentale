"""Tests des helpers partagés RMN (FEAT-002)."""

from core.rules import nmr_common as nc


# --- Exposants / indices Unicode ---

def test_to_superscript_digits():
    assert nc.to_superscript("1") == "¹"
    assert nc.to_superscript("13") == "¹³"
    assert nc.to_superscript("19") == "¹⁹"


def test_subscript_formula_only_after_letters():
    assert nc.subscript_formula("CDCl3") == "CDCl₃"
    assert nc.subscript_formula("CH2") == "CH₂"
    # Un nombre isolé (déplacement/intégration) n'est pas converti.
    assert nc.subscript_formula("298") == "298"
    assert nc.subscript_formula("2.34") == "2.34"


def test_superscript_label_keeps_word_and_element():
    assert nc.superscript_label("1H NMR") == "¹H NMR"
    assert nc.superscript_label("13C RMN") == "¹³C RMN"
    assert nc.superscript_label("19F{1H} NMR") == "¹⁹F{¹H} NMR"


# --- Normalisation des espaces ---

def test_normalize_spaces_replaces_nbsp():
    assert nc.normalize_spaces("298\xa0K") == "298 K"


# --- Délimitation du segment de section ---

PARA = (
    "1H NMR (400.18 MHz, DMF-d7, 298) δ 9.18 (dd, 2H) "
    "13C NMR (100.63 MHz, DMF-d7, 298 K) δ 149.4 (2C) "
    "19F{1H} NMR (376.55 MHz, DMF-d7, 298 K) δ -20.9 (3F)"
)


def test_section_span_isolates_first_section():
    start, end = nc.section_span(PARA, 0)
    assert start == 0
    segment = PARA[start:end]
    assert segment.startswith("1H NMR")
    assert "13C" not in segment


def test_section_span_from_13c_offset():
    offset = PARA.index("13C")
    start, end = nc.section_span(PARA, offset)
    segment = PARA[start:end]
    assert segment.startswith("13C NMR")
    assert "19F" not in segment


def test_section_span_last_section_runs_to_end():
    offset = PARA.index("19F")
    start, end = nc.section_span(PARA, offset)
    assert end == len(PARA)


# --- Parenthèse à 3 éléments ---

def test_normalize_parenthesis_full():
    res = nc.normalize_parenthesis("400.18MHz, CDCl3, 298")
    assert res.text == "400.18 MHz, CDCl₃, 298 K"


def test_normalize_parenthesis_missing_temperature_placeholder():
    res = nc.normalize_parenthesis("400 MHz, CDCl3")
    assert "[??? K]" in res.text
    assert any(kind == "placeholder" for kind, _ in res.actions)


def test_normalize_parenthesis_incomplete_is_flagged():
    res = nc.normalize_parenthesis("400 MHz")
    assert any(kind == "flagged" for kind, _ in res.actions)


# --- Delta ---

def test_split_delta_body_handles_variant_and_ppm():
    # ẟ (U+1E9F) suivi de '(ppm) ='
    body = nc.split_delta_body(": ẟ (ppm) = 9.18 (dd, 2H), 8.90 (m, 2H)")
    assert body == "9.18 (dd, 2H), 8.90 (m, 2H)"


def test_split_delta_body_standard_delta():
    body = nc.split_delta_body(" δ 7.5 (s, 1H)")
    assert body == "7.5 (s, 1H)"


def test_split_delta_body_none_when_absent():
    assert nc.split_delta_body("pas de delta ici") is None


# --- Parsing / tri / formatage ---

def test_parse_signals_basic():
    signals, all_parsable = nc.parse_signals("7.98 (d, J = 8.2 Hz, 2H, Ar-H), 2.34 (s, 3H)")
    assert all_parsable is True
    assert len(signals) == 2
    assert signals[0].multiplicity == "d"
    assert signals[0].j == "8.2"
    assert signals[0].integration == "2H"
    assert signals[0].attribution == "Ar-H"


def test_parse_signals_range_shift():
    signals, all_parsable = nc.parse_signals("7.31-7.24 (m, 2H)")
    assert all_parsable is True
    assert "–" in signals[0].shift
    assert signals[0].shift_high == 7.31


def test_parse_signals_bs_normalized():
    signals, _ = nc.parse_signals("8.35 (bs, 2H)")
    assert signals[0].multiplicity == "br s"


def test_parse_signals_unparsable_sets_flag():
    signals, all_parsable = nc.parse_signals("bizarre, 7.5 (m, 1H)")
    assert all_parsable is False


def test_sort_signals_descending_when_parsable():
    signals, ap = nc.parse_signals("2.3 (s, 3H), 7.5 (m, 1H), 4.1 (q, 2H)")
    ordered = nc.sort_signals(signals, ap)
    shifts = [s.shift for s in ordered]
    assert shifts == ["7.5", "4.1", "2.3"]


def test_sort_signals_no_reorder_when_not_parsable():
    signals, ap = nc.parse_signals("2.3 (s, 3H), bizarre, 7.5 (m, 1H)")
    ordered = nc.sort_signals(signals, ap)
    # Ordre d'entrée conservé.
    assert ordered[0].shift == "2.3"
    assert ordered[-1].shift == "7.5"


def test_format_signal_1h():
    signals, _ = nc.parse_signals("7.98 (d, J = 8.2 Hz, 2H, Ar-H)")
    assert nc.format_signal_1h(signals[0]) == "7.98 (d, J = 8.2 Hz, 2\xa0H; Ar-H)"


def test_format_signal_13c_with_attribution():
    signals, _ = nc.parse_signals("166.4 (C=O)")
    assert nc.format_signal_13c(signals[0]) == "166.4 (C=O)"


def test_format_signal_13c_keeps_j_when_coupling():
    signals, _ = nc.parse_signals("120.5 (q, J = 32.0 Hz)")
    out = nc.format_signal_13c(signals[0])
    assert "J = 32.0 Hz" in out
