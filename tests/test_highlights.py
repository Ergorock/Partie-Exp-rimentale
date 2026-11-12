"""Surlignage dans le texte : empans calculés dans core, exposés par le contrôleur."""

from core import config as cfg
from core.config import RmnConfig
from core.highlights import compute_spans
from core.processor import build_registry, process_texts
from core.rules.base import Action, ActionKind
from ui.controller import report_to_dict

NB = "\u00a0"


def _spans(texts):
    report = report_to_dict(process_texts(texts, build_registry()))
    return [
        (p["after"], [(p["after"][s["start"]:s["end"]], s["kind"]) for s in p["spans"]])
        for p in report["paragraphs"]
    ]


def _kinds(spans, text):
    return [kind for piece, kind in spans if text in piece]


def test_corrected_text_is_highlighted_green():
    after, spans = _spans(["Stirred 5 mL for 2 h."])[0]
    assert after == f"Stirred 5{NB}mL for 2{NB}h."
    assert spans == [(NB, "corrected"), (NB, "corrected")]


def test_unchanged_text_has_no_span():
    assert _spans(["Texte sans analyse."]) == []
    report = report_to_dict(process_texts(["Rf = 0.38 (SiO₂; heptane/EtOAc 4:1)"], build_registry()))
    assert report["paragraphs"][0]["spans"] == []


def test_placeholder_marker_is_highlighted_purple():
    _, spans = _spans(["1H NMR (400 MHz, CDCl3) δ 7.26 (s, 1H)"])[0]
    assert ("[??? K]", "placeholder") in spans


def test_custom_placeholder_is_highlighted():
    cfg.set_config(RmnConfig(temperature_placeholder="[TEMP ?]"))
    _, spans = _spans(["1H NMR (400 MHz, CDCl3) δ 7.26 (s, 1H)"])[0]
    assert ("[TEMP ?]", "placeholder") in spans


def test_flagged_value_is_highlighted_amber():
    _, spans = _spans(["gave 25 (843 mg, 77.5 %) as needles"])[0]
    assert ("77.5 %", "flagged") in [(p.replace(NB, " "), k) for p, k in spans]


def test_only_the_bad_signals_are_flagged():
    _, spans = _spans(["1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H), 1.2 (t, 3H)"])[0]
    flagged = [p for p, k in spans if k == "flagged"]
    assert flagged == [f"1.2 (t, 3{NB}H)"]


def test_hrms_found_mass_is_flagged():
    _, spans = _spans(["HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0950."])[0]
    assert ("165.0950", "flagged") in spans


def test_rf_value_and_entry_are_flagged():
    _, spans = _spans(["Rf = 0.4 (hexane/EtOAc 4:1)"])[0]
    assert all(k == "flagged" for _, k in spans if "0.4" in _)
    assert any("0.4" in piece for piece, k in spans if k == "flagged")


def test_melting_point_bad_number_and_range_are_flagged():
    _, spans = _spans(["mp 130-128 °C"])[0]
    assert any(k == "flagged" and "130" in p and "128" in p for p, k in spans)
    _, spans = _spans(["mp 185.5 °C"])[0]
    assert ("185.5", "flagged") in spans


def test_wrong_analysis_order_highlights_the_late_label():
    _, spans = _spans(
        ["13C NMR (101 MHz, CDCl3, 298 K) δ 77.0. 1H NMR (400 MHz, CDCl3, 298 K) δ 7.26 (s, 1H)."]
    )[0]
    assert any(k == "flagged" and "H NMR" in p for p, k in spans)


def test_flagged_beats_corrected_and_spans_never_overlap():
    after, spans = _spans(["1H NMR (400 MHz, CDCl3, 298 K) δ 1.2 (t, 3H)"])[0]
    start = 0
    for span in report_to_dict(process_texts(
            ["1H NMR (400 MHz, CDCl3, 298 K) δ 1.2 (t, 3H)"], build_registry()))["paragraphs"][0]["spans"]:
        assert span["start"] >= start and span["end"] > span["start"]
        start = span["end"]
    assert ("1.2 (t, 3" + NB + "H)", "flagged") in spans


def test_missing_excerpt_is_ignored():
    action = Action(ActionKind.FLAGGED, "x : y", "R", ("introuvable", "a"))
    assert compute_spans("texte", "texte", [action]) == []


def test_non_breaking_space_in_excerpt_matches_plain_space():
    action = Action(ActionKind.FLAGGED, "x : y", "R", ("77.5 %",))
    spans = compute_spans("a 77.5\u00a0% b", "a 77.5\u00a0% b", [action])
    assert spans == [{"start": 2, "end": 8, "kind": "flagged"}]


def test_spans_are_json_compatible():
    import json

    report = report_to_dict(process_texts(["Stirred 5 mL"], build_registry()))
    json.dumps(report)
    assert report["paragraphs"][0]["spans"][0].keys() == {"start", "end", "kind"}
