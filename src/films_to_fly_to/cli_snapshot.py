"""CLI: catalog-snapshot — fetch and persist a dated catalog snapshot.

Usage:
    catalog-snapshot [--date YYYY-MM-DD] [--dir PATH]

If --date is omitted, today's UTC date is used.
If --dir is omitted, the FTFT_SNAPSHOT_DIR env var is checked, then ./snapshots.

Exit codes:
    0  snapshot saved (even if catalog was empty / holding-page)
    1  network error
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    day = None
    snapshot_dir = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--date" and i + 1 < len(argv):
            i += 1
            try:
                day = datetime.strptime(argv[i], "%Y-%m-%d").date()
            except ValueError:
                print(f"error: bad date '{argv[i]}' (expected YYYY-MM-DD)", file=sys.stderr)
                return 2
        elif arg == "--dir" and i + 1 < len(argv):
            i += 1
            snapshot_dir = Path(argv[i])
        else:
            print(f"error: unexpected argument '{arg}'", file=sys.stderr)
            return 2
        i += 1

    import urllib.error

    from films_to_fly_to.snapshot import DEFAULT_SNAPSHOT_DIR, fetch_and_save

    if snapshot_dir is None:
        snapshot_dir = DEFAULT_SNAPSHOT_DIR

    try:
        path, films, holding_page = fetch_and_save(day, snapshot_dir=snapshot_dir)
    except urllib.error.URLError as exc:
        print(f"error: could not fetch catalog: {exc}", file=sys.stderr)
        return 1

    if holding_page:
        print(f"warning: BA site returned a holding page — snapshot saved (0 films): {path}", file=sys.stderr)
    else:
        print(f"Saved {len(films)} films → {path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
