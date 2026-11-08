"""Interface en ligne de commande pour standardiser une partie expérimentale.

Usage::

    python cli.py [--sans-commentaires] <entrée.docx> [sortie.docx]
    python cli.py --evaluer <entrée.docx>

Si le fichier de sortie n'est pas fourni, il est déduit du nom d'entrée en
ajoutant le suffixe ``_standardise``. Par défaut, chaque paragraphe à vérifier
reçoit un commentaire Word dans le fichier de sortie ; ``--sans-commentaires``
désactive ces commentaires.

``--evaluer`` n'écrit aucun fichier : il affiche le pourcentage de sections
conformes, la note obtenue et les règles non respectées.
"""

from __future__ import annotations

import os
import sys

from core.evaluation import evaluate_file
from core.processor import standardize_file

NO_COMMENTS_FLAG = "--sans-commentaires"
EVALUATE_FLAG = "--evaluer"


def usage() -> str:
    """Ligne d'aide, avec le nom réel de la commande (script ou exécutable)."""
    if getattr(sys, "frozen", False):  # exécutable PyInstaller
        program = os.path.basename(sys.executable)
    else:
        program = "python cli.py"
    return (
        f"Usage : {program} [{NO_COMMENTS_FLAG}] <entrée.docx> [sortie.docx]\n"
        f"        {program} {EVALUATE_FLAG} <entrée.docx>"
    )


def default_output_path(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}_standardise{ext}"


def _force_utf8_stdout() -> None:
    """Passe la sortie standard en UTF-8.

    Le rapport contient δ, exposants et indices Unicode : sur une console
    Windows (cp1252 par défaut), ``print`` lèverait ``UnicodeEncodeError``.
    """
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8", errors="replace")


def main(argv: list[str]) -> int:
    _force_utf8_stdout()
    args = argv[1:]
    annotate = NO_COMMENTS_FLAG not in args
    evaluate = EVALUATE_FLAG in args
    args = [a for a in args if a not in (NO_COMMENTS_FLAG, EVALUATE_FLAG)]
    unknown = [a for a in args if a.startswith("--")]
    if unknown or not args:
        if unknown:
            print(f"Option inconnue : {unknown[0]}")
        print(usage())
        return 2

    input_path = args[0]
    if not os.path.exists(input_path):
        print(f"Fichier introuvable : {input_path}")
        return 1

    if evaluate:
        if len(args) > 1:
            print(f"{EVALUATE_FLAG} n'écrit aucun fichier : pas de fichier de sortie.")
            print(usage())
            return 2
        print(evaluate_file(input_path).summary())
        return 0

    output_path = args[1] if len(args) > 1 else default_output_path(input_path)
    try:
        report = standardize_file(input_path, output_path, annotate=annotate)
    except ValueError as exc:
        print(exc)
        return 1

    print(f"Fichier standardisé écrit : {output_path}\n")
    print(report.summary())
    return 0


def run() -> None:
    """Point d'entrée de la commande installée ``standardisation-rmn``."""
    raise SystemExit(main(sys.argv))


if __name__ == "__main__":
    run()
