"""Prototype: look up a film's rating via OMDb.

Usage:
    export OMDB_API_KEY=<your-key>
    python prototypes/rating_source/omdb_lookup.py "The Substance" --year 2024

Exercises the adapter shape described in docs/decisions/0001-rating-source.md.
Intentionally has no project dependencies — uses only the stdlib so it can be
run before the project's package layout is set up.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

OMDB_ENDPOINT = "https://www.omdbapi.com/"


@dataclass
class RatingResult:
    source: str
    external_id: str
    title: str
    year: int | None
    score: float | None
    score_raw: dict = field(default_factory=dict)


class RatingSource(Protocol):
    def lookup(self, title: str, year: int | None) -> RatingResult | None: ...


class OmdbRatingSource:
    def __init__(self, api_key: str, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def lookup(self, title: str, year: int | None) -> RatingResult | None:
        params = {"apikey": self._api_key, "t": title, "type": "movie"}
        if year is not None:
            params["y"] = str(year)
        url = f"{OMDB_ENDPOINT}?{urllib.parse.urlencode(params)}"

        with urllib.request.urlopen(url, timeout=self._timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        if payload.get("Response") != "True":
            return None

        score = _pick_score(payload)
        return RatingResult(
            source="omdb",
            external_id=payload["imdbID"],
            title=payload.get("Title", title),
            year=_safe_int(payload.get("Year")),
            score=score,
            score_raw={
                "imdbRating": payload.get("imdbRating"),
                "Ratings": payload.get("Ratings"),
                "Metascore": payload.get("Metascore"),
            },
        )


def _pick_score(payload: dict) -> float | None:
    """Normalise OMDb's varied score formats to 0-10.

    Prefer IMDb (widest coverage). Fall back to Rotten Tomatoes critic score.
    """
    imdb = payload.get("imdbRating")
    if imdb and imdb != "N/A":
        try:
            return float(imdb)
        except ValueError:
            pass

    for entry in payload.get("Ratings", []):
        if entry.get("Source") == "Rotten Tomatoes":
            value = entry.get("Value", "").rstrip("%")
            try:
                return float(value) / 10.0
            except ValueError:
                continue
    return None


def _safe_int(value: object) -> int | None:
    if not isinstance(value, str):
        return None
    head = value.split("-", 1)[0].strip()
    try:
        return int(head)
    except ValueError:
        return None


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description="OMDb rating lookup prototype")
    parser.add_argument("title", help="Film title, e.g. 'The Substance'")
    parser.add_argument("--year", type=int, default=None, help="Release year")
    args = parser.parse_args(argv)

    api_key = os.environ.get("OMDB_API_KEY")
    if not api_key:
        print("error: set OMDB_API_KEY in the environment", file=sys.stderr)
        return 2

    source: RatingSource = OmdbRatingSource(api_key)
    result = source.lookup(args.title, args.year)
    if result is None:
        print(f"no match for {args.title!r} ({args.year})")
        return 1

    print(f"{result.title} ({result.year})  [{result.external_id}]")
    print(f"  score: {result.score}")
    print(f"  raw:   {result.score_raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
