"""Interface en ligne de commande pour standardiser une partie expérimentale.

Usage::

    python cli.py <entrée.docx> [sortie.docx]

Si le fichier de sortie n'est pas fourni, il est déduit du nom d'entrée en
ajoutant le suffixe ``_standardise``.
"""

from __future__ import annotations

import os
import sys

from core.processor import standardize_file


def default_output_path(input_path: str) -> str:
    base, ext = os.path.splitext(input_path)
    return f"{base}_standardise{ext}"


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("Usage : python cli.py <entrée.docx> [sortie.docx]")
        return 2

    input_path = argv[1]
    if not os.path.exists(input_path):
        print(f"Fichier introuvable : {input_path}")
        return 1

    output_path = argv[2] if len(argv) > 2 else default_output_path(input_path)
    report = standardize_file(input_path, output_path)

    print(f"Fichier standardisé écrit : {output_path}\n")
    print(report.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
