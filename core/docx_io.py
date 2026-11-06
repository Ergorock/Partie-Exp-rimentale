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

from copy import deepcopy
from difflib import SequenceMatcher
from typing import TYPE_CHECKING, Iterator, List, Optional, Tuple

from docx import Document
from docx.document import Document as DocumentObject
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.text.paragraph import Paragraph
from docx.text.run import Run

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


# En-têtes / pieds de page d'une section : (libellé, attribut python-docx).
_HEADER_FOOTER_PARTS = (
    ("En-tête", "header"),
    ("En-tête (première page)", "first_page_header"),
    ("En-tête (pages paires)", "even_page_header"),
    ("Pied de page", "footer"),
    ("Pied de page (première page)", "first_page_footer"),
    ("Pied de page (pages paires)", "even_page_footer"),
)


def iter_paragraphs(document: DocumentObject) -> Iterator[Tuple[str, Paragraph]]:
    """Parcourt TOUS les paragraphes éditables du document, chacun une fois.

    Ordre : paragraphes du corps (libellé vide : le processor les numérote
    comme avant), puis tableaux du corps (récursivement, tableaux imbriqués
    compris), puis en-têtes et pieds de page de chaque section.

    Un paragraphe n'est produit qu'une fois : les cellules fusionnées (que
    python-docx répète) et les en-têtes liés à la section précédente (non
    parcourus, pour ne pas créer de définition vide) sont ignorés.

    Les notes de bas de page ne sont pas exposées par python-docx et ne sont
    donc pas traitées.

    Yields:
        Des couples ``(libellé, paragraphe)``.
    """
    # On garde une référence sur chaque élément vu : lxml renvoie alors le même
    # objet proxy pour un même nœud, ce qui rend le test d'identité fiable.
    seen: List = []
    seen_ids = set()

    def fresh(element) -> bool:
        if id(element) in seen_ids:
            return False
        seen.append(element)
        seen_ids.add(id(element))
        return True

    def walk_tables(tables, prefix: str):
        for t_index, table in enumerate(tables, start=1):
            t_label = f"{prefix}tableau {t_index}" if prefix else f"Tableau {t_index}"
            for r_index, row in enumerate(table.rows, start=1):
                for c_index, cell in enumerate(row.cells, start=1):
                    if not fresh(cell._tc):
                        continue
                    c_label = f"{t_label}, ligne {r_index}, cellule {c_index}"
                    for p_index, paragraph in enumerate(cell.paragraphs, start=1):
                        if fresh(paragraph._p):
                            yield f"{c_label}, paragraphe {p_index}", paragraph
                    yield from walk_tables(cell.tables, f"{c_label} > ")

    for paragraph in document.paragraphs:
        if fresh(paragraph._p):
            yield "", paragraph
    yield from walk_tables(document.tables, "")

    for s_index, section in enumerate(document.sections, start=1):
        for part_label, attr in _HEADER_FOOTER_PARTS:
            part = getattr(section, attr)
            if part.is_linked_to_previous:
                continue
            label = f"{part_label} (section {s_index})"
            for p_index, paragraph in enumerate(part.paragraphs, start=1):
                if fresh(paragraph._p):
                    yield f"{label}, paragraphe {p_index}", paragraph
            yield from walk_tables(part.tables, f"{label} > ")


def apply_text_edit(paragraph: Paragraph, old_text: str, new_text: str) -> bool:
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
    n'est pas le cas, ou si du texte vit hors des runs directs (lien
    hypertexte, champ…), le paragraphe n'est PAS modifié : un remplacement
    aveugle risquerait de dupliquer ou de supprimer du texte.

    Args:
        paragraph: le paragraphe à modifier.
        old_text: le texte courant du paragraphe (avant correction).
        new_text: le texte corrigé.

    Returns:
        ``True`` si le paragraphe porte ``new_text`` après l'appel, ``False``
        s'il n'a pas pu être modifié.
    """
    if old_text == new_text:
        return True

    runs = paragraph.runs
    if paragraph.text != old_text or not runs_cover_text(paragraph):
        return False

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
    return True


# --------------------------------------------------------------------------- #
# Édition stylisée
# --------------------------------------------------------------------------- #

# Propriétés retirées du style de base des segments stylisés : la règle fixe
# elle-même gras / italique, et les exposants / indices sont toujours écrits en
# Unicode, jamais en superscript / subscript Word.
_SEGMENT_STRIPPED_PROPS = ("w:b", "w:bCs", "w:i", "w:iCs", "w:vertAlign")


def runs_cover_text(paragraph: Paragraph) -> bool:
    """Vrai si les runs directs du paragraphe portent TOUT son texte.

    Faux lorsque du texte vit hors des runs directs (lien hypertexte, champ,
    contrôle de contenu…) : les positions calculées run par run ne
    correspondraient plus au texte du paragraphe, on ne doit donc pas l'éditer.
    """
    runs = paragraph.runs
    return bool(runs) and "".join(r.text for r in runs) == paragraph.text


def _run_starts(runs) -> List[int]:
    """Position de début de chaque run dans le texte du paragraphe."""
    starts: List[int] = []
    pos = 0
    for run in runs:
        starts.append(pos)
        pos += len(run.text)
    return starts


def _dominant_run(runs, start: int, end: int) -> Optional[Run]:
    """Run qui couvre le plus de caractères de l'intervalle ``[start, end)``."""
    best, best_overlap = None, -1
    for run, run_start in zip(runs, _run_starts(runs)):
        overlap = min(run_start + len(run.text), end) - max(run_start, start)
        if overlap > best_overlap:
            best, best_overlap = run, overlap
    return best


