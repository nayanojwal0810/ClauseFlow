#!/usr/bin/env python3
"""CLI entrypoint for CUAD contract dataset preparation and split assignment."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from clauseflow.data.prepare import prepare_dataset


def parse_args(args=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Prepare CUAD contracts, assign reproducible 328/80/102 splits, and generate manifest."
    )
    parser.add_argument(
        "--archive",
        type=Path,
        default=Path("data/raw/CUAD_v1.zip"),
        help="Path to full CUAD v1 zip archive (default: data/raw/CUAD_v1.zip)",
    )
    parser.add_argument(
        "--split-archive",
        type=Path,
        default=Path("data/raw/cuad_official_splits.zip"),
        help="Path to publisher official splits zip archive (default: data/raw/cuad_official_splits.zip)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("data/processed"),
        help="Directory to write processed JSONL files (default: data/processed)",
    )
    parser.add_argument(
        "--manifest-path",
        type=Path,
        default=Path("configs/contract_splits.json"),
        help="Path to write the tracked split manifest (default: configs/contract_splits.json)",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for 80-of-408 validation split selection (default: 42)",
    )
    return parser.parse_args(args)


def main() -> int:
    args = parse_args()

    # Friendly check for archive existence before attempting deep zip inspection
    if not args.archive.exists():
        # Check if CUAD_v1.zip is at the repository root
        root_candidate = Path("CUAD_v1.zip")
        if root_candidate.exists():
            args.archive = root_candidate
        else:
            print(
                f"Error: Full CUAD v1 archive not found at '{args.archive}'.\n"
                "Please place CUAD_v1.zip in data/raw/ or pass --archive <path>.",
                file=sys.stderr,
            )
            return 1

    if not args.split_archive.exists():
        print(
            f"Error: Publisher official splits archive not found at '{args.split_archive}'.\n"
            "Please download it to data/raw/cuad_official_splits.zip before running this command:\n"
            "  curl -L -o data/raw/cuad_official_splits.zip https://raw.githubusercontent.com/The-Atticus-Project/cuad/main/data.zip",
            file=sys.stderr,
        )
        return 1

    try:
        result = prepare_dataset(
            archive_path=args.archive,
            split_archive_path=args.split_archive,
            output_dir=args.output_dir,
            manifest_path=args.manifest_path,
            seed=args.seed,
        )
    except Exception as e:
        print(f"Dataset preparation failed: {e}", file=sys.stderr)
        return 1

    counts = result["counts"]
    print(f"CUAD v1 preparation completed successfully.")
    print(f"Total contracts: {counts['total']}")
    print(f"Official train:  {counts['official_train']}")
    print(f"  - Development: {counts['development']}")
    print(f"  - Validation:  {counts['validation']}")
    print(f"Official test:   {counts['final_test']}")
    print(f"Manifest:        {args.manifest_path}")
    print(f"Output files in: {args.output_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
