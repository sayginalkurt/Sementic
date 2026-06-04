#!/usr/bin/env python3
"""
CLI: üç ağ analizi matrislerini XLSX olarak kaydeder (AI kullanmaz; token tabanlı).

  - Co-occurrence  → cooccurrence_matrix.xlsx
  - Semantic       → semantic_matrix.xlsx
  - Epistemic      → epistemic_matrix.xlsx
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from analyses import run_all_analyses

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "output"


def save_matrix(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_excel(path, engine="openpyxl")
    print(f"  → {path}  ({df.shape[0]}×{df.shape[1]})")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Semantic / Co-occurrence / Epistemic kelime matrisleri"
    )
    parser.add_argument(
        "-i",
        "--input",
        type=Path,
        required=True,
        help="Girdi metin dosyası (.txt)",
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="XLSX çıktı klasörü",
    )
    parser.add_argument(
        "--min-freq",
        type=int,
        default=2,
        help="Kelimenin matrise girmesi için minimum frekans",
    )
    args = parser.parse_args()

    text = args.input.read_text(encoding="utf-8")
    vocab, matrices = run_all_analyses(text, min_freq=args.min_freq)

    print(f"Girdi: {args.input}")
    print(f"Sözlük: {len(vocab)} kelime")
    print("Matrisler:")

    names = {
        "cooccurrence": "cooccurrence_matrix.xlsx",
        "semantic": "semantic_matrix.xlsx",
        "epistemic": "epistemic_matrix.xlsx",
    }
    for key, filename in names.items():
        save_matrix(matrices[key], args.output_dir / filename)

    print("\nÖzet (ilk 5 kelime, co-occurrence üst üçgen):")
    co = matrices["cooccurrence"]
    preview = co.iloc[:5, :5]
    print(preview.to_string())


if __name__ == "__main__":
    main()
