"""FastAPI web UI to serve ftft locally on localhost:8000.

Run with:
    export OMDB_API_KEY=<your-key>
    uv run uvicorn films_to_fly_to.app:app --reload
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse

from films_to_fly_to.catalog import CatalogFilm, fetch_catalog
from films_to_fly_to.cli import RankedFilm
from films_to_fly_to.ratings import OmdbRatingSource, RatingResult, get_rating_provider

app = FastAPI(title="Films to Fly To")

_CATALOG_TTL = 48 * 3600  # 48 hours
_RATING_TTL = 7 * 24 * 3600  # 7 days

_DB_PATH = Path(os.environ.get("DATA_DIR", str(Path.home() / ".ftft"))) / "cache.db"


def _get_db() -> sqlite3.Connection | None:
    try:
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(_DB_PATH, check_same_thread=False)
        conn.execute(
            "CREATE TABLE IF NOT EXISTS catalog_cache "
            "(month TEXT PRIMARY KEY, films_json TEXT, fetched_at INTEGER)"
        )
        conn.execute(
            "CREATE TABLE IF NOT EXISTS rating_cache "
            "(provider TEXT NOT NULL DEFAULT 'omdb', title TEXT, year INTEGER, "
            "result_json TEXT, fetched_at INTEGER, "
            "PRIMARY KEY (provider, title, year))"
        )
        conn.commit()
        return conn
    except Exception as exc:
        print(f"ftft cache: DB unavailable, falling back to live fetch: {exc}", file=sys.stderr)
        return None


_db: sqlite3.Connection | None = _get_db()


def _get_catalog() -> list[CatalogFilm]:
    global _db
    month_key = datetime.now().strftime("%Y-%m")
    now = int(time.time())

    if _db is not None:
        try:
            row = _db.execute(
                "SELECT films_json, fetched_at FROM catalog_cache WHERE month = ?", (month_key,)
            ).fetchone()
            if row and now - row[1] < _CATALOG_TTL:
                return [CatalogFilm(**f) for f in json.loads(row[0])]
        except Exception as exc:
            print(f"ftft cache: catalog read failed: {exc}", file=sys.stderr)
            _db = None

    films = fetch_catalog()

    if _db is not None:
        try:
            _db.execute(
                "INSERT OR REPLACE INTO catalog_cache (month, films_json, fetched_at) VALUES (?, ?, ?)",
                (month_key, json.dumps([f.__dict__ for f in films]), now),
            )
            _db.commit()
        except Exception as exc:
            print(f"ftft cache: catalog write failed: {exc}", file=sys.stderr)

    return films


def _rating_in_cache(provider: str, title: str, year: int | None) -> bool:
    if _db is None:
        return False
    try:
        now = int(time.time())
        row = _db.execute(
            "SELECT fetched_at FROM rating_cache WHERE provider = ? AND title = ? AND year = ?",
            (provider, title, year if year is not None else -1),
        ).fetchone()
        return bool(row and now - row[0] < _RATING_TTL)
    except Exception:
        return False


def _get_rating(source: OmdbRatingSource, title: str, year: int | None) -> RatingResult | None:
    global _db
    provider = getattr(source, "name", "omdb")
    db_year = year if year is not None else -1
    now = int(time.time())

    if _db is not None:
        try:
            row = _db.execute(
                "SELECT result_json, fetched_at FROM rating_cache "
                "WHERE provider = ? AND title = ? AND year = ?",
                (provider, title, db_year),
            ).fetchone()
            if row and now - row[1] < _RATING_TTL:
                data = json.loads(row[0])
                return RatingResult(**data) if data is not None else None
        except Exception as exc:
            print(f"ftft cache: rating read failed: {exc}", file=sys.stderr)
            _db = None

    result = source.lookup(title, year)

    if _db is not None:
        try:
            result_json = json.dumps(result.__dict__) if result is not None else json.dumps(None)
            _db.execute(
                "INSERT OR REPLACE INTO rating_cache "
                "(provider, title, year, result_json, fetched_at) VALUES (?, ?, ?, ?, ?)",
                (provider, title, db_year, result_json, now),
            )
            _db.commit()
        except Exception as exc:
            print(f"ftft cache: rating write failed: {exc}", file=sys.stderr)

    return result

_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Films to Fly To</title>
<style>
  *, *::before, *::after {{ box-sizing: border-box; }}
  body {{ font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 1.5rem 2rem; }}
  h1 {{ color: #e6edf3; margin: 0 0 1.25rem; font-size: 1.6rem; letter-spacing: -0.02em; }}
  form {{ display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 1.75rem; }}
  input {{ padding: 0.5rem 0.75rem; background: #161b22; border: 1px solid #30363d; border-radius: 6px; font-size: 1rem; color: #e6edf3; }}
  input::placeholder {{ color: #8b949e; }}
  button {{ padding: 0.5rem 1.25rem; background: #1f6feb; color: white; border: none; border-radius: 6px; cursor: pointer; font-size: 1rem; font-weight: 600; }}
  button:hover {{ background: #388bfd; }}
  .info {{ color: #8b949e; font-size: 0.875rem; margin-bottom: 1.25rem; }}
  .grid {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 1.25rem; }}
  .card {{ background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; cursor: pointer; transition: transform 0.15s, box-shadow 0.15s; text-decoration: none; color: inherit; display: flex; flex-direction: column; }}
  .card:hover {{ transform: translateY(-3px); box-shadow: 0 8px 24px rgba(0,0,0,0.4); border-color: #58a6ff; }}
  .poster-wrap {{ position: relative; aspect-ratio: 2/3; background: #21262d; overflow: hidden; }}
  .poster-wrap img {{ width: 100%; height: 100%; object-fit: cover; display: block; }}
  .poster-placeholder {{ width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 2.5rem; color: #30363d; }}
  .badge {{ position: absolute; top: 6px; right: 6px; padding: 2px 7px; border-radius: 12px; font-size: 0.78rem; font-weight: 700; line-height: 1.4; }}
  .badge-good {{ background: #1a7f37; color: #fff; }}
  .badge-decent {{ background: #9a6700; color: #fff; }}
  .badge-unrated {{ background: #21262d; color: #8b949e; border: 1px solid #30363d; }}
  .card-body {{ padding: 0.6rem 0.75rem 0.75rem; flex: 1; display: flex; flex-direction: column; gap: 0.2rem; }}
  .card-title {{ font-size: 0.85rem; font-weight: 600; line-height: 1.3; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }}
  .card-year {{ font-size: 0.78rem; color: #8b949e; }}
  .error {{ color: #f85149; padding: 1rem; background: #161b22; border: 1px solid #da3633; border-radius: 6px; }}
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
    provider_name = os.environ.get("FTFT_RATING_PROVIDER", "omdb")
    omdb_key = os.environ.get("OMDB_API_KEY")
    if provider_name == "omdb" and not omdb_key:
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

    kwargs = {"api_key": omdb_key} if provider_name == "omdb" else {}
    source = get_rating_provider(provider_name, **kwargs)
    ranked: list[RankedFilm] = []

    for i, film in enumerate(films):
        try:
            # Only sleep between requests if rating not already cached
            if i > 0 and not _rating_in_cache(provider_name, film.title, film.year):
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

    cards = [f'<p class="info">BA {flight} · {date} · {len(ranked)} films</p><div class="grid">']
    for item in ranked:
        score = item.rating.score if item.rating and item.rating.score is not None else None
        if score is not None and score >= 7.0:
            badge_cls, badge_txt = "badge-good", f"{score:.1f}"
        elif score is not None:
            badge_cls, badge_txt = "badge-decent", f"{score:.1f}"
        else:
            badge_cls, badge_txt = "badge-unrated", "NR"

        if item.catalog.poster_url:
            poster_html = f'<img src="{item.catalog.poster_url}" alt="{item.catalog.title}" loading="lazy">'
        else:
            poster_html = '<div class="poster-placeholder">🎬</div>'

        year_html = f'<div class="card-year">{item.catalog.year}</div>' if item.catalog.year else ""

        if item.catalog.detail_url:
            tag_open = f'<a class="card" href="{item.catalog.detail_url}" target="_blank" rel="noopener">'
            tag_close = "</a>"
        else:
            tag_open = '<div class="card">'
            tag_close = "</div>"

        cards.append(
            f'{tag_open}'
            f'<div class="poster-wrap">'
            f'{poster_html}'
            f'<span class="badge {badge_cls}">{badge_txt}</span>'
            f'</div>'
            f'<div class="card-body">'
            f'<div class="card-title">{item.catalog.title}</div>'
            f'{year_html}'
            f'</div>'
            f'{tag_close}'
        )
    cards.append("</div>")

    body = "\n".join(cards)
    return _render_page(body, flight, date)
