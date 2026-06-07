"""CLI: catalog-diff — diff two snapshot files and report churn.

Usage:
    catalog-diff <snapshot-a> <snapshot-b>

Prints a summary of added and removed films.  Exits 0 if no churn, 1 if churn
detected (so it can be used in scripts / cron checks).
"""

from __future__ import annotations

import sys
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) != 2:
        print("usage: catalog-diff <snapshot-a> <snapshot-b>", file=sys.stderr)
        return 2

    path_a = Path(argv[0])
    path_b = Path(argv[1])

    for p in (path_a, path_b):
        if not p.exists():
            print(f"error: file not found: {p}", file=sys.stderr)
            return 2

    from films_to_fly_to.diff import diff_snapshots
    from films_to_fly_to.snapshot import load_snapshot

    a = load_snapshot(path_a)
    b = load_snapshot(path_b)

    result = diff_snapshots(a, b)
    print(result.summary(label_a=path_a.stem, label_b=path_b.stem))

    return 1 if result.has_churn else 0


if __name__ == "__main__":
    raise SystemExit(main())
