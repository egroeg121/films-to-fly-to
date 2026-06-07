"""OMDb rating source, adapted from prototypes/rating_source/omdb_lookup.py."""

from __future__ import annotations

import json
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
        params: dict[str, str] = {
            "apikey": self._api_key,
            "t": title,
            "type": "movie",
        }
        if year is not None:
            params["y"] = str(year)
        url = f"{OMDB_ENDPOINT}?{urllib.parse.urlencode(params)}"

        with urllib.request.urlopen(url, timeout=self._timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8"))

        if payload.get("Response") != "True":
            return None

        return RatingResult(
            source="omdb",
            external_id=payload["imdbID"],
            title=payload.get("Title", title),
            year=_safe_int(payload.get("Year")),
            score=_pick_score(payload),
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
