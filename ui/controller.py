"""Logique applicative de l'UI, indépendante de toute bibliothèque graphique.

Le contrôleur orchestre le traitement et retourne des données simples
(dataclasses, dictionnaires JSON-compatibles) que l'interface se contente
d'afficher. Il est entièrement testable sans fenêtre.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from core.highlights import compute_spans
from core.evaluation import CONFORM, CORRECTED, TO_REVIEW, EvaluationReport, evaluate_file
from core.processor import ProcessingReport, available_rules, same_file, standardize_file
from core.rules.base import ActionKind

# Libellés des types d'action pour l'interface (casse de phrase).
_KIND_UI_LABELS = {
    ActionKind.CORRECTED: "Corrigé",
    ActionKind.FLAGGED: "À vérifier",
    ActionKind.PLACEHOLDER: "Marqueur",
    ActionKind.UNCHANGED: "Conforme",
}


def report_to_dict(report: ProcessingReport) -> dict:
    """Convertit un rapport en dictionnaire JSON-compatible pour l'interface.

    ``counts`` compte des PARAGRAPHES (pas des actions) : modifiés
    (``corrected``), portant au moins un signalement (``flagged``) ou un
    marqueur inséré (``placeholder``). ``needs_review`` marque les paragraphes
    qui demandent une intervention humaine.
    """
    paragraphs = []
    counts = {"corrected": 0, "flagged": 0, "placeholder": 0}
    for pr in report.paragraphs:
        kinds = {a.kind for a in pr.actions}
        if pr.changed:
            counts["corrected"] += 1
        if ActionKind.FLAGGED in kinds:
            counts["flagged"] += 1
        if ActionKind.PLACEHOLDER in kinds:
            counts["placeholder"] += 1
        paragraphs.append(
            {
                "label": pr.label,
                "before": pr.original_text,
                "after": pr.new_text,
                "changed": pr.changed,
                # Surlignage dans le texte final (calculé dans core, affiché par l'UI).
                "spans": compute_spans(pr.original_text, pr.new_text, pr.actions, pr.changed),
                "needs_review": bool(kinds & {ActionKind.FLAGGED, ActionKind.PLACEHOLDER}),
                "actions": [
                    {
                        "kind": a.kind.value,
                        "label": _KIND_UI_LABELS.get(a.kind, a.kind.value),
                        "rule": a.rule_name,
                        "message": a.message,
                    }
                    for a in pr.actions
                ],
            }
        )
    return {
        "paragraphs": paragraphs,
        "counts": counts,
        "comments": report.comment_count,
        "summary": report.summary(),
    }


@dataclass
class RuleInfo:
    """Information sur une règle, pour l'affichage dans l'interface."""

    name: str
    description: str


@dataclass
class StandardizeOutcome:
    """Résultat d'une demande de standardisation depuis l'UI."""

    success: bool
    message: str
    output_path: str = ""
    report: ProcessingReport | None = None


def list_rules() -> List[RuleInfo]:
    """Liste les règles disponibles (nom + description) pour l'interface."""
    return [RuleInfo(r.name, getattr(r, "description", "")) for r in available_rules()]


def suggest_output_path(input_path: str) -> str:
    """Propose un chemin de sortie à partir du chemin d'entrée."""
    base, ext = os.path.splitext(input_path)
    return f"{base}_standardise{ext or '.docx'}"


def output_path_for_new_input(
    previous_input: str, current_output: str, new_input: str
) -> str:
    """Chemin de sortie à afficher quand l'utilisateur choisit un fichier d'entrée.

    Une sortie choisie pour un AUTRE fichier d'entrée n'a plus de sens : la
    garder ferait écrire le résultat du nouveau fichier par-dessus celui du
    précédent. On propose donc la sortie suggérée pour le nouveau fichier, sauf
    dans deux cas où le choix de l'utilisateur est conservé :

    - la sortie a été choisie avant tout fichier d'entrée ;
    - le même fichier d'entrée est rechargé.
    """
    if current_output and (not previous_input or previous_input == new_input):
        return current_output
    return suggest_output_path(new_input)


