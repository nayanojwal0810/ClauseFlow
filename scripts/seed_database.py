#!/usr/bin/env python3
"""CLI script to seed the ClauseFlow database with initial demo data."""

from __future__ import annotations

from pathlib import Path
import sys

from clauseflow.db.database import get_engine, get_session
from clauseflow.db.seed import seed_demo_data


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent

    try:
        engine = get_engine()
        with get_session(engine) as session:
            summary = seed_demo_data(session, repo_root)
            session.commit()
    except Exception as exc:
        print(f"Error seeding database: {exc}", file=sys.stderr)
        return 1

    print("Database seeding completed successfully.")
    for k, v in summary.items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

