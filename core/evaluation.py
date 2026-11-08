"""Mode évaluation : note la conformité d'un document SANS le modifier.

Chaque application d'une règle à un paragraphe (une section RMN, une entrée
HRMS…) est un **élément évalué**, classé :

- ``conforme`` : la règle n'a rien à corriger ni à signaler ;
- ``corrigé`` : le format n'était pas respecté, mais la standardisation le
  corrige automatiquement ;
- ``à vérifier`` : un signalement (``FLAGGED``) ou un marqueur
  (``PLACEHOLDER``) demande une intervention humaine.

Le **score** est le pourcentage d'éléments conformes. La **note** en découle
d'après les seuils ``config.evaluation_thresholds`` (Parfait, Très bon, Bon,
Correct, sinon Mauvais). Les écarts sont regroupés par règle et par type
(``issues``) : le type est la partie fixe du message d'action, avant ``' : '``.

Le document n'est jamais écrit : les règles sont appliquées en chaîne sur le
texte seul, comme ``processor.process_texts``.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Tuple

from core import docx_io
from core.config import EVALUATION_GRADES, get_config
from core.processor import build_registry
from core.rules.base import Action, ActionKind
from core.rules.registry import RuleRegistry

CONFORM = "conforme"
CORRECTED = "corrigé"
TO_REVIEW = "à vérifier"

#: Libellé lisible de chaque note (clé de ``evaluation_thresholds``).
GRADE_LABELS = {
    "parfait": "Parfait",
    "tres_bon": "Très bon",
    "bon": "Bon",
    "correct": "Correct",
}
BAD_GRADE = "Mauvais"
NOT_EVALUABLE = "Non évaluable"

_REVIEW_KINDS = (ActionKind.FLAGGED, ActionKind.PLACEHOLDER)


def grade_for(score: Optional[float], thresholds: Dict[str, float]) -> str:
    """Note correspondant à un score (pourcentage), d'après les seuils."""
    if score is None:
        return NOT_EVALUABLE
    for key in EVALUATION_GRADES:
        # Petite marge pour les arrondis flottants (2/3 * 100…).
        if score + 1e-9 >= thresholds[key]:
            return GRADE_LABELS[key]
    return BAD_GRADE


def status_of(actions: Iterable[Action], changed: bool) -> str:
    """Statut d'un élément évalué d'après ses actions."""
    kinds = {a.kind for a in actions}
    if kinds & set(_REVIEW_KINDS):
        return TO_REVIEW
    if changed or ActionKind.CORRECTED in kinds:
        return CORRECTED
    return CONFORM


def issue_type(message: str) -> str:
    """Type d'écart : partie fixe du message, avant ``' : '`` (valeurs exclues)."""
    head = message.split(" : ", 1)[0].strip().rstrip(".")
    # Garde-fou si un message met une valeur dans sa partie fixe.
    return re.sub(r"'[^']*'", "…", head)


@dataclass
class EvaluationItem:
    """Une section / entrée évaluée."""

    label: str  # emplacement lisible ('Paragraphe 3', 'Tableau 1, …')
    rule_name: str
    status: str
    actions: List[Action] = field(default_factory=list)
    text: str = ""  # texte du paragraphe tel qu'il est dans le document


@dataclass
class RuleScore:
    """Score d'une règle sur le document."""

    rule_name: str
    ok_count: int
    total: int

    @property
    def score(self) -> float:
        return 100.0 * self.ok_count / self.total


@dataclass
class Issue:
    """Un type d'écart et le nombre de sections concernées."""

    rule_name: str
    kind: str  # 'corrected' | 'flagged' | 'placeholder'
    description: str
    count: int


