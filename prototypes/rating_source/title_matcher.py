"""Prototype: title-matching strategy — BA catalog titles -> OMDb records.

BA catalog titles are messy ('The Substance (2024)', 'THE SUBSTANCE', 'Substance, The').
This module normalises raw titles, queries OMDb, and maintains a local
(title, year) -> imdbID cache so we only pay the lookup cost once per film.

Usage:
    export OMDB_API_KEY=<your-key>
    python prototypes/rating_source/title_matcher.py "The Substance (2024)"
    python prototypes/rating_source/title_matcher.py "OPPENHEIMER" --year 2023
    python prototypes/rating_source/title_matcher.py "Il Maestro" --year 2023 --cache-file /tmp/ftft_cache.json

Strategy:
    1. Normalise: lowercase, strip punctuation, strip parenthesised year, strip
       common suffixes like ', The' / ', A'.
    2. Extract inline year if present in the raw title string (e.g. 'Dune (2021)').
    3. Query OMDb with normalised title + year.
    4. If no match and a year was supplied, retry with year ± 1 (sequels/release drift).
    5. If still no match, retry with type=series to catch TV content BA includes.
    6. Cache successful (normalised_key, year) -> imdbID in a JSON file so
       subsequent runs skip the API call.

Edge cases handled:
    - 'The Substance' / 'Substance, The' / 'THE SUBSTANCE' all normalise to 'substance'
    - Inline year: 'Top Gun: Maverick (2022)' extracts year=2022
    - Year drift: sequels sometimes release a year later than the BA catalog records
    - TV specials: retry as type=series if movie lookup fails
    - Foreign titles: no special handling needed — OMDb accepts non-ASCII titles
      and will return the canonical English title in the response

Not in scope for this prototype:
    - Director/runtime disambiguation (requires OMDb's full /i= endpoint; relevant
      only when title-only search returns multiple candidates, which OMDb's ?t= param
      doesn't expose — it picks the most popular match automatically)
    - Persistent cache backed by a database (JSON file is fine for the prototype)
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


OMDB_ENDPOINT = "https://www.omdbapi.com/"
_ARTICLE_SUFFIX = re.compile(r",\s*(the|a|an|le|la|les|el|los|las|der|die|das|de|het|een)\s*$", re.IGNORECASE)
_INLINE_YEAR = re.compile(r"\(\s*(\d{4})\s*\)\s*$")
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

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


@dataclass
class MatchResult:
    raw_title: str
    year_used: int | None
    normalised: str
    result: RatingResult
    cache_hit: bool
    retry_reason: str | None = None


# ---------------------------------------------------------------------------
# Normalisation
# ---------------------------------------------------------------------------

def normalise_title(raw: str) -> tuple[str, int | None]:
    """Return (normalised_title, extracted_year) from a raw BA catalog title.

    Transformations applied (in order):
    1. Strip inline year suffix: 'The Substance (2024)' -> 'The Substance', 2024
    2. NFC normalise unicode so accented variants collapse
    3. Move article suffix to front: 'Substance, The' -> 'The Substance'
    4. Lowercase
    5. Strip all punctuation
    6. Collapse whitespace
    """
    raw = raw.strip()

    # 1. Extract inline year
    year: int | None = None
    m = _INLINE_YEAR.search(raw)
    if m:
        year = int(m.group(1))
        raw = raw[: m.start()].strip()

    # 2. NFC normalise
    raw = unicodedata.normalize("NFC", raw)

    # 3. Move trailing article to front ('Substance, The' -> 'The Substance')
    m2 = _ARTICLE_SUFFIX.search(raw)
    if m2:
        article = m2.group(1).capitalize()
        raw = article + " " + raw[: m2.start()].strip()

    # 4-6. Lowercase, strip punctuation, collapse whitespace
    raw = raw.lower()
    raw = _PUNCTUATION.sub(" ", raw)
    raw = _WHITESPACE.sub(" ", raw).strip()

    return raw, year


# ---------------------------------------------------------------------------
# OMDb client (same shape as omdb_lookup.py, extended with retry logic)
# ---------------------------------------------------------------------------

class OmdbRatingSource:
    def __init__(self, api_key: str, *, timeout: float = 10.0) -> None:
        self._api_key = api_key
        self._timeout = timeout

    def lookup(self, title: str, year: int | None) -> RatingResult | None:
        return self._query(title, year, media_type="movie")

    def lookup_series(self, title: str, year: int | None) -> RatingResult | None:
        return self._query(title, year, media_type="series")

    def _query(self, title: str, year: int | None, media_type: str) -> RatingResult | None:
        params: dict[str, str] = {
            "apikey": self._api_key,
            "t": title,
            "type": media_type,
        }
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


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------

class TitleCache:
    """JSON file-backed cache: (normalised_title, year_str) -> imdbID."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._data: dict[str, str] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                pass

    def _key(self, normalised: str, year: int | None) -> str:
        return f"{normalised}|{year}"

    def get(self, normalised: str, year: int | None) -> str | None:
        return self._data.get(self._key(normalised, year))

    def set(self, normalised: str, year: int | None, imdb_id: str) -> None:
        self._data[self._key(normalised, year)] = imdb_id
        self._path.write_text(json.dumps(self._data, indent=2))


