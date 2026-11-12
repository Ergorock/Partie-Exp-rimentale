"""Mode évaluation : pourcentage de sections conformes, note et écarts."""

import os

import pytest
from docx import Document

import cli
from core import config as cfg
from core.config import RmnConfig
from core.evaluation import evaluate_file, evaluate_texts, grade_for
from core.processor import build_registry
from core.rules.base import ActionKind
from core.rules.nmr_1h import OneHNmrRule

CONFORM_1H = "¹H NMR (400 MHz, CDCl₃, 298 K) δ (ppm) = 7.26 (s, 1\xa0H)"
RAW_1H = "1H NMR (400MHz, CDCl3, 298) δ 7.26 (s, 1H)"
CONFORM_HRMS = "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0910; Found 165.0912."
WRONG_HRMS = "HRMS (ESI) m/z: [M + H]⁺ Calcd for C₁₀H₁₃O₂ 165.0950; Found 165.0952."


def _evaluate(texts):
    return evaluate_texts(texts, build_registry())


# --- Prérequis : une section déjà conforme est reconnue ---------------------------

def test_already_styled_section_is_recognized_as_conform():
    rule = OneHNmrRule()
    assert rule.applies(CONFORM_1H)
    result = rule.apply(CONFORM_1H)
    assert result.new_text == CONFORM_1H
    assert [a.kind for a in result.actions] == [ActionKind.UNCHANGED]


def test_already_styled_decoupled_label_is_recognized():
    text = "¹⁹F{¹H} NMR (376 MHz, CDCl₃, 298 K) δ (ppm) = −63.2 (s, 3\xa0F)"
    final = _evaluate([text]).items
    assert [(i.rule_name, i.status) for i in final] == [("19F NMR", "conforme")]


def test_unchanged_section_keeps_its_flags():
    text = "¹H NMR (400 MHz, CDCl₃, [??? K]) δ (ppm) = 7.26 (s, 1\xa0H)"
    result = OneHNmrRule().apply(text)
    assert result.new_text == text
    kinds = [a.kind for a in result.actions]
    assert ActionKind.PLACEHOLDER in kinds and ActionKind.UNCHANGED not in kinds


# --- Score et statut ----------------------------------------------------------------

def test_each_section_is_one_item():
    report = _evaluate([f"{CONFORM_1H} {CONFORM_HRMS}", RAW_1H])
    assert [(i.rule_name, i.status) for i in report.items] == [
        ("1H NMR", "conforme"),
        ("HRMS", "conforme"),
        ("1H NMR", "corrigé"),
    ]
    assert report.total == 3
    assert report.ok_count == 2
    assert report.score == pytest.approx(200 / 3)


def test_flagged_item_is_to_review():
    report = _evaluate([WRONG_HRMS])
    assert report.items[0].status == "à vérifier"
    assert report.score == 0


def test_all_conform_is_perfect():
    report = _evaluate([CONFORM_1H, CONFORM_HRMS])
    assert report.score == 100
    assert report.grade == "Parfait"


def test_no_section_is_not_evaluable():
    report = _evaluate(["Texte sans analyse."])
    assert report.total == 0
    assert report.score is None
    assert report.grade == "Non évaluable"


# --- Notes et seuils ------------------------------------------------------------------

@pytest.mark.parametrize(
    "score, grade",
    [(100, "Parfait"), (95, "Très bon"), (90, "Très bon"), (80, "Bon"),
     (60, "Correct"), (49.9, "Mauvais"), (0, "Mauvais")],
)
def test_default_grades(score, grade):
    assert grade_for(score, RmnConfig().evaluation_thresholds) == grade


def test_thresholds_are_configurable():
    cfg.set_config(RmnConfig(evaluation_thresholds={
        "parfait": 100.0, "tres_bon": 60.0, "bon": 40.0, "correct": 20.0}))
    report = _evaluate([CONFORM_1H, CONFORM_1H, RAW_1H])  # 66,7 %
    assert report.grade == "Très bon"


