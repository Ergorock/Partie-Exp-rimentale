"""Logique applicative de l'UI, séparée de Qt pour rester testable.

Le contrôleur ne dépend pas de PySide6 : il orchestre le traitement et
retourne des données simples que la fenêtre se contente d'afficher.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import List

from core.processor import ProcessingReport, available_rules, standardize_file


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


def run_standardization(
    input_path: str,
    output_path: str,
    enabled_names: "set[str] | None" = None,
) -> StandardizeOutcome:
    """Exécute la standardisation et retourne un résultat pour l'affichage.

    Args:
        input_path: chemin du .docx d'entrée.
        output_path: chemin du .docx de sortie.
        enabled_names: règles à appliquer (toutes si ``None``). Un ensemble
            vide signifie « aucune règle sélectionnée » et est rejeté.

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
    if enabled_names is not None and len(enabled_names) == 0:
        return StandardizeOutcome(False, "Aucune règle sélectionnée.")

    try:
        report = standardize_file(input_path, output_path, enabled_names)
    except Exception as exc:  # pragma: no cover - dépend de l'environnement
        return StandardizeOutcome(False, f"Erreur pendant le traitement : {exc}")

    message = (
        f"Terminé. {report.changed_count} paragraphe(s) modifié(s), "
        f"{report.action_count} action(s).\nFichier écrit : {output_path}"
    )
    return StandardizeOutcome(True, message, output_path, report)
