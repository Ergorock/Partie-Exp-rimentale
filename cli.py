"""Interface en ligne de commande pour standardiser une partie expérimentale.

Usage::

    python cli.py [--sans-commentaires] <entrée.docx> [sortie.docx]

Si le fichier de sortie n'est pas fourni, il est déduit du nom d'entrée en
ajoutant le suffixe ``_standardise``. Par défaut, chaque paragraphe à vérifier
reçoit un commentaire Word dans le fichier de sortie ; ``--sans-commentaires``
désactive ces commentaires.
"""

from __future__ import annotations

import os
import sys

from core.processor import standardize_file

USAGE = "Usage : python cli.py [--sans-commentaires] <entrée.docx> [sortie.docx]"
NO_COMMENTS_FLAG = "--sans-commentaires"


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
    args = [a for a in args if a != NO_COMMENTS_FLAG]
    unknown = [a for a in args if a.startswith("--")]
    if unknown or not args:
        if unknown:
            print(f"Option inconnue : {unknown[0]}")
        print(USAGE)
        return 2

    input_path = args[0]
    if not os.path.exists(input_path):
        print(f"Fichier introuvable : {input_path}")
        return 1

    output_path = args[1] if len(args) > 1 else default_output_path(input_path)
    try:
        report = standardize_file(input_path, output_path, annotate=annotate)
    except ValueError as exc:
        print(exc)
        return 1

    print(f"Fichier standardisé écrit : {output_path}\n")
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
