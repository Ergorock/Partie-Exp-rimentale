"""Interface commune des règles de standardisation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Tuple


class ActionKind(str, Enum):
    """Nature d'une action réalisée par une règle sur un paragraphe."""

    CORRECTED = "corrected"  # une correction automatique a été appliquée
    FLAGGED = "flagged"  # un problème a été signalé (sans correction sûre)
    PLACEHOLDER = "placeholder"  # un marqueur a été inséré pour une donnée manquante
    UNCHANGED = "unchanged"  # paragraphe conforme, rien à faire


@dataclass
class Action:
    """Une action réalisée par une règle, pour le rapport final."""

    kind: ActionKind
    message: str
    rule_name: str = ""
    #: Extraits EXACTS du texte final du paragraphe à surligner dans l'interface
    #: (valeur en cause, entrée concernée…). Affichage seulement ; un extrait
    #: introuvable est ignoré.
    highlights: Tuple[str, ...] = ()


@dataclass
class StyledSegment:
    """Fragment de texte stylisé destiné à produire un *run* docx distinct.

    Une règle qui veut contrôler la mise en forme (gras / italique) de sa
    sortie découpe la sous-chaîne de remplacement en plusieurs ``StyledSegment``.
    Chaque segment devient un run docx dont ``run.bold`` / ``run.italic`` sont
    positionnés d'après ``bold`` / ``italic``.
    """

    text: str
    bold: bool = False
    italic: bool = False
    #: Indice Word (``w:vertAlign=subscript``). RÉSERVÉ aux lettres sans indice
    #: Unicode : le D de ``[α]D``, le f de ``Rf`` et le R de ``tR``. Tout le
    #: reste s'écrit en indices / exposants Unicode.
    subscript: bool = False


@dataclass
class RuleResult:
    """Résultat de l'application d'une règle à un paragraphe.

    En plus de ``new_text`` (toujours le texte final COMPLET du paragraphe),
    une règle peut fournir une sortie stylisée optionnelle :

    - ``segments`` : la sous-chaîne de remplacement, découpée en segments
      stylisés. Si ``None`` (défaut), le comportement est inchangé (écriture par
      diff via ``apply_text_edit``, préservation des runs voisins).
    - ``replaced_text`` : la sous-chaîne EXACTE de l'ancien texte que
      ``segments`` remplace. Si ``None`` alors que ``segments`` est fourni, les
      segments remplacent tout le paragraphe.

    Important : ``new_text`` doit toujours refléter le texte final complet du
    paragraphe (concaténation du texte des segments inséré dans le reste), afin
    que ``process_texts`` (sans docx) et les rapports restent corrects même
    quand aucun style n'est appliqué.
    """

    new_text: str
    actions: List[Action] = field(default_factory=list)
    segments: Optional[List[StyledSegment]] = None
    replaced_text: Optional[str] = None

    @property
    def changed(self) -> bool:
        """Indique si le texte a été modifié par la règle."""
        return any(a.kind != ActionKind.UNCHANGED for a in self.actions)

    @property
    def is_styled(self) -> bool:
        """Vrai si la règle fournit une sortie stylisée (segments)."""
        return self.segments is not None


class Rule(ABC):
    """Interface d'une règle de standardisation.

    Une règle décide si elle s'applique à un paragraphe (``applies``) puis
    produit un texte corrigé et la liste des actions réalisées (``apply``).
    """

    #: Nom lisible de la règle, utilisé dans le rapport et l'interface.
    name: str = "rule"

    #: Description courte de la règle, affichée dans l'interface de gestion.
    description: str = ""

    @abstractmethod
    def applies(self, paragraph_text: str) -> bool:
        """Retourne True si la règle doit traiter ce paragraphe."""
        raise NotImplementedError

    @abstractmethod
    def apply(self, paragraph_text: str) -> RuleResult:
        """Applique la règle et retourne le texte corrigé + les actions."""
        raise NotImplementedError
