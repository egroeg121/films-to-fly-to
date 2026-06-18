"""FastAPI web UI to serve ftft locally on localhost:8000.

Run with:
    export OMDB_API_KEY=<your-key>
    uv run uvicorn films_to_fly_to.app:app --reload
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from films_to_fly_to.catalog import CatalogFilm, fetch_catalog
from films_to_fly_to.cli import RankedFilm
from films_to_fly_to.ratings import OmdbRatingSource, RatingResult

app = FastAPI(title="Films to Fly To")

# Simple in-memory cache with TTL
_CATALOG_TTL = 3600.0  # 1 hour — catalog changes monthly
_RATING_TTL = 86400.0  # 24 hours — ratings are stable

_catalog_cache: tuple[float, list[CatalogFilm]] | None = None
_rating_cache: dict[tuple[str, int | None], tuple[float, RatingResult | None]] = {}


def _get_catalog() -> list[CatalogFilm]:
    global _catalog_cache
    now = time.monotonic()
    if _catalog_cache and now - _catalog_cache[0] < _CATALOG_TTL:
        return _catalog_cache[1]
    films = fetch_catalog()
    _catalog_cache = (now, films)
    return films


def _get_rating(source: OmdbRatingSource, title: str, year: int | None) -> RatingResult | None:
    key = (title, year)
    now = time.monotonic()
    if key in _rating_cache and now - _rating_cache[key][0] < _RATING_TTL:
        return _rating_cache[key][1]
    result = source.lookup(title, year)
    _rating_cache[key] = (now, result)
    return result

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Films to Fly To</title>
<style>
  body {{ font-family: system-ui, sans-serif; max-width: 800px; margin: 2rem auto; padding: 0 1rem; }}
  h1 {{ color: #1a1a2e; }}
  form {{ display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 2rem; }}
  input {{ padding: 0.5rem; border: 1px solid #ccc; border-radius: 4px; font-size: 1rem; }}
  button {{ padding: 0.5rem 1.25rem; background: #1a1a2e; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 1rem; }}
  button:hover {{ background: #2d2d5e; }}
  .film {{ border-bottom: 1px solid #eee; padding: 0.75rem 0; display: flex; align-items: baseline; gap: 0.5rem; }}
  .rank {{ color: #888; min-width: 2.5rem; text-align: right; }}
  .title {{ font-weight: 600; }}
  .year {{ color: #888; font-size: 0.9rem; }}
  .score {{ margin-left: auto; font-weight: 700; color: #1a6e1a; }}
  .unrated {{ color: #888; }}
  .why {{ color: #555; font-size: 0.9rem; margin-left: 3rem; }}
  .error {{ color: #c00; padding: 1rem; background: #fff0f0; border-radius: 4px; }}
  .info {{ color: #555; font-size: 0.9rem; margin-bottom: 1rem; }}
</style>
</head>
<body>
<h1>Films to Fly To ✈️</h1>
<form method="post" action="/search">
  <input name="flight" placeholder="Flight e.g. BA286" value="{flight}" required>
  <input name="date" type="date" value="{date}" required>
  <button type="submit">Find films</button>
</form>
{body}
</body>
</html>
"""


def _render_page(body: str = "", flight: str = "", date: str = "") -> HTMLResponse:
    html = _INDEX_HTML.format(body=body, flight=flight, date=date)
    return HTMLResponse(html)


@app.get("/", response_class=HTMLResponse)
async def index():
    return _render_page()


@app.post("/search", response_class=HTMLResponse)
async def search(
    flight: Annotated[str, Form()],
    date: Annotated[str, Form()],
):
    omdb_key = os.environ.get("OMDB_API_KEY")
    if not omdb_key:
        body = '<p class="error">OMDB_API_KEY is not set. Set it in your environment and restart the server.</p>'
        return _render_page(body, flight, date)

    try:
        films = _get_catalog()
    except urllib.error.URLError as exc:
        body = f'<p class="error">Could not fetch BA catalog: {exc}</p>'
        return _render_page(body, flight, date)

    if not films:
        body = '<p class="error">BA catalog is behind a holding page or empty. Try again later.</p>'
        return _render_page(body, flight, date)

    source = OmdbRatingSource(omdb_key)
    ranked: list[RankedFilm] = []

    for i, film in enumerate(films):
        try:
            # Only sleep between requests if rating not already cached
            if i > 0 and (film.title, film.year) not in _rating_cache:
                time.sleep(0.15)
            result = _get_rating(source, film.title, film.year)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                body = f'<p class="error">OMDb rejected API key (HTTP {exc.code}). Check OMDB_API_KEY.</p>'
                return _render_page(body, flight, date)
            result = None
        except (urllib.error.URLError, json.JSONDecodeError):
            result = None
        ranked.append(RankedFilm(catalog=film, rating=result))

    ranked.sort(key=lambda r: r.sort_key, reverse=True)

    rows = [f'<p class="info">BA {flight} · {date} · {len(ranked)} films</p>']
    for pos, item in enumerate(ranked, 1):
        year_str = f'<span class="year">({item.catalog.year})</span>' if item.catalog.year else ""
        if item.rating and item.rating.score is not None:
            score_str = f'<span class="score">{item.rating.score:.1f}</span>'
        else:
            score_str = '<span class="unrated">unrated</span>'
        rows.append(
            f'<div class="film">'
            f'<span class="rank">{pos}.</span>'
            f'<span class="title">{item.catalog.title}</span>'
            f'{year_str}'
            f'{score_str}'
            f'</div>'
            f'<div class="why">{item.why_watch()}</div>'
        )

    body = "\n".join(rows)
    return _render_page(body, flight, date)
