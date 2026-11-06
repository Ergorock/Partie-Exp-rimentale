"""Lecture et écriture de fichiers .docx.

Ce module isole toute interaction avec ``python-docx`` afin que le reste du
cœur de traitement (règles, processor) ne dépende pas directement de la
bibliothèque. Un paragraphe ``.docx`` peut être découpé en plusieurs *runs*
(fragments de mise en forme, ex. gras / italique / indices).

Pour appliquer une correction tout en conservant la mise en forme du reste du
paragraphe, on utilise ``apply_text_edit`` : il calcule les différences entre
l'ancien et le nouveau texte et ne modifie que les runs réellement touchés,
laissant intacts les runs environnants (et donc leur style).
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING, List, Optional

from docx import Document
from docx.document import Document as DocumentObject
from docx.text.paragraph import Paragraph

if TYPE_CHECKING:
    from core.rules.base import StyledSegment


def load(path: str) -> DocumentObject:
    """Ouvre un fichier .docx et retourne l'objet Document.

    Args:
        path: chemin vers le fichier .docx à ouvrir.

    Returns:
        L'objet ``Document`` de python-docx.
    """
    return Document(path)


def save(document: DocumentObject, output_path: str) -> None:
    """Sauvegarde le document dans le chemin de sortie.

    Args:
        document: le document à sauvegarder.
        output_path: chemin du fichier .docx de sortie.
    """
    document.save(output_path)


def paragraph_texts(document: DocumentObject) -> List[str]:
    """Retourne la liste des textes de tous les paragraphes du document.

    Args:
        document: le document à parcourir.

    Returns:
        La liste des textes de paragraphes (y compris les paragraphes vides).
    """
    return [p.text for p in document.paragraphs]


def set_paragraph_text(paragraph: Paragraph, new_text: str) -> None:
    """Remplace tout le texte d'un paragraphe (sans préserver les styles internes).

    Le nouveau texte est écrit dans le premier run existant ; les runs suivants
    sont vidés. Utilisé en dernier recours. Préférer ``apply_text_edit`` pour
    conserver la mise en forme.

    Args:
        paragraph: le paragraphe à modifier.
        new_text: le nouveau texte à écrire.
    """
    if not paragraph.runs:
        paragraph.add_run(new_text)
        return

    paragraph.runs[0].text = new_text
    for run in paragraph.runs[1:]:
        run.text = ""


def apply_text_edit(paragraph: Paragraph, old_text: str, new_text: str) -> None:
    """Applique une correction à un paragraphe en préservant la mise en forme.

    Au lieu de réécrire tout le texte dans un seul run (ce qui écrase gras,
    italique, indices…), on calcule un diff entre ``old_text`` et ``new_text``
    et on ne modifie que les portions de runs réellement touchées. Les runs non
    concernés gardent leur texte et leur style d'origine.

    La correspondance se fait par position de caractère : chaque caractère du
    paragraphe appartient à un run donné. Les segments « égaux » du diff sont
    laissés tels quels ; les insertions et remplacements sont écrits dans le
    run qui couvre la position concernée (typiquement un run existant, dont on
    conserve ainsi le style).

    Hypothèse : ``old_text`` correspond au texte courant du paragraphe. Si ce
    n'est pas le cas, on retombe sur ``set_paragraph_text``.

    Args:
        paragraph: le paragraphe à modifier.
        old_text: le texte courant du paragraphe (avant correction).
        new_text: le texte corrigé.
    """
    if old_text == new_text:
        return

    runs = paragraph.runs
    if not runs or paragraph.text != old_text:
        # Sécurité : structure inattendue -> remplacement simple.
        set_paragraph_text(paragraph, new_text)
        return

    # Texte cible par run (initialisé au texte d'origine de chaque run).
    run_texts: List[str] = [r.text for r in runs]

    # Bornes [début, fin) de chaque run dans le texte complet du paragraphe.
    starts: List[int] = []
    pos = 0
    for t in run_texts:
        starts.append(pos)
        pos += len(t)

    def run_index_for(position: int) -> int:
        """Retourne l'indice du run couvrant la position donnée (clampé)."""
        idx = 0
        for i, start in enumerate(starts):
            if position >= start:
                idx = i
            else:
                break
        return idx

    # On reconstruit le texte de chaque run à partir des opérations du diff.
    new_run_texts: List[str] = ["" for _ in runs]
    matcher = SequenceMatcher(a=old_text, b=new_text, autojunk=False)

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "equal":
            # Copie caractère par caractère dans le run d'origine correspondant.
            for offset in range(i2 - i1):
                ri = run_index_for(i1 + offset)
                new_run_texts[ri] += old_text[i1 + offset]
        elif tag in ("replace", "insert"):
            # Le texte inséré/remplacé est rattaché au run couvrant i1
            # (ou le dernier run si i1 est en fin de texte).
            anchor = i1 if i1 < len(old_text) else len(old_text) - 1
            ri = run_index_for(max(anchor, 0))
            new_run_texts[ri] += new_text[j1:j2]
        elif tag == "delete":
            # Les caractères supprimés ne sont simplement pas recopiés.
            continue

    for run, text in zip(runs, new_run_texts):
        run.text = text