def _segment_rpr(base_run: Optional[Run]):
    """Copie du ``rPr`` du run de base, sans gras / italique / exposant Word."""
    if base_run is None or base_run._element.rPr is None:
        return None
    rpr = deepcopy(base_run._element.rPr)
    for tag in _SEGMENT_STRIPPED_PROPS:
        for element in rpr.findall(qn(tag)):
            rpr.remove(element)
    return rpr


def _make_run(paragraph: Paragraph, text: str, rpr, style=None):
    """Crée un élément ``w:r`` portant ``text`` et une copie de ``rpr``.

    ``style`` vaut ``None`` (propriétés de ``rpr`` conservées telles quelles) ou
    un couple ``(bold, italic)`` appliqué par-dessus.
    """
    element = OxmlElement("w:r")
    if rpr is not None:
        element.append(deepcopy(rpr))
    run = Run(element, paragraph)
    run.text = text
    if style is not None:
        run.bold, run.italic = style
    return element


def _segment_run(paragraph: Paragraph, segment: "StyledSegment", rpr):
    """Run d'un segment stylisé : gras / italique posés seulement si demandés."""
    style = (True if segment.bold else None, True if segment.italic else None)
    return _make_run(paragraph, segment.text, rpr, style)


def _replace_runs(paragraph: Paragraph, new_elements) -> None:
    """Remplace les runs directs du paragraphe par ``new_elements``, à leur place.

    Les nouveaux runs sont insérés avant le premier run d'origine : les autres
    éléments du paragraphe (signets…) gardent leur position relative.
    """
    runs = paragraph.runs
    anchor = runs[0]._element
    for element in new_elements:
        anchor.addprevious(element)
    for run in runs:
        run._element.getparent().remove(run._element)


def _rewrite_from_new_text(
    paragraph: Paragraph, new_text: str, segments: List["StyledSegment"]
) -> None:
    """Repli : réécrit tout le paragraphe à partir de ``new_text``.

    Les segments stylisés sont localisés dans ``new_text`` ; le texte qui les
    précède et les suit est écrit en clair avec le style du run dominant du
    paragraphe. Si les segments sont introuvables, on retombe sur une édition
    par diff (``apply_text_edit``) : la mise en forme demandée par la règle est
    perdue, mais AUCUN texte n'est supprimé.
    """
    seg_text = "".join(s.text for s in segments)
    index = new_text.find(seg_text) if seg_text else -1
    if index < 0:
        apply_text_edit(paragraph, paragraph.text, new_text)
        return
    base = _dominant_run(paragraph.runs, 0, len(paragraph.text))
    plain_rpr = base._element.rPr if base is not None else None
    seg_rpr = _segment_rpr(base)
    elements = []
    if new_text[:index]:
        elements.append(_make_run(paragraph, new_text[:index], plain_rpr))
    elements.extend(_segment_run(paragraph, s, seg_rpr) for s in segments if s.text)
    if new_text[index + len(seg_text):]:
        elements.append(_make_run(paragraph, new_text[index + len(seg_text):], plain_rpr))
    _replace_runs(paragraph, elements)


def apply_styled_edit(
    paragraph: Paragraph,
    old_text: str,
    new_text: str,
    replaced_text: Optional[str],
    segments: List["StyledSegment"],
) -> bool:
    """Applique une édition stylisée : remplace une portion par des runs stylisés.

    La sous-chaîne ``replaced_text`` (ou tout le paragraphe si ``None``) est
    remplacée par un run par ``StyledSegment``. Les runs situés avant et après
    la portion sont conservés avec TOUTES leurs propriétés (police, taille,
    couleur…). Les runs des segments reprennent les propriétés du run dominant
    de la portion remplacée, sans gras / italique / exposant Word (fixés par la
    règle ; exposants en Unicode).

    Repli sans perte : si ``paragraph.text != old_text`` ou si
    ``replaced_text`` est introuvable, le paragraphe est réécrit à partir de
    ``new_text`` (voir ``_rewrite_from_new_text``).

    Args:
        paragraph: le paragraphe à modifier.
        old_text: le texte attendu du paragraphe avant l'édition.
        new_text: le texte final complet du paragraphe (vérité textuelle).
        replaced_text: la sous-chaîne exacte de ``old_text`` à remplacer, ou
            ``None`` pour remplacer tout le paragraphe.
        segments: les segments stylisés qui remplacent la portion.

    Returns:
        ``False`` (paragraphe NON modifié) si sa structure Word n'est pas prise
        en charge (texte hors des runs directs), ``True`` sinon.
    """
    if not runs_cover_text(paragraph):
        return False

    current = paragraph.text
    if replaced_text is None:
        start, end = 0, len(current)
    else:
        found = current == old_text and bool(replaced_text)
        start = current.find(replaced_text) if found else -1
        if start < 0:
            _rewrite_from_new_text(paragraph, new_text, segments)
            return True
        end = start + len(replaced_text)

    runs = paragraph.runs
    starts = _run_starts(runs)
    seg_rpr = _segment_rpr(_dominant_run(runs, start, end))

    elements = []
    # Partie AVANT la portion : copie conforme des runs (propriétés comprises).
    for run, run_start in zip(runs, starts):
        before = run.text[: max(0, min(run_start + len(run.text), start) - run_start)]
        if before:
            elements.append(_make_run(paragraph, before, run._element.rPr))
    # Portion remplacée : un run par segment stylisé.
    elements.extend(_segment_run(paragraph, s, seg_rpr) for s in segments if s.text)
    # Partie APRÈS la portion.
    for run, run_start in zip(runs, starts):
        if run_start + len(run.text) > end:
            after = run.text[max(0, end - run_start):]
            if after:
                elements.append(_make_run(paragraph, after, run._element.rPr))

    _replace_runs(paragraph, elements)
    return True