def test_thresholds_config_roundtrip_and_validation():
    good = {"parfait": 98.0, "tres_bon": 85.0, "bon": 70.0, "correct": 40.0}
    data = cfg.config_to_dict(RmnConfig(evaluation_thresholds=good))
    assert cfg.config_from_dict(data).evaluation_thresholds == good
    default = RmnConfig().evaluation_thresholds
    for bad in (
        {"parfait": 100, "tres_bon": 95, "bon": 97, "correct": 50},  # désordre
        {"parfait": 120, "tres_bon": 90, "bon": 75, "correct": 50},  # > 100
        {"parfait": 100, "tres_bon": 90},                             # incomplet
        "90",
        {"parfait": True, "tres_bon": 90, "bon": 75, "correct": 50},
    ):
        assert cfg.config_from_dict({"evaluation_thresholds": bad}).evaluation_thresholds == default


# --- Détail des écarts ---------------------------------------------------------------

def test_issues_are_grouped_by_rule_and_type():
    report = _evaluate([RAW_1H, RAW_1H.replace("CDCl3", "C6D6")])
    issues = {(i.rule_name, i.kind, i.description): i.count for i in report.issues()}
    assert issues[("1H NMR", "corrected", "Fréquence normalisée")] == 2
    assert issues[("1H NMR", "corrected", "Solvant en indices Unicode")] == 2


def test_by_rule_breakdown():
    report = _evaluate([CONFORM_1H, RAW_1H, CONFORM_HRMS])
    by_rule = {r.rule_name: (r.ok_count, r.total) for r in report.by_rule()}
    assert by_rule == {"1H NMR": (1, 2), "HRMS": (1, 1)}


def test_summary_text():
    summary = _evaluate([CONFORM_1H, RAW_1H]).summary()
    assert "50 %" in summary and "Correct" in summary
    assert "Fréquence normalisée" in summary


# --- Fichier et CLI ------------------------------------------------------------------

def _make_docx(path, texts):
    doc = Document()
    for text in texts:
        doc.add_paragraph(text)
    doc.save(path)
    return path


def test_evaluate_file_does_not_modify_document(tmp_path):
    src = _make_docx(os.path.join(tmp_path, "in.docx"), [RAW_1H, CONFORM_HRMS])
    before = os.path.getmtime(src)
    report = evaluate_file(src)
    assert report.total == 2 and report.ok_count == 1
    assert os.path.getmtime(src) == before
    assert [p.text for p in Document(src).paragraphs] == [RAW_1H, CONFORM_HRMS]


def test_evaluate_file_respects_enabled_rules(tmp_path):
    src = _make_docx(os.path.join(tmp_path, "in.docx"), [RAW_1H, CONFORM_HRMS])
    report = evaluate_file(src, {"HRMS"})
    assert [i.rule_name for i in report.items] == ["HRMS"]


def test_cli_evaluate_mode_writes_nothing(tmp_path, capsys):
    src = _make_docx(os.path.join(tmp_path, "in.docx"), [RAW_1H, CONFORM_HRMS])
    assert cli.main(["cli.py", "--evaluer", src]) == 0
    out = capsys.readouterr().out
    assert "50 %" in out and "Correct" in out
    assert os.listdir(tmp_path) == ["in.docx"]


# --- IR ------------------------------------------------------------------------------

CONFORM_IR = "IR (ATR): ν\u0303(cm⁻¹) = 3420, 1715, 1600"


def test_ir_conform_and_corrected_items():
    report = _evaluate([CONFORM_IR, "IR (ATR) 1715, 3420 cm-1"])
    assert [(i.rule_name, i.status) for i in report.items] == [
        ("IR", "conforme"),
        ("IR", "corrigé"),
    ]


def test_ir_decimal_band_is_to_check_and_gap_is_grouped_on_fixed_part():
    report = _evaluate(["IR (ATR) 3420, 1715.5 cm-1", "IR (ATR) 3420, 1600.5 cm-1"])
    assert [i.status for i in report.items] == ["à vérifier", "à vérifier"]
    issues = report.issues()
    assert len(issues) == 1
    assert issues[0].count == 2
