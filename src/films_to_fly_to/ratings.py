"""Rating providers: pluggable RatingProvider protocol with registry.

Strategy (see docs/decisions/0002-title-matching.md):
  1. Normalise title (lowercase, strip punctuation, move trailing articles)
  2. Extract inline year from title strings like 'Dune (2021)'
  3. Query provider with normalised title + year
  4. Retry with year ±1 for release-date drift
  5. Retry without year constraint
  6. Retry as type=series (TV content in BA catalog)
  7. Cache imdbID on success to avoid repeat lookups
"""

from __future__ import annotations

import json
import re
import unicodedata
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol


OMDB_ENDPOINT = "https://www.omdbapi.com/"

_ARTICLE_SUFFIX = re.compile(
    r",\s*(the|a|an|le|la|les|el|los|las|der|die|das|de|het|een)\s*$",
    re.IGNORECASE,
)
_INLINE_YEAR = re.compile(r"\(\s*(\d{4})\s*\)\s*$")
_PUNCTUATION = re.compile(r"[^\w\s]")
_WHITESPACE = re.compile(r"\s+")


@dataclass
class RatingResult:
    source: str
    external_id: str | None
    title: str
    year: int | None
    score: float | None
    rt_score: int | None = None  # Rotten Tomatoes percentage (0–100), if available
    score_raw: dict = field(default_factory=dict)
    imdb_score: float | None = None
    rt_percent: int | None = None
    metacritic: int | None = None
    letterboxd: float | None = None


class RatingProvider(Protocol):
    name: str

    def lookup(self, title: str, year: int | None) -> RatingResult | None: ...


@dataclass
class MatchResult:
    raw_title: str
    year_used: int | None
    normalised: str
    result: RatingResult
    cache_hit: bool
    retry_reason: str | None = None


def normalise_title(raw: str) -> tuple[str, int | None]:
    """Return (normalised_title, extracted_year) from a raw BA catalog title.

    Transformations (in order):
    1. Strip trailing inline year: 'The Substance (2024)' -> 'The Substance', 2024
    2. NFC-normalise unicode
    3. Move trailing article to front: 'Substance, The' -> 'The Substance'
    4. Lowercase
    5. Strip punctuation (replaced with space)
    6. Collapse whitespace
    """
    raw = raw.strip()

    year: int | None = None
    m = _INLINE_YEAR.search(raw)
    if m:
        year = int(m.group(1))
        raw = raw[: m.start()].strip()

    raw = unicodedata.normalize("NFC", raw)

    m2 = _ARTICLE_SUFFIX.search(raw)
    if m2:
        article = m2.group(1).capitalize()
        raw = article + " " + raw[: m2.start()].strip()

    raw = raw.lower()
    raw = _PUNCTUATION.sub(" ", raw)
    raw = _WHITESPACE.sub(" ", raw).strip()

    return raw, year


class OmdbRatingSource:
    name = "omdb"

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

        imdb_score = _parse_imdb_score(payload.get("imdbRating"))
        rt_percent = _parse_rt_percent(payload.get("Ratings", []))
        metacritic = _parse_metacritic(payload.get("Metascore"))

        return RatingResult(
            source="omdb",
            external_id=payload["imdbID"],
            title=payload.get("Title", title),
            year=_safe_int(payload.get("Year")),
            score=_pick_score(payload),
            rt_score=_pick_rt_score(payload),
            score_raw={
                "imdbRating": payload.get("imdbRating"),
                "Ratings": payload.get("Ratings"),
                "Metascore": payload.get("Metascore"),
            },
            imdb_score=imdb_score,
            rt_percent=rt_percent,
            metacritic=metacritic,
        )

    def fetch_by_id(self, imdb_id: str) -> RatingResult | None:
        params = {"apikey": self._api_key, "i": imdb_id}
        url = f"{OMDB_ENDPOINT}?{urllib.parse.urlencode(params)}"
        with urllib.request.urlopen(url, timeout=self._timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if payload.get("Response") != "True":
            return None

        imdb_score = _parse_imdb_score(payload.get("imdbRating"))
        rt_percent = _parse_rt_percent(payload.get("Ratings", []))
        metacritic = _parse_metacritic(payload.get("Metascore"))

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
            imdb_score=imdb_score,
            rt_percent=rt_percent,
            metacritic=metacritic,
        )


class TmdbRatingSource:
    """TMDB rating provider stub — not yet implemented."""

    name = "tmdb"

    def __init__(self, **kwargs) -> None:
        pass

    def lookup(self, title: str, year: int | None) -> RatingResult | None:
        raise NotImplementedError("TMDB provider is not yet implemented")


RATING_PROVIDERS: dict[str, type] = {
    "omdb": OmdbRatingSource,
    "tmdb": TmdbRatingSource,
}


def get_rating_provider(name: str, **kwargs) -> RatingProvider:
    cls = RATING_PROVIDERS.get(name)
    if cls is None:
        raise ValueError(f"Unknown rating provider: {name!r}. Available: {list(RATING_PROVIDERS)}")
    return cls(**kwargs)


class TitleCache:
    """JSON file-backed cache: (normalised_title, year) -> imdbID."""

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


class TitleMatcher:
    """Map raw BA catalog titles to RatingResults via a RatingProvider, with caching.

    Resolution order:
      1. Normalise title and extract inline year.
      2. Cache hit: fetch by imdbID and return immediately.
      3. Provider lookup: normalised title + year, type=movie.
      4. Year drift ±1 (only when year is known).
      5. No-year fallback (only when year was known and all year-pinned calls failed).
      6. type=series retry.
    """

    def __init__(self, source: OmdbRatingSource, cache: TitleCache) -> None:
        self._source = source
        self._cache = cache

    def resolve(self, raw_title: str, year: int | None = None) -> MatchResult | None:
        normalised, inline_year = normalise_title(raw_title)
        effective_year = year if year is not None else inline_year

        cached_id = self._cache.get(normalised, effective_year)
        if cached_id:
            result = self._source.fetch_by_id(cached_id)
            if result:
                return MatchResult(
                    raw_title=raw_title,
                    year_used=effective_year,
                    normalised=normalised,
                    result=result,
                    cache_hit=True,
                )

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
        r = self._source.lookup(normalised, year)
        if r:
            return r, None

        if year is not None:
            for delta in (-1, +1):
                r = self._source.lookup(normalised, year + delta)
                if r:
                    return r, f"year_drift({delta:+d})"

            r = self._source.lookup(normalised, None)
            if r:
                return r, "year_dropped"

        r = self._source.lookup_series(normalised, year)
        if r:
            return r, "type=series"

        return None, None


def _parse_imdb_score(value: str | None) -> float | None:
    if value and value != "N/A":
        try:
            return float(value)
        except ValueError:
            pass
    return None


def _pick_rt_score(payload: dict) -> int | None:
    """Return the Rotten Tomatoes score as an integer percentage (0–100), or None."""
    for entry in payload.get("Ratings", []):
        if entry.get("Source") == "Rotten Tomatoes":
            value = entry.get("Value", "").rstrip("%")
            try:
                return int(value)
            except ValueError:
                continue
    return None


def _parse_rt_percent(ratings: list) -> int | None:
    for entry in ratings:
        if entry.get("Source") == "Rotten Tomatoes":
            value = entry.get("Value", "").rstrip("%")
            try:
                return int(value)
            except ValueError:
                continue
    return None


def _parse_metacritic(value: str | None) -> int | None:
    if value and value != "N/A":
        try:
            return int(value)
        except ValueError:
            pass
    return None



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
