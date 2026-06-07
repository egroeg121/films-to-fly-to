"""CLI entry point: films-to-fly-to <flight> <date>

Usage:
    export OMDB_API_KEY=<your-key>
    films-to-fly-to BA286 2026-06-15

Prints a ranked list of films available on the BA in-flight catalog for that month.

MVP notes:
- The BA catalog is fleet-wide for a given month; the flight number and date are
  used to derive the month and (in a later iteration) confirm the aircraft is IFE-
  equipped. For the MVP, any valid BA flight number is accepted and the current
  catalog is returned regardless of aircraft type.
- Films are ranked by IMDb score (fallback: RT/100*10), highest first.
- Unrated films (not found in OMDb) are listed at the bottom.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
from dataclasses import dataclass

from films_to_fly_to.catalog import CatalogFilm, fetch_catalog
from films_to_fly_to.ratings import OmdbRatingSource, RatingResult


@dataclass
class RankedFilm:
    catalog: CatalogFilm
    rating: RatingResult | None

    @property
    def sort_key(self) -> float:
        if self.rating and self.rating.score is not None:
            return self.rating.score
        return -1.0

    def why_watch(self) -> str:
        if self.rating is None:
            return "No rating data available."
        score = self.rating.score
        genres = self.catalog.genres
        genre_str = "/".join(genres[:2]) if genres else "film"
        if score is None:
            return f"A {genre_str} — no score on record."
        if score >= 8.0:
            return f"Critically acclaimed {genre_str} (IMDb {score:.1f})."
        if score >= 7.0:
            return f"Well-regarded {genre_str} (IMDb {score:.1f})."
        if score >= 6.0:
            return f"Decent {genre_str} (IMDb {score:.1f})."
        return f"{genre_str.capitalize()} — take it or leave it (IMDb {score:.1f})."


def run(flight: str, date: str, *, omdb_key: str) -> int:
    print(f"Fetching BA catalog for {flight} on {date}...", file=sys.stderr)

    try:
        films = fetch_catalog()
    except urllib.error.URLError as exc:
        print(f"error: could not fetch catalog: {exc}", file=sys.stderr)
        return 1

    if not films:
        print(
            "BA catalog is behind a holding page or empty. Try again later.",
            file=sys.stderr,
        )
        return 1

    print(f"  {len(films)} films in catalog.", file=sys.stderr)
    print("Fetching ratings from OMDb...", file=sys.stderr)

    source = OmdbRatingSource(omdb_key)
    ranked: list[RankedFilm] = []

    for i, film in enumerate(films):
        if i > 0 and i % 20 == 0:
            print(f"  {i}/{len(films)}...", file=sys.stderr)
        # Small delay to stay within free-tier rate limits
        if i > 0:
            time.sleep(0.15)
        try:
            result = source.lookup(film.title, film.year)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                print(f"\nerror: OMDb rejected key (HTTP {exc.code}) — check OMDB_API_KEY", file=sys.stderr)
                return 1
            result = None
        except (urllib.error.URLError, json.JSONDecodeError):
            result = None
        ranked.append(RankedFilm(catalog=film, rating=result))

    ranked.sort(key=lambda r: r.sort_key, reverse=True)

    print()
    print(f"Films on BA {flight} ({date}) — ranked by rating")
    print("=" * 60)
    for pos, item in enumerate(ranked, 1):
        year_str = f" ({item.catalog.year})" if item.catalog.year else ""
        score_str = (
            f"{item.rating.score:.1f}/10" if item.rating and item.rating.score is not None else "unrated"
        )
        print(f"{pos:3}. {item.catalog.title}{year_str}  [{score_str}]")
        print(f"      {item.why_watch()}")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    if len(argv) != 2:
        print("usage: films-to-fly-to <flight> <date>", file=sys.stderr)
        print("  e.g.  films-to-fly-to BA286 2026-06-15", file=sys.stderr)
        return 2

    flight, date = argv

    omdb_key = os.environ.get("OMDB_API_KEY")
    if not omdb_key:
        print("error: set OMDB_API_KEY in the environment", file=sys.stderr)
        return 2

    return run(flight, date, omdb_key=omdb_key)


if __name__ == "__main__":
    raise SystemExit(main())
