"""Processor : applique les règles à un document et produit un rapport."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List

from core import docx_io
from core.rules.base import Action, ActionKind
from core.rules.registry import RuleRegistry


@dataclass
class ParagraphReport:
    """Rapport des actions réalisées sur un paragraphe."""

    index: int
    original_text: str
    new_text: str
    actions: List[Action] = field(default_factory=list)

    @property
    def changed(self) -> bool:
        return self.original_text != self.new_text


@dataclass
class ProcessingReport:
    """Rapport global du traitement d'un document."""

    paragraphs: List[ParagraphReport] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return sum(1 for p in self.paragraphs if p.changed)

    @property
    def action_count(self) -> int:
        return sum(len(p.actions) for p in self.paragraphs)

    def summary(self) -> str:
        """Retourne un résumé lisible des actions réalisées."""
        if not self.paragraphs:
            return "Aucune correction : aucun paragraphe concerné par les règles."

        lines: List[str] = []
        kind_labels = {
            ActionKind.CORRECTED: "CORRIGÉ",
            ActionKind.PLACEHOLDER: "MARQUEUR",
            ActionKind.FLAGGED: "À VÉRIFIER",
            ActionKind.UNCHANGED: "CONFORME",
        }
        for pr in self.paragraphs:
            lines.append(f"Paragraphe {pr.index + 1} :")
            for action in pr.actions:
                label = kind_labels.get(action.kind, action.kind.value)
                prefix = f"[{action.rule_name}] " if action.rule_name else ""
                lines.append(f"  - {label} : {prefix}{action.message}")
            if pr.changed:
                lines.append(f"    Avant : {pr.original_text}")
                lines.append(f"    Après : {pr.new_text}")
            lines.append("")
        header = (
            f"{self.changed_count} paragraphe(s) modifié(s), "
            f"{self.action_count} action(s) au total.\n"
        )
        return header + "\n".join(lines)


def process_texts(texts: List[str], registry: RuleRegistry) -> ProcessingReport:
    """Applique les règles du registre à une liste de textes de paragraphes.

    Utile pour tester la logique sans fichier .docx. Les règles sont appliquées
    en chaîne : le texte produit par une règle est transmis à la suivante.

    Chemin sans docx : les segments stylisés ne sont pas pris en compte ici.
    Comme une règle stylisée renseigne toujours ``new_text`` avec le texte final
    complet du paragraphe, le chaînage sur ``new_text`` reste la vérité textuelle
    même quand plusieurs règles s'appliquent (chacune reçoit le ``new_text``
    précédent).
    """
    report = ProcessingReport()
    for index, text in enumerate(texts):
        rules = registry.rules_for(text)
        if not rules:
            continue
        current = text
        actions: List[Action] = []
        for rule in rules:
            result = rule.apply(current)
            current = result.new_text
            actions.extend(result.actions)
        report.paragraphs.append(
            ParagraphReport(
                index=index,
                original_text=text,
                new_text=current,
                actions=actions,
            )
        )
    return report


def process_document(document, registry: RuleRegistry) -> ProcessingReport:
    """Applique les règles à un document python-docx et réécrit les paragraphes.

    Modifie le document en place (le texte corrigé est écrit dans les
    paragraphes concernés) et retourne le rapport des actions.
    """
    report = ProcessingReport()
    for index, paragraph in enumerate(document.paragraphs):
        text = paragraph.text
        rules = registry.rules_for(text)
        if not rules:
            continue
        current = text
        actions: List[Action] = []
        # Éditions stylisées produites par les règles (chacune cible une
        # sous-chaîne disjointe du paragraphe : voir FEAT-002). On les met de
        # côté pour les appliquer via docx_io.apply_styled_edit.
        styled_edits = []
        for rule in rules:
            result = rule.apply(current)
            current = result.new_text
            actions.extend(result.actions)
            if result.is_styled:
                styled_edits.append((result.replaced_text, result.segments))

        if styled_edits:
            # Les règles ciblent des sous-chaînes disjointes : on applique
            # chaque édition stylisée une par une en recalculant old_text =
            # paragraph.text avant chaque application (l'ordre n'introduit pas
            # de conflit). Les éventuelles règles non-stylisées ont déjà écrit
            # leur texte via new_text, reflété dans styled_edits/replaced_text.
            for replaced_text, segments in styled_edits:
                docx_io.apply_styled_edit(
                    paragraph,
                    paragraph.text,
                    current,
                    replaced_text,
                    segments,
                )
        elif current != text:
            docx_io.apply_text_edit(paragraph, text, current)

        report.paragraphs.append(
            ParagraphReport(
                index=index,
                original_text=text,
                new_text=current,
                actions=actions,
            )
        )
    return report


def available_rules() -> List:
    """Retourne une instance de chaque règle disponible dans l'application.

    Catalogue central des règles. Pour exposer une nouvelle règle (dans le CLI
    comme dans l'interface), il suffit de l'importer et de l'ajouter à cette
    liste : elle apparaîtra automatiquement dans l'UI de gestion des règles.
    """
    from core.rules.nmr_1h import OneHNmrRule

    return [OneHNmrRule()]


def build_registry(enabled_names: "set[str] | None" = None) -> RuleRegistry:
    """Construit un registre avec les règles disponibles.

    Args:
        enabled_names: ensemble des noms de règles à activer. Si ``None``,
            toutes les règles disponibles sont activées.

    Returns:
        Un ``RuleRegistry`` contenant les règles sélectionnées.
    """
    registry = RuleRegistry()
    for rule in available_rules():
        if enabled_names is None or rule.name in enabled_names:
            registry.register(rule)
    return registry


def build_default_registry() -> RuleRegistry:
    """Construit le registre avec toutes les règles disponibles (toutes activées)."""
    return build_registry(None)


def standardize_file(
    input_path: str,
    output_path: str,
    enabled_names: "set[str] | None" = None,
) -> ProcessingReport:
    """Charge un .docx, applique les règles sélectionnées, sauvegarde le résultat.

    Args:
        input_path: chemin du .docx d'entrée.
        output_path: chemin du .docx de sortie à écrire.
        enabled_names: noms des règles à appliquer (toutes si ``None``).

    Returns:
        Le rapport des actions réalisées.
    """
    document = docx_io.load(input_path)
    registry = build_registry(enabled_names)
    report = process_document(document, registry)
    docx_io.save(document, output_path)
    return report