def _write_fragments(paragraph: Paragraph, fragments) -> None:
    """Vide le paragraphe de ses runs puis écrit un run par fragment.

    ``fragments`` est une liste de triplets ``(texte, bold, italic)`` où
    ``bold`` / ``italic`` sont des états tri-valués (``True`` / ``False`` /
    ``None``) écrits tels quels dans le run (préservation possible d'un style
    d'origine). Un fragment au texte vide est ignoré.
    """
    for run in list(paragraph.runs):
        run._element.getparent().remove(run._element)
    for text, bold, italic in fragments:
        if not text:
            continue
        run = paragraph.add_run(text)
        run.bold = bold
        run.italic = italic


def _rewrite_paragraph_with_segments(
    paragraph: Paragraph, segments: List["StyledSegment"]
) -> None:
    """Réécrit tout le paragraphe à partir de segments stylisés.

    Utilisé comme repli (fallback) quand la portion à remplacer est
    introuvable ou que la structure est inattendue : on vide le paragraphe de
    ses runs puis on ajoute un run par segment, en positionnant le gras et
    l'italique. Le style des runs d'origine est perdu, mais la mise en forme
    demandée par la règle (gras / italique) apparaît quand même.
    """
    fragments = [
        (seg.text, True if seg.bold else None, True if seg.italic else None)
        for seg in segments
    ]
    _write_fragments(paragraph, fragments)


def apply_styled_edit(
    paragraph: Paragraph,
    old_text: str,
    new_text: str,
    replaced_text: Optional[str],
    segments: List["StyledSegment"],
) -> None:
    """Applique une édition stylisée : remplace une portion par des runs stylisés.

    La sous-chaîne ``replaced_text`` (ou tout le texte du paragraphe si
    ``replaced_text`` vaut ``None``) est remplacée par une suite de runs créés à
    partir de ``segments`` (un run par ``StyledSegment``, avec ``run.bold`` /
    ``run.italic`` positionnés). Les runs situés avant et après la portion
    remplacée sont préservés lorsque c'est possible, afin de garder leur texte
    et leur style.

    Approche : on localise la portion ``[start, end)`` de ``replaced_text`` dans
    ``old_text`` (``str.find``), on recalcule les bornes par run comme dans
    ``apply_text_edit``, on vide la partie couverte par la portion puis on
    insère les nouveaux runs stylisés à la bonne position dans le XML du
    paragraphe.

    Repli propre : si ``paragraph.text != old_text`` ou si ``replaced_text`` est
    introuvable, on réécrit tout le paragraphe en runs stylisés
    (``_rewrite_paragraph_with_segments``) de sorte que le gras / italique
    apparaisse quand même.

    Args:
        paragraph: le paragraphe à modifier.
        old_text: le texte courant du paragraphe (avant édition).
        new_text: le texte final complet attendu du paragraphe (pour cohérence).
        replaced_text: la sous-chaîne exacte de ``old_text`` à remplacer, ou
            ``None`` pour remplacer tout le paragraphe.
        segments: les segments stylisés qui remplacent la portion.
    """
    runs = paragraph.runs

    # Cas de repli : structure inattendue ou remplacement global demandé.
    if not runs or paragraph.text != old_text or replaced_text is None:
        _rewrite_paragraph_with_segments(paragraph, segments)
        return

    start = old_text.find(replaced_text)
    if start < 0 or not replaced_text:
        _rewrite_paragraph_with_segments(paragraph, segments)
        return
    end = start + len(replaced_text)

    # Bornes [début, fin) de chaque run dans le texte complet du paragraphe.
    run_texts: List[str] = [r.text for r in runs]
    starts: List[int] = []
    pos = 0
    for t in run_texts:
        starts.append(pos)
        pos += len(t)

    # On reconstruit la liste ordonnée des fragments (texte + style) du nouveau
    # paragraphe : partie AVANT la portion (style tri-valué d'origine préservé
    # par run), puis les segments stylisés, puis partie APRÈS (style d'origine
    # préservé). Chaque fragment est un triplet (texte, bold, italic).
    fragments = []

    for i, run in enumerate(runs):
        run_start = starts[i]
        run_end = starts[i] + len(run_texts[i])
        before = run_texts[i][: max(0, min(run_end, start) - run_start)]
        if before:
            fragments.append((before, run.bold, run.italic))

    for seg in segments:
        fragments.append(
            (seg.text, True if seg.bold else None, True if seg.italic else None)
        )

    for i, run in enumerate(runs):
        run_start = starts[i]
        run_end = starts[i] + len(run_texts[i])
        if run_end > end:
            after = run_texts[i][max(0, end - run_start):]
            if after:
                fragments.append((after, run.bold, run.italic))

    _write_fragments(paragraph, fragments)

    _ = new_text  # new_text est la vérité textuelle complète (voir RuleResult).
