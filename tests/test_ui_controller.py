"""Tests de fumée de la couche contrôleur UI (Task 5), sans Qt."""

import os

from ui.controller import run_standardization, suggest_output_path

EXAMPLE_DOCX = os.path.join(os.path.dirname(os.path.dirname(__file__)), "partie exp.docx")


def test_suggest_output_path_adds_suffix():
    out = suggest_output_path("doc.docx")
    assert out.endswith("_standardise.docx")
    assert suggest_output_path("sans_extension").endswith("_standardise.docx")


def test_run_standardization_rejects_missing_file():
    outcome = run_standardization("n_existe_pas.docx", "sortie.docx")
    assert outcome.success is False
    assert "introuvable" in outcome.message.lower()


def test_run_standardization_rejects_non_docx():
    outcome = run_standardization("fichier.txt", "sortie.docx")
    assert outcome.success is False


def test_run_standardization_success(tmp_path):
    output = os.path.join(tmp_path, "out.docx")
    outcome = run_standardization(EXAMPLE_DOCX, output)
    assert outcome.success is True
    assert os.path.exists(output)
    assert outcome.report is not None
    assert outcome.report.action_count >= 1


# --- Gestion des règles depuis l'UI ---

from ui.controller import list_rules  # noqa: E402


def test_list_rules_exposes_name_and_description():
    rules = list_rules()
    assert rules, "Il devrait y avoir au moins une règle disponible"
    names = [r.name for r in rules]
    assert "1H NMR" in names
    one_h = next(r for r in rules if r.name == "1H NMR")
    assert one_h.description  # description non vide


def test_run_standardization_rejects_empty_rule_selection(tmp_path):
    output = os.path.join(tmp_path, "out.docx")
    outcome = run_standardization(EXAMPLE_DOCX, output, set())
    assert outcome.success is False
    assert "règle" in outcome.message.lower()


def test_run_standardization_with_disabled_rule_makes_no_change(tmp_path):
    # Aucune règle connue activée -> le 1H NMR n'est pas corrigé.
    output = os.path.join(tmp_path, "out.docx")
    outcome = run_standardization(EXAMPLE_DOCX, output, {"Règle inexistante"})
    assert outcome.success is True
    assert outcome.report is not None
    assert outcome.report.changed_count == 0


def test_run_standardization_with_1h_rule_enabled_corrects(tmp_path):
    output = os.path.join(tmp_path, "out.docx")
    outcome = run_standardization(EXAMPLE_DOCX, output, {"1H NMR"})
    assert outcome.success is True
    assert outcome.report is not None
    assert outcome.report.changed_count >= 1
