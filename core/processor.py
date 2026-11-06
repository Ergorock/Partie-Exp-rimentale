"""Processor : applique les règles à un document et produit un rapport."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import List

from core import docx_io
from core.rules.base import Action, ActionKind
from core.rules.registry import RuleRegistry


# Libellés des types d'action, partagés par le rapport et les commentaires Word.
KIND_LABELS = {
    ActionKind.CORRECTED: "CORRIGÉ",
    ActionKind.PLACEHOLDER: "MARQUEUR",
    ActionKind.FLAGGED: "À VÉRIFIER",
    ActionKind.UNCHANGED: "CONFORME",
}

# Types d'action qui demandent une intervention humaine : reportés en
# commentaire Word dans le fichier de sortie.
_ANNOTATED_KINDS = (ActionKind.FLAGGED, ActionKind.PLACEHOLDER)

#: Auteur des commentaires Word ajoutés par l'outil (sert aussi à les
#: reconnaître pour ne pas les dupliquer lors d'un nouveau traitement).
COMMENT_AUTHOR = "Standardisation RMN"
COMMENT_INITIALS = "SR"


@dataclass
class ParagraphReport:
    """Rapport des actions réalisées sur un paragraphe."""

    index: int
    original_text: str
    new_text: str
    actions: List[Action] = field(default_factory=list)
    #: Emplacement lisible hors corps du texte (``'Tableau 1, ligne 2, …'``,
    #: ``'En-tête (section 1), …'``). Vide pour un paragraphe du corps.
    location: str = ""

    @property
    def label(self) -> str:
        """Libellé affiché dans le rapport."""
        return self.location or f"Paragraphe {self.index + 1}"

    @property
    def changed(self) -> bool:
        return self.original_text != self.new_text


@dataclass
class ProcessingReport:
    """Rapport global du traitement d'un document."""

    paragraphs: List[ParagraphReport] = field(default_factory=list)
    #: Nombre de commentaires Word ajoutés dans le document de sortie.
    comment_count: int = 0

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
        for pr in self.paragraphs:
            lines.append(f"{pr.label} :")
            for action in pr.actions:
                label = KIND_LABELS.get(action.kind, action.kind.value)
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
        if self.comment_count:
            header += (
                f"{self.comment_count} commentaire(s) Word ajouté(s) sur les "
                "points à vérifier.\n"
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


def comment_lines(actions: List[Action]) -> List[str]:
    """Lignes du commentaire Word d'un paragraphe : ses actions à vérifier."""
    lines = []
    for action in actions:
        if action.kind in _ANNOTATED_KINDS:
            prefix = f"[{action.rule_name}] " if action.rule_name else ""
            lines.append(f"{KIND_LABELS[action.kind]} : {prefix}{action.message}")
    return lines


def process_document(
    document, registry: RuleRegistry, annotate: bool = False
) -> ProcessingReport:
    """Applique les règles à un document python-docx et réécrit les paragraphes.

    Modifie le document en place (le texte corrigé est écrit dans les
    paragraphes concernés) et retourne le rapport des actions. Tous les
    paragraphes sont traités : corps, tableaux (imbriqués compris), en-têtes
    et pieds de page (voir ``docx_io.iter_paragraphs``). ``index`` reste la
    position dans le corps pour les paragraphes du corps.

    Avec ``annotate``, chaque paragraphe du corps qui porte une action à
    vérifier (FLAGGED / PLACEHOLDER) reçoit un commentaire Word listant ces
    actions (voir ``docx_io.add_paragraph_comment`` pour les cas ignorés).
    """
    report = ProcessingReport()
    for index, (location, paragraph) in enumerate(docx_io.iter_paragraphs(document)):
        text = paragraph.text
        rules = registry.rules_for(text)
        if not rules:
            continue
        current = text
        actions: List[Action] = []
        # Chaque règle écrit son édition IMMÉDIATEMENT dans le paragraphe : la
        # règle suivante reçoit ainsi un texte identique à celui du document,
        # et son ``replaced_text`` y est retrouvable. Règles stylisées et non
        # stylisées peuvent donc se mélanger sans perte.
        for rule in rules:
            result = rule.apply(current)
            actions.extend(result.actions)
            if result.is_styled:
                ok = docx_io.apply_styled_edit(
                    paragraph,
                    current,
                    result.new_text,
                    result.replaced_text,
                    result.segments,
                )
            else:
                ok = docx_io.apply_text_edit(paragraph, current, result.new_text)
            if not ok:
                actions.append(
                    Action(
                        ActionKind.FLAGGED,
                        "Structure Word non prise en charge (lien hypertexte, "
                        "champ…) : paragraphe laissé inchangé, correction à "
                        "faire à la main.",
                        rule.name,
                    )
                )
                break
            current = result.new_text

        report.paragraphs.append(
            ParagraphReport(
                index=index,
                original_text=text,
                new_text=paragraph.text,
                actions=actions,
                location=location,
            )
        )
        if annotate and docx_io.add_paragraph_comment(
            document, paragraph, comment_lines(actions), COMMENT_AUTHOR, COMMENT_INITIALS
        ):
            report.comment_count += 1
    return report


def available_rules() -> List:
    """Retourne une instance de chaque règle disponible dans l'application.

    Catalogue central des règles. Pour exposer une nouvelle règle (dans le CLI
    comme dans l'interface), il suffit de l'importer et de l'ajouter à cette
    liste : elle apparaîtra automatiquement dans l'UI de gestion des règles.
    """
    from core.rules.nmr_1h import OneHNmrRule
    from core.rules.nmr_13c import ThirteenCNmrRule

    return [OneHNmrRule(), ThirteenCNmrRule()]


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


def same_file(path_a: str, path_b: str) -> bool:
    """Vrai si les deux chemins désignent le même fichier (casse Windows, ``.``…)."""
    try:
        if os.path.exists(path_a) and os.path.exists(path_b):
            return os.path.samefile(path_a, path_b)
    except OSError:
        pass
    norm = lambda p: os.path.normcase(os.path.abspath(p))  # noqa: E731
    return norm(path_a) == norm(path_b)


def standardize_file(
    input_path: str,
    output_path: str,
    enabled_names: "set[str] | None" = None,
    annotate: bool = True,
) -> ProcessingReport:
    """Charge un .docx, applique les règles sélectionnées, sauvegarde le résultat.

    Args:
        input_path: chemin du .docx d'entrée.
        output_path: chemin du .docx de sortie à écrire.
        enabled_names: noms des règles à appliquer (toutes si ``None``).
        annotate: ajoute un commentaire Word sur chaque paragraphe à vérifier.

    Returns:
        Le rapport des actions réalisées.

    Raises:
        ValueError: si ``output_path`` désigne le fichier d'entrée (on ne
            l'écrase jamais : il reste la référence en cas d'erreur).
    """
    if same_file(input_path, output_path):
        raise ValueError(
            "Le fichier de sortie est le fichier d'entrée : choisissez un autre "
            "nom pour ne pas écraser l'original."
        )
    document = docx_io.load(input_path)
    registry = build_registry(enabled_names)
    report = process_document(document, registry, annotate=annotate)
    docx_io.save(document, output_path)
    return report
