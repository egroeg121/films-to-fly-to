"""Build a self-contained static site (site/index.html + site/films.json).

Usage:
    OMDB_API_KEY=<key> uv run build-static [--out DIR]

The OMDb key is read from the environment at build time only and is never
written to the output; the build aborts if it would appear in any output file.
Only a whitelist of fields is serialised (never ``score_raw``).
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
from datetime import UTC, datetime
from pathlib import Path

from films_to_fly_to.catalog import CatalogFilm, fetch_catalog
from films_to_fly_to.cli import RankedFilm
from films_to_fly_to.ratings import get_rating_provider


def film_to_dict(item: RankedFilm) -> dict:
    """Whitelisted, public-safe representation of a ranked film."""
    r = item.rating
    c = item.catalog
    return {
        "title": c.title,
        "year": c.year,
        "genres": list(c.genres),
        "age_rating": c.rating,
        "poster_url": c.poster_url,
        "detail_url": c.detail_url,
        "score": r.score if r else None,
        "imdb_score": r.imdb_score if r else None,
        "rt_score": (r.rt_percent if r and r.rt_percent is not None else (r.rt_score if r else None)),
        "metacritic": r.metacritic if r else None,
    }


def rank_films(films: list[CatalogFilm], source, *, delay: float = 0.15) -> list[RankedFilm]:
    ranked: list[RankedFilm] = []
    for i, film in enumerate(films):
        if i > 0 and delay:
            time.sleep(delay)
        try:
            result = source.lookup(film.title, film.year)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise
            result = None
        except (urllib.error.URLError, json.JSONDecodeError):
            result = None
        ranked.append(RankedFilm(catalog=film, rating=result))
    ranked.sort(key=lambda r: r.sort_key, reverse=True)
    return ranked


def build_site(ranked: list[RankedFilm], out_dir: Path, *, secrets: tuple[str, ...] = ()) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "films": [film_to_dict(r) for r in ranked],
    }
    films_json = json.dumps(payload, indent=1, ensure_ascii=False)
    # Embed the data too so the page also works when opened from file://.
    inline = films_json.replace("</", "<\\/")
    html = _INDEX_HTML.replace("/*__DATA__*/null", inline)
    for secret in secrets:
        if secret and (secret in films_json or secret in html):
            raise RuntimeError("refusing to write site: API key found in output")
    (out_dir / "films.json").write_text(films_json, encoding="utf-8")
    (out_dir / "index.html").write_text(html, encoding="utf-8")
    (out_dir / ".nojekyll").write_text("", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    out = Path("site")
    if argv[:1] == ["--out"] and len(argv) == 2:
        out = Path(argv[1])
    elif argv:
        print("usage: build-static [--out DIR]", file=sys.stderr)
        return 2

    key = os.environ.get("OMDB_API_KEY")
    if not key:
        print("error: set OMDB_API_KEY in the environment", file=sys.stderr)
        return 2

    try:
        films = fetch_catalog()
    except urllib.error.URLError as exc:
        print(f"error: could not fetch catalog: {exc}", file=sys.stderr)
        return 1
    if not films:
        print("error: BA catalog is behind a holding page or empty", file=sys.stderr)
        return 1
    print(f"{len(films)} films in catalog; fetching ratings...", file=sys.stderr)

    source = get_rating_provider("omdb", api_key=key)
    try:
        ranked = rank_films(films, source)
    except urllib.error.HTTPError as exc:
        print(f"error: OMDb rejected key (HTTP {exc.code})", file=sys.stderr)
        return 1

    build_site(ranked, out, secrets=(key,))
    print(f"Wrote {out}/index.html and {out}/films.json ({len(ranked)} films)")
    return 0


_INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Films to Fly To</title>
<style>
  *, *::before, *::after { box-sizing: border-box; }
  body { font-family: system-ui, sans-serif; background: #0d1117; color: #e6edf3; margin: 0; padding: 1.5rem 1rem; }
  h1 { margin: 0 0 1rem; font-size: 1.6rem; letter-spacing: -0.02em; }
  .controls { display: flex; gap: 0.75rem; flex-wrap: wrap; margin-bottom: 0.75rem; }
  input, select { padding: 0.5rem 0.75rem; background: #161b22; border: 1px solid #30363d; border-radius: 6px; font-size: 1rem; color: #e6edf3; }
  .pills { display: flex; gap: 0.4rem; flex-wrap: wrap; margin-bottom: 1rem; }
  .pill { padding: 0.25rem 0.7rem; border: 1px solid #30363d; background: #161b22; color: #e6edf3; border-radius: 999px; cursor: pointer; font-size: 0.85rem; }
  .pill.active { background: #1f6feb; border-color: #1f6feb; }
  .info { color: #8b949e; font-size: 0.875rem; margin-bottom: 1rem; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 1.25rem; }
  .card { background: #161b22; border: 1px solid #30363d; border-radius: 8px; overflow: hidden; text-decoration: none; color: inherit; display: flex; flex-direction: column; }
  a.card:hover { border-color: #58a6ff; }
  .poster-wrap { position: relative; aspect-ratio: 2/3; background: #21262d; }
  .poster-wrap img { width: 100%; height: 100%; object-fit: cover; display: block; }
  .poster-placeholder { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; font-size: 2.5rem; }
  .badge { position: absolute; top: 6px; right: 6px; padding: 2px 7px; border-radius: 12px; font-size: 0.78rem; font-weight: 700; }
  .badge-good { background: #1a7f37; color: #fff; }
  .badge-decent { background: #9a6700; color: #fff; }
  .badge-unrated { background: #21262d; color: #8b949e; border: 1px solid #30363d; }
  .card-body { padding: 0.6rem 0.75rem 0.75rem; }
  .card-title { font-size: 0.85rem; font-weight: 600; line-height: 1.3; }
  .card-year { font-size: 0.78rem; color: #8b949e; }
</style>
</head>
<body>
<h1>Films to Fly To &#9992;&#65039;</h1>
<div class="controls">
  <input id="q" type="search" placeholder="Search title" aria-label="Search title">
  <select id="sort" aria-label="Sort">
    <option value="score">Sort: rating</option>
    <option value="title">Sort: title</option>
    <option value="year">Sort: year (newest)</option>
  </select>
  <select id="minscore" aria-label="Minimum rating">
    <option value="0">Any rating</option>
    <option value="6">6.0+</option>
    <option value="7">7.0+</option>
    <option value="8">8.0+</option>
  </select>
</div>
<div class="pills" id="genres"></div>
<div class="info" id="info"></div>
<div class="grid" id="grid"></div>
<script id="films-data" type="application/json">/*__DATA__*/null</script>
<script>
(function () {
  var state = { genres: new Set() }, films = [], grid = document.getElementById('grid');
  function el(tag, cls, text) { var e = document.createElement(tag); if (cls) e.className = cls; if (text != null) e.textContent = text; return e; }
  function safeUrl(u) { return typeof u === 'string' && /^https?:\\/\\//.test(u) ? u : null; }
  function card(f) {
    var link = safeUrl(f.detail_url);
    var c = link ? el('a', 'card') : el('div', 'card');
    if (link) { c.href = link; c.target = '_blank'; c.rel = 'noopener'; }
    var w = el('div', 'poster-wrap'), p = safeUrl(f.poster_url);
    if (p) { var i = el('img'); i.src = p; i.alt = f.title; i.loading = 'lazy'; w.appendChild(i); }
    else w.appendChild(el('div', 'poster-placeholder', '\\uD83C\\uDFAC'));
    var s = f.score;
    w.appendChild(el('span', 'badge ' + (s == null ? 'badge-unrated' : s >= 7 ? 'badge-good' : 'badge-decent'), s == null ? 'NR' : s.toFixed(1)));
    c.appendChild(w);
    var b = el('div', 'card-body'); b.appendChild(el('div', 'card-title', f.title));
    if (f.year) b.appendChild(el('div', 'card-year', String(f.year)));
    c.appendChild(b); return c;
  }
  function render() {
    var q = document.getElementById('q').value.trim().toLowerCase();
    var min = parseFloat(document.getElementById('minscore').value);
    var sort = document.getElementById('sort').value;
    var list = films.filter(function (f) {
      if (q && f.title.toLowerCase().indexOf(q) < 0) return false;
      if (min > 0 && !(f.score != null && f.score >= min)) return false;
      if (state.genres.size && !f.genres.some(function (g) { return state.genres.has(g); })) return false;
      return true;
    });
    list.sort(function (a, b) {
      if (sort === 'title') return a.title.localeCompare(b.title);
      if (sort === 'year') return (b.year || 0) - (a.year || 0);
      return (b.score == null ? -1 : b.score) - (a.score == null ? -1 : a.score);
    });
    grid.textContent = '';
    list.forEach(function (f) { grid.appendChild(card(f)); });
    document.getElementById('info').textContent = list.length + ' of ' + films.length + ' films' + (window.__gen ? ' \\u00B7 updated ' + window.__gen : '');
  }
  function init(data) {
    films = data.films; window.__gen = (data.generated_at || '').slice(0, 10);
    var gs = {}; films.forEach(function (f) { f.genres.forEach(function (g) { gs[g] = 1; }); });
    var box = document.getElementById('genres');
    Object.keys(gs).sort().forEach(function (g) {
      var p = el('button', 'pill', g); p.type = 'button';
      p.addEventListener('click', function () {
        if (state.genres.has(g)) { state.genres.delete(g); p.classList.remove('active'); } else { state.genres.add(g); p.classList.add('active'); }
        render();
      });
      box.appendChild(p);
    });
    ['q', 'sort', 'minscore'].forEach(function (id) { document.getElementById(id).addEventListener('input', render); });
    render();
  }
  var inline = JSON.parse(document.getElementById('films-data').textContent);
  if (inline) init(inline);
  else fetch('films.json').then(function (r) { return r.json(); }).then(init);
}());
</script>
</body>
</html>
"""


if __name__ == "__main__":
    raise SystemExit(main())
