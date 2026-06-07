"""Save and load dated catalog snapshots for the churn-detection pilot (ftft-are).

Snapshots are stored as newline-delimited JSON (one record per line) under a
configurable directory, with filenames of the form ``YYYY-MM-DD.jsonl``.  The
format is deliberately simple so snapshots can be diffed with standard Unix
tools as well as via :func:`diff_snapshots`.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict
from datetime import date, datetime
from pathlib import Path

from films_to_fly_to.catalog import CatalogFilm, fetch_catalog


DEFAULT_SNAPSHOT_DIR = Path(os.environ.get("FTFT_SNAPSHOT_DIR", "snapshots"))


def snapshot_path(snapshot_dir: Path, day: date) -> Path:
    return snapshot_dir / f"{day.isoformat()}.jsonl"


def save_snapshot(
    films: list[CatalogFilm],
    day: date,
    *,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
) -> Path:
    """Serialise *films* to ``<snapshot_dir>/<day>.jsonl`` and return the path."""
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_path(snapshot_dir, day)
    with path.open("w", encoding="utf-8") as fh:
        for film in films:
            fh.write(json.dumps(asdict(film)) + "\n")
    return path


def load_snapshot(path: Path) -> list[CatalogFilm]:
    """Load a snapshot file, returning a list of :class:`CatalogFilm`."""
    films: list[CatalogFilm] = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            films.append(CatalogFilm(**data))
    return films


def fetch_and_save(
    day: date | None = None,
    *,
    snapshot_dir: Path = DEFAULT_SNAPSHOT_DIR,
    timeout: float = 30.0,
) -> tuple[Path, list[CatalogFilm], bool]:
    """Fetch the live catalog and save it as a snapshot.

    Returns ``(path, films, holding_page)`` where *holding_page* is True when
    the site was behind a queue page and *films* is empty.
    """
    if day is None:
        day = datetime.utcnow().date()
    films = fetch_catalog(timeout=timeout)
    holding_page = len(films) == 0
    path = save_snapshot(films, day, snapshot_dir=snapshot_dir)
    return path, films, holding_page