# ---------------------------------------------------------------------------
# Matcher — ties normalisation, cache, and OMDb together
# ---------------------------------------------------------------------------

class TitleMatcher:
    """Map raw BA catalog titles to RatingResults via OMDb with caching.

    Resolution order for a given raw title:
      1. Normalise title, extract inline year (overridden by explicit year kwarg).
      2. Check cache (normalised, year) -> imdbID; if hit, fetch by ID and return.
      3. Query OMDb: normalised title + year, type=movie.
      4. If miss and year supplied: retry with year-1 then year+1 (release drift).
      5. If still miss: retry without year constraint.
      6. If still miss: retry as type=series (TV content in BA catalog).
      7. Cache successful imdbID and return.
    """

    def __init__(self, source: OmdbRatingSource, cache: TitleCache) -> None:
        self._source = source
        self._cache = cache

    def resolve(self, raw_title: str, year: int | None = None) -> MatchResult | None:
        normalised, inline_year = normalise_title(raw_title)
        effective_year = year if year is not None else inline_year

        # Cache hit
        cached_id = self._cache.get(normalised, effective_year)
        if cached_id:
            result = self._source._query(f"{{imdbID}}", None, "movie")
            # Re-fetch by imdbID using the ?i= param
            result = self._fetch_by_id(cached_id)
            if result:
                return MatchResult(
                    raw_title=raw_title,
                    year_used=effective_year,
                    normalised=normalised,
                    result=result,
                    cache_hit=True,
                )

        # Live lookup with retry ladder
        result, retry_reason = self._lookup_with_retries(normalised, effective_year)
        if result is None:
            return None

        self._cache.set(normalised, effective_year, result.external_id)
        return MatchResult(
            raw_title=raw_title,
            year_used=effective_year,
            normalised=normalised,
            result=result,
            cache_hit=False,
            retry_reason=retry_reason,
        )

    def _lookup_with_retries(
        self, normalised: str, year: int | None
    ) -> tuple[RatingResult | None, str | None]:
        # Step 1: exact year, movie
        r = self._source.lookup(normalised, year)
        if r:
            return r, None

        # Step 2: year drift ±1 (only if year was known)
        if year is not None:
            for delta in (-1, +1):
                r = self._source.lookup(normalised, year + delta)
                if r:
                    return r, f"year_drift({delta:+d})"

        # Step 3: no year constraint, movie
        if year is not None:
            r = self._source.lookup(normalised, None)
            if r:
                return r, "year_dropped"

        # Step 4: TV series (BA catalog includes some TV content)
        r = self._source.lookup_series(normalised, year)
        if r:
            return r, "type=series"

        return None, None

    def _fetch_by_id(self, imdb_id: str) -> RatingResult | None:
        params = {"apikey": self._source._api_key, "i": imdb_id}
        url = f"{OMDB_ENDPOINT}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=self._source._timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("Response") != "True":
            return None
        return RatingResult(
            source="omdb",
            external_id=payload["imdbID"],
            title=payload.get("Title", imdb_id),
            year=_safe_int(payload.get("Year")),
            score=_pick_score(payload),
            score_raw={
                "imdbRating": payload.get("imdbRating"),
                "Ratings": payload.get("Ratings"),
                "Metascore": payload.get("Metascore"),
            },
        )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Resolve a BA catalog title to an OMDb rating record."
    )
    parser.add_argument("title", help="Raw BA title, e.g. 'The Substance (2024)'")
    parser.add_argument("--year", type=int, default=None, help="Override year")
    parser.add_argument(
        "--cache-file",
        default=".ftft_title_cache.json",
        help="Path to JSON cache file (default: .ftft_title_cache.json)",
    )
    parser.add_argument(
        "--show-normalised",
        action="store_true",
        help="Print normalised title and exit (no API call)",
    )
    args = parser.parse_args(argv)

    if args.show_normalised:
        norm, year = normalise_title(args.title)
        print(f"normalised: {norm!r}  year: {year}")
        return 0

    api_key = os.environ.get("OMDB_API_KEY")
    if not api_key:
        print("error: set OMDB_API_KEY in the environment", file=sys.stderr)
        return 2

    source = OmdbRatingSource(api_key)
    cache = TitleCache(Path(args.cache_file))
    matcher = TitleMatcher(source, cache)

    match = matcher.resolve(args.title, args.year)
    if match is None:
        print(f"no match for {args.title!r}")
        return 1

    r = match.result
    flags = []
    if match.cache_hit:
        flags.append("cache-hit")
    if match.retry_reason:
        flags.append(f"retry:{match.retry_reason}")
    flag_str = f"  [{', '.join(flags)}]" if flags else ""

    print(f"{r.title} ({r.year})  [{r.external_id}]{flag_str}")
    print(f"  normalised: {match.normalised!r}")
    print(f"  score:      {r.score}")
    print(f"  raw:        {r.score_raw}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