@dataclass
class EvaluationReport:
    """Résultat de l'évaluation d'un document."""

    items: List[EvaluationItem] = field(default_factory=list)
    thresholds: Dict[str, float] = field(default_factory=dict)

    @property
    def total(self) -> int:
        return len(self.items)

    @property
    def ok_count(self) -> int:
        return sum(1 for i in self.items if i.status == CONFORM)

    def count(self, status: str) -> int:
        return sum(1 for i in self.items if i.status == status)

    @property
    def score(self) -> Optional[float]:
        """Pourcentage d'éléments conformes, ou ``None`` sans aucun élément."""
        if not self.items:
            return None
        return 100.0 * self.ok_count / self.total

    @property
    def grade(self) -> str:
        return grade_for(self.score, self.thresholds)

    def by_rule(self) -> List[RuleScore]:
        """Score par règle, dans l'ordre de première apparition."""
        totals: "OrderedDict[str, List[int]]" = OrderedDict()
        for item in self.items:
            ok_total = totals.setdefault(item.rule_name, [0, 0])
            ok_total[0] += item.status == CONFORM
            ok_total[1] += 1
        return [RuleScore(name, ok, total) for name, (ok, total) in totals.items()]

    def issues(self) -> List[Issue]:
        """Écarts regroupés par (règle, type d'action, type d'écart).

        ``count`` compte les SECTIONS concernées (un type d'écart répété dans
        une même section ne compte qu'une fois). Tri : à vérifier d'abord,
        puis par fréquence décroissante.
        """
        counts: Dict[Tuple[str, str, str], int] = {}
        for item in self.items:
            seen = set()
            for action in item.actions:
                if action.kind == ActionKind.UNCHANGED:
                    continue
                key = (item.rule_name, action.kind.value, issue_type(action.message))
                if key not in seen:
                    seen.add(key)
                    counts[key] = counts.get(key, 0) + 1
        order = {"flagged": 0, "placeholder": 1, "corrected": 2}
        issues = [Issue(rule, kind, desc, n) for (rule, kind, desc), n in counts.items()]
        return sorted(issues, key=lambda i: (order.get(i.kind, 3), -i.count, i.rule_name))

    def summary(self) -> str:
        """Résumé lisible (CLI)."""
        if not self.items:
            return "Évaluation impossible : aucune section reconnue par les règles."
        lines = [
            f"Score : {self.score:.0f} % de sections conformes "
            f"({self.ok_count}/{self.total}) — note : {self.grade}.",
            f"{self.count(CORRECTED)} à corriger automatiquement, "
            f"{self.count(TO_REVIEW)} à vérifier à la main.",
            "",
            "Par règle :",
        ]
        for rule in self.by_rule():
            lines.append(
                f"  - {rule.rule_name} : {rule.score:.0f} % ({rule.ok_count}/{rule.total})"
            )
        issues = self.issues()
        if issues:
            labels = {"flagged": "À VÉRIFIER", "placeholder": "MARQUEUR", "corrected": "À CORRIGER"}
            lines += ["", "Règles non respectées :"]
            for issue in issues:
                lines.append(
                    f"  - {labels.get(issue.kind, issue.kind)} [{issue.rule_name}] "
                    f"{issue.description} : {issue.count} section(s)"
                )
        return "\n".join(lines)


def _evaluate_paragraph(label: str, text: str, registry: RuleRegistry) -> List[EvaluationItem]:
    """Applique les règles en chaîne au texte (sans docx) : un élément par règle."""
    items = []
    current = text
    for rule in registry.rules_for(text):
        result = rule.apply(current)
        items.append(
            EvaluationItem(
                label=label,
                rule_name=rule.name,
                status=status_of(result.actions, result.new_text != current),
                actions=list(result.actions),
                text=text,
            )
        )
        current = result.new_text
    return items


def evaluate_texts(
    texts: List[str], registry: RuleRegistry, labels: Optional[List[str]] = None
) -> EvaluationReport:
    """Évalue une liste de textes de paragraphes (utile en test)."""
    report = EvaluationReport(thresholds=dict(get_config().evaluation_thresholds))
    for index, text in enumerate(texts):
        label = labels[index] if labels else f"Paragraphe {index + 1}"
        report.items.extend(_evaluate_paragraph(label, text, registry))
    return report


def evaluate_document(document, registry: RuleRegistry) -> EvaluationReport:
    """Évalue un document python-docx (corps, tableaux, en-têtes / pieds de page)."""
    texts, labels = [], []
    for index, (location, paragraph) in enumerate(docx_io.iter_paragraphs(document)):
        texts.append(paragraph.text)
        labels.append(location or f"Paragraphe {index + 1}")
    return evaluate_texts(texts, registry, labels)


def evaluate_file(
    input_path: str, enabled_names: "set[str] | None" = None
) -> EvaluationReport:
    """Évalue un fichier .docx avec les règles activées ; le fichier n'est pas modifié."""
    return evaluate_document(docx_io.load(input_path), build_registry(enabled_names))
