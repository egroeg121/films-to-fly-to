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
from films_to_fly_to.ratings import OmdbRatingSource, RatingResult

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
            "(title TEXT, year INTEGER, result_json TEXT, fetched_at INTEGER, "
            "PRIMARY KEY (title, year))"
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


def _rating_in_cache(title: str, year: int | None) -> bool:
    if _db is None:
        return False
    try:
        now = int(time.time())
        row = _db.execute(
            "SELECT fetched_at FROM rating_cache WHERE title = ? AND year = ?",
            (title, year if year is not None else -1),
        ).fetchone()
        return bool(row and now - row[0] < _RATING_TTL)
    except Exception:
        return False


def _get_rating(source: OmdbRatingSource, title: str, year: int | None) -> RatingResult | None:
    global _db
    db_year = year if year is not None else -1
    now = int(time.time())

    if _db is not None:
        try:
            row = _db.execute(
                "SELECT result_json, fetched_at FROM rating_cache WHERE title = ? AND year = ?",
                (title, db_year),
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
                "INSERT OR REPLACE INTO rating_cache (title, year, result_json, fetched_at) VALUES (?, ?, ?, ?)",
                (title, db_year, result_json, now),
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
  .filters {{ margin-bottom: 1.25rem; display: flex; flex-direction: column; gap: 0.5rem; }}
  .filter-row {{ display: flex; align-items: center; gap: 0.4rem; flex-wrap: wrap; }}
  .filter-label {{ font-size: 0.8rem; color: #888; min-width: 5rem; }}
  .pill {{
    padding: 0.25rem 0.65rem; border: 1px solid #ccc; border-radius: 999px;
    font-size: 0.8rem; cursor: pointer; background: #fff; user-select: none;
    transition: background 0.1s, color 0.1s, border-color 0.1s;
  }}
  .pill:hover {{ border-color: #1a1a2e; }}
  .pill.active {{ background: #1a1a2e; color: #fff; border-color: #1a1a2e; }}
  .film-card.hidden {{ display: none; }}
  #filter-count {{ font-size: 0.85rem; color: #888; margin-bottom: 0.5rem; }}
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
            if i > 0 and not _rating_in_cache(film.title, film.year):
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

    # Collect filter values from all films
    all_genres: list[str] = sorted(
        {g for item in ranked for g in (item.catalog.genres or [])}
    )
    all_ratings: list[str] = sorted(
        {item.catalog.rating for item in ranked if item.catalog.rating}
    )

    def _decade(year: int | None) -> str:
        if year is None:
            return ""
        if year < 2000:
            return "Pre-2000"
        if year < 2010:
            return "2000s"
        if year < 2020:
            return "2010s"
        return "2020s"

    rows = [f'<p class="info">BA {flight} · {date} · {len(ranked)} films</p>']

    # Filter bar HTML (populated by JS for genres; static for decade/rating)
    genre_pills = "".join(
        f'<span class="pill" data-group="genre" data-value="{_esc(g)}">{_esc(g)}</span>'
        for g in all_genres
    )
    decade_pills = "".join(
        f'<span class="pill" data-group="decade" data-value="{d}">{d}</span>'
        for d in ["Pre-2000", "2000s", "2010s", "2020s"]
        if d in {_decade(item.catalog.year) for item in ranked}
    )
    rating_pills = "".join(
        f'<span class="pill" data-group="rating" data-value="{_esc(r)}">{_esc(r)}</span>'
        for r in all_ratings
    )

    filter_bar = (
        '<div class="filters" id="filters">'
        + (f'<div class="filter-row"><span class="filter-label">Genre</span>{genre_pills}</div>' if genre_pills else "")
        + (f'<div class="filter-row"><span class="filter-label">Decade</span>{decade_pills}</div>' if decade_pills else "")
        + (f'<div class="filter-row"><span class="filter-label">Rating</span>{rating_pills}</div>' if rating_pills else "")
        + "</div>"
        + '<div id="filter-count"></div>'
    )
    rows.append(filter_bar)

    for pos, item in enumerate(ranked, 1):
        year_str = f'<span class="year">({item.catalog.year})</span>' if item.catalog.year else ""
        if item.rating and item.rating.score is not None:
            score_str = f'<span class="score">{item.rating.score:.1f}</span>'
        else:
            score_str = '<span class="unrated">unrated</span>'
        genres_attr = _esc(json.dumps(item.catalog.genres or []))
        decade_attr = _esc(_decade(item.catalog.year))
        rating_attr = _esc(item.catalog.rating or "")
        rows.append(
            f'<div class="film-card"'
            f' data-genres=\'{genres_attr}\''
            f' data-decade="{decade_attr}"'
            f' data-rating="{rating_attr}">'
            f'<div class="film">'
            f'<span class="rank">{pos}.</span>'
            f'<span class="title">{item.catalog.title}</span>'
            f'{year_str}'
            f'{score_str}'
            f'</div>'
            f'<div class="why">{item.why_watch()}</div>'
            f'</div>'
        )

    rows.append(_FILTER_JS)
    body = "\n".join(rows)
    return _render_page(body, flight, date)


def _esc(s: str) -> str:
    """HTML-escape a string for use in attribute values."""
    return s.replace("&", "&amp;").replace('"', "&quot;").replace("'", "&#39;").replace("<", "&lt;").replace(">", "&gt;")


_FILTER_JS = """<script>
(function () {
  var active = { genre: new Set(), decade: new Set(), rating: new Set() };

  function applyFilters() {
    var cards = document.querySelectorAll('.film-card');
    var visible = 0;
    cards.forEach(function (card) {
      var genres = JSON.parse(card.dataset.genres || '[]');
      var decade = card.dataset.decade || '';
      var rating = card.dataset.rating || '';

      var passGenre = active.genre.size === 0 || genres.some(function (g) { return active.genre.has(g); });
      var passDecade = active.decade.size === 0 || active.decade.has(decade);
      var passRating = active.rating.size === 0 || active.rating.has(rating);

      if (passGenre && passDecade && passRating) {
        card.classList.remove('hidden');
        visible++;
      } else {
        card.classList.add('hidden');
      }
    });
    var countEl = document.getElementById('filter-count');
    if (countEl) {
      countEl.textContent = visible < cards.length ? (visible + ' of ' + cards.length + ' films') : '';
    }
  }

  document.querySelectorAll('#filters .pill').forEach(function (pill) {
    pill.addEventListener('click', function () {
      var group = pill.dataset.group;
      var value = pill.dataset.value;
      if (active[group].has(value)) {
        active[group].delete(value);
        pill.classList.remove('active');
      } else {
        // decade and rating are single-select (radio behaviour); genre is multi-select
        if (group !== 'genre') {
          active[group].clear();
          document.querySelectorAll('#filters .pill[data-group="' + group + '"]').forEach(function (p) {
            p.classList.remove('active');
          });
        }
        active[group].add(value);
        pill.classList.add('active');
      }
      applyFilters();
    });
  });
}());
</script>"""