def run_standardization(
    input_path: str,
    output_path: str,
    enabled_names: "set[str] | None" = None,
    annotate: bool = True,
) -> StandardizeOutcome:
    """Exécute la standardisation et retourne un résultat pour l'affichage.

    Args:
        input_path: chemin du .docx d'entrée.
        output_path: chemin du .docx de sortie.
        enabled_names: règles à appliquer (toutes si ``None``). Un ensemble
            vide signifie « aucune règle sélectionnée » et est rejeté.
        annotate: ajoute un commentaire Word sur chaque paragraphe à vérifier.

    Capture les erreurs pour que l'UI puisse les présenter proprement.
    """
    if not input_path:
        return StandardizeOutcome(False, "Aucun fichier d'entrée sélectionné.")
    if not os.path.exists(input_path):
        return StandardizeOutcome(False, f"Fichier introuvable : {input_path}")
    if not input_path.lower().endswith(".docx"):
        return StandardizeOutcome(False, "Le fichier d'entrée doit être un .docx.")
    if not output_path:
        return StandardizeOutcome(False, "Aucun fichier de sortie spécifié.")
    if same_file(input_path, output_path):
        return StandardizeOutcome(
            False,
            "Le fichier de sortie est le fichier d'entrée : choisissez un autre "
            "nom pour ne pas écraser l'original.",
        )
    if enabled_names is not None and len(enabled_names) == 0:
        return StandardizeOutcome(False, "Aucune règle sélectionnée.")

    try:
        report = standardize_file(input_path, output_path, enabled_names, annotate=annotate)
    except Exception as exc:  # pragma: no cover - dépend de l'environnement
        return StandardizeOutcome(False, f"Erreur pendant le traitement : {exc}")

    message = (
        f"Terminé. {report.changed_count} paragraphe(s) modifié(s), "
        f"{report.action_count} action(s).\nFichier écrit : {output_path}"
    )
    return StandardizeOutcome(True, message, output_path, report)


# --------------------------------------------------------------------------- #
# Mode évaluation
# --------------------------------------------------------------------------- #

@dataclass
class EvaluateOutcome:
    """Résultat d'une demande d'évaluation depuis l'UI."""

    success: bool
    message: str
    report: EvaluationReport | None = None


def evaluation_to_dict(report: EvaluationReport) -> dict:
    """Convertit une évaluation en dictionnaire JSON-compatible pour l'interface."""
    return {
        "score": report.score,
        "grade": report.grade,
        "total": report.total,
        "ok": report.ok_count,
        "counts": {s: report.count(s) for s in (CONFORM, CORRECTED, TO_REVIEW)},
        "thresholds": dict(report.thresholds),
        "by_rule": [
            {"rule": r.rule_name, "ok": r.ok_count, "total": r.total, "score": r.score}
            for r in report.by_rule()
        ],
        "issues": [
            {"rule": i.rule_name, "kind": i.kind, "description": i.description, "count": i.count}
            for i in report.issues()
        ],
        "items": [
            {
                "label": item.label,
                "rule": item.rule_name,
                "status": item.status,
                "text": item.text,
                "actions": [
                    {
                        "kind": a.kind.value,
                        "label": _KIND_UI_LABELS.get(a.kind, a.kind.value),
                        "message": a.message,
                    }
                    for a in item.actions
                    if a.kind != ActionKind.UNCHANGED
                ],
            }
            for item in report.items
        ],
        "summary": report.summary(),
    }


def run_evaluation(input_path: str, enabled_names: "set[str] | None" = None) -> EvaluateOutcome:
    """Évalue le document (sans l'écrire) et retourne un résultat pour l'affichage."""
    if not input_path:
        return EvaluateOutcome(False, "Aucun fichier d'entrée sélectionné.")
    if not os.path.exists(input_path):
        return EvaluateOutcome(False, f"Fichier introuvable : {input_path}")
    if not input_path.lower().endswith(".docx"):
        return EvaluateOutcome(False, "Le fichier d'entrée doit être un .docx.")
    if enabled_names is not None and len(enabled_names) == 0:
        return EvaluateOutcome(False, "Aucune règle sélectionnée.")
    try:
        report = evaluate_file(input_path, enabled_names)
    except Exception as exc:  # pragma: no cover - dépend de l'environnement
        return EvaluateOutcome(False, f"Erreur pendant l'évaluation : {exc}")
    return EvaluateOutcome(True, "Évaluation terminée.", report)
