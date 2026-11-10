"""FastAPI web UI to serve ftft locally on localhost:8000.

Run with:
    export OMDB_API_KEY=<your-key>
    uv run uvicorn films_to_fly_to.app:app --reload
"""

from __future__ import annotations

import html as html_lib
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

from films_to_fly_to.airlines import (
    SUPPORTED_AIRLINES,
    Airline,
    airline_for_flight,
    get_airline,
)
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
        print(
            f"ftft cache: DB unavailable, falling back to live fetch: {exc}",
            file=sys.stderr,
        )
        return None


_db: sqlite3.Connection | None = _get_db()


def _get_catalog() -> list[CatalogFilm]:
    global _db
    month_key = datetime.now().strftime("%Y-%m")
    now = int(time.time())

    if _db is not None:
        try:
            row = _db.execute(
                "SELECT films_json, fetched_at FROM catalog_cache WHERE month = ?",
                (month_key,),
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


def _get_rating(
    source: OmdbRatingSource, title: str, year: int | None
) -> RatingResult | None:
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
            result_json = (
                json.dumps(result.__dict__) if result is not None else json.dumps(None)
            )
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
  body {{ font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 1.5rem 1rem; }}
  h1 {{ color: #e6edf3; margin: 0 0 1.25rem; font-size: 1.6rem; letter-spacing: -0.02em; }}
  input, select {{ padding: 0.5rem 0.75rem; background: #161b22; border: 1px solid #30363d; border-radius: 6px; font-size: 1rem; color: #e6edf3; }}
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
  form.search {{ display: flex; flex-direction: column; gap: 1rem; max-width: 34rem; margin-bottom: 1.75rem; }}
  fieldset {{ border: 1px solid #30363d; border-radius: 6px; padding: 0.75rem; margin: 0; display: flex; flex-wrap: wrap; gap: 0.75rem; }}
  legend {{ color: #8b949e; font-size: 0.85rem; padding: 0 0.4rem; }}
  label {{ display: flex; flex-direction: column; gap: 0.25rem; font-size: 0.85rem; color: #8b949e; flex: 1 1 8rem; }}
  .modes {{ display: flex; gap: 1rem; font-size: 0.95rem; }}
  .modes[hidden] {{ display: none; }}
  .modes label {{ flex-direction: row; align-items: center; gap: 0.4rem; flex: 0 0 auto; color: #e6edf3; }}
  .hidden-group {{ display: none; }}
  .supported {{ margin-top: 2rem; color: #8b949e; font-size: 0.9rem; }}
  .supported h2 {{ font-size: 1.05rem; color: #e6edf3; margin: 0 0 0.5rem; }}
  .supported li {{ margin: 0.2rem 0; }}
  .back {{ color: #58a6ff; margin-left: 0.5rem; }}
  h1 a.home {{ color: inherit; text-decoration: none; }}
</style>
</head>
<body>
<h1><a class="home" href="/">Films to Fly To ✈️</a></h1>
{body}
</body>
</html>
"""

_FORM_JS = """<script>
(function () {
  var radios = document.querySelectorAll('input[name="mode"]');
  var groups = {
    flight: document.getElementById('group-flight'),
    route: document.getElementById('group-route')
  };
  function sync() {
    var mode = document.querySelector('input[name="mode"]:checked').value;
    Object.keys(groups).forEach(function (k) {
      groups[k].classList.toggle('hidden-group', k !== mode);
    });
  }
  document.getElementById('modes').hidden = false;
  radios.forEach(function (r) { r.addEventListener('change', sync); });
  sync();
}());
</script>"""


def _form_html(
    airline: str = "",
    flight: str = "",
    from_: str = "",
    to: str = "",
    date: str = "",
    time_: str = "",
) -> str:
    """Search form. Without JS both input groups are shown."""
    route_mode = bool((from_ or to) and not flight)
    options = "".join(
        f'<option value="{_esc(a.iata)}"'
        f"{' selected' if a.iata == airline.upper() else ''}>"
        f"{_esc(a.name)} ({_esc(a.iata)})</option>"
        for a in SUPPORTED_AIRLINES
    )
    return (
        '<form class="search" method="post" action="/search">'
        '<div class="modes" id="modes" hidden>'
        '<label><input type="radio" name="mode" value="flight"'
        f"{'' if route_mode else ' checked'}> Flight number</label>"
        '<label><input type="radio" name="mode" value="route"'
        f"{' checked' if route_mode else ''}> Route</label></div>"
        f'<label>Airline<select name="airline">{options}</select></label>'
        '<fieldset id="group-flight"><legend>Flight number</legend>'
        '<label>Flight<input name="flight" placeholder="e.g. BA286" '
        f'value="{_esc(flight)}"></label></fieldset>'
        '<fieldset id="group-route"><legend>Route</legend>'
        '<label>From<input name="from" placeholder="LHR" maxlength="3" '
        f'pattern="[A-Za-z]{{3}}" value="{_esc(from_)}"></label>'
        '<label>To<input name="to" placeholder="JFK" maxlength="3" '
        f'pattern="[A-Za-z]{{3}}" value="{_esc(to)}"></label></fieldset>'
        "<fieldset><legend>Departure</legend>"
        f'<label>Date<input name="date" type="date" value="{_esc(date)}" required></label>'
        f'<label>Time (optional)<input name="time" type="time" value="{_esc(time_)}"></label>'
        "</fieldset>"
        '<button type="submit">Find films</button></form>' + _FORM_JS
    )


def _supported_html() -> str:
    items = "".join(
        f"<li>{_esc(a.name)} ({_esc(a.iata)})</li>" for a in SUPPORTED_AIRLINES
    )
    return (
        '<section class="supported" id="supported"><h2>Supported airlines</h2>'
        f"<ul>{items}</ul></section>"
    )


def _supported_names() -> str:
    return ", ".join(f"{a.name} ({a.iata})" for a in SUPPORTED_AIRLINES)


def _render_page(
    body: str = "",
    *,
    airline: str = "",
    flight: str = "",
    from_: str = "",
    to: str = "",
    date: str = "",
    time_: str = "",
    show_form: bool = True,
) -> HTMLResponse:
    parts = [body]
    if show_form:
        parts.append(_form_html(airline, flight, from_, to, date, time_))
        parts.append(_supported_html())
    return HTMLResponse(_INDEX_HTML.format(body="\n".join(parts)))


@app.get("/", response_class=HTMLResponse)
async def index():
    return _render_page()


@app.post("/search", response_class=HTMLResponse)
async def search(
    airline: Annotated[str, Form()] = "",
    flight: Annotated[str, Form()] = "",
    from_: Annotated[str, Form(alias="from")] = "",
    to: Annotated[str, Form()] = "",
    date: Annotated[str, Form()] = "",
    time_: Annotated[str, Form(alias="time")] = "",
    mode: Annotated[str, Form()] = "",
):
    airline, flight, from_, to, date, time_ = (
        v.strip() for v in (airline, flight, from_, to, date, time_)
    )
    # The JS toggle hides the inactive group but still submits it; honour the mode.
    if mode == "route":
        flight = ""
    elif mode == "flight":
        from_ = to = ""

    def fail(msg: str) -> HTMLResponse:
        return _render_page(
            f'<p class="error">{_esc(msg)}</p>',
            airline=airline,
            flight=flight,
            from_=from_,
            to=to,
            date=date,
            time_=time_,
        )

    route_ok = len(from_) == 3 and len(to) == 3 and from_.isalpha() and to.isalpha()
    if not flight and not route_ok:
        return fail(
            "Enter a flight number, or both a departure and arrival airport "
            "(3-letter IATA codes)."
        )
    if not date:
        return fail("Please enter a departure date.")
    try:
        datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        return fail("Departure date must be in YYYY-MM-DD format.")

    chosen: Airline | None
    if flight:
        chosen = airline_for_flight(flight)
        if chosen is None:
            return fail(
                f'Sorry, we don\'t support the airline for flight "{flight}". '
                f"Supported airlines: {_supported_names()}."
            )
        what = flight.upper().replace(" ", "")
    else:
        chosen = get_airline(airline)
        if chosen is None:
            return fail(f"Please choose a supported airline: {_supported_names()}.")
        what = f"{from_.upper()} \u2192 {to.upper()}"
    when = f"{date} {time_}".strip()
    header = f"{chosen.name} \u00b7 {what} \u00b7 {when}"
    back = '<a class="back" href="/">Change flight</a>'

    def error_page(msg: str) -> HTMLResponse:
        return _render_page(
            f'<p class="error">{_esc(msg)}</p><p>{back}</p>', show_form=False
        )

    provider_name = os.environ.get("FTFT_RATING_PROVIDER", "omdb")
    omdb_key = os.environ.get("OMDB_API_KEY")
    if provider_name == "omdb" and not omdb_key:
        return error_page(
            "OMDB_API_KEY is not set. Set it in your environment and restart the server."
        )

    try:
        films = _get_catalog()
    except urllib.error.URLError as exc:
        return error_page(f"Could not fetch {chosen.name} catalog: {exc}")

    if not films:
        return error_page(
            f"{chosen.name} catalog is behind a holding page or empty. Try again later."
        )

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
                return error_page(
                    f"OMDb rejected API key (HTTP {exc.code}). Check OMDB_API_KEY."
                )
            result = None
        except (urllib.error.URLError, json.JSONDecodeError):
            result = None
        ranked.append(RankedFilm(catalog=film, rating=result))

    ranked.sort(key=lambda r: r.sort_key, reverse=True)

    cards = [
        f'<p class="info">{_esc(header)} · {len(ranked)} films {back}</p>'
        '<div class="grid">'
    ]
    for item in ranked:
        score = (
            item.rating.score if item.rating and item.rating.score is not None else None
        )
        if score is not None and score >= 7.0:
            badge_cls, badge_txt = "badge-good", f"{score:.1f}"
        elif score is not None:
            badge_cls, badge_txt = "badge-decent", f"{score:.1f}"
        else:
            badge_cls, badge_txt = "badge-unrated", "NR"

        safe_title = html_lib.escape(item.catalog.title)
        if item.catalog.poster_url:
            poster_html = f'<img src="{item.catalog.poster_url}" alt="{safe_title}" loading="lazy">'
        else:
            poster_html = '<div class="poster-placeholder">🎬</div>'

        year_html = (
            f'<div class="card-year">{item.catalog.year}</div>'
            if item.catalog.year
            else ""
        )

        if item.catalog.detail_url:
            tag_open = f'<a class="card" href="{item.catalog.detail_url}" target="_blank" rel="noopener">'
            tag_close = "</a>"
        else:
            tag_open = '<div class="card">'
            tag_close = "</div>"

        cards.append(
            f"{tag_open}"
            f'<div class="poster-wrap">'
            f"{poster_html}"
            f'<span class="badge {badge_cls}">{badge_txt}</span>'
            f"</div>"
            f'<div class="card-body">'
            f'<div class="card-title">{safe_title}</div>'
            f"{year_html}"
            f"</div>"
            f"{tag_close}"
        )
    cards.append("</div>")

    body = "\n".join(cards)
    return _render_page(body, show_form=False)


def _esc(s: str) -> str:
    """HTML-escape a string for use in attribute values."""
    return (
        s.replace("&", "&amp;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


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
