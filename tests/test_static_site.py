"""Tests for the static site builder."""

import json

import pytest
from films_to_fly_to.airlines import SUPPORTED_AIRLINES
from films_to_fly_to.catalog import CatalogFilm
from films_to_fly_to.cli import RankedFilm
from films_to_fly_to.ratings import RatingResult
from films_to_fly_to.static_site import build_site, main, rank_films

from films_to_fly_to import static_site

KEY = "SECRETKEY123"


def _film(title, year=2020):
    return CatalogFilm(title, year, ["Drama"], "15", "https://x/p.jpg", "https://x/d")


class FakeSource:
    def lookup(self, title, year):
        if title == "Unknown":
            return None
        return RatingResult(
            "omdb",
            "tt1",
            title,
            year,
            8.0 if title == "Good" else 6.0,
            score_raw={"apikey": KEY},
        )


def test_rank_orders_by_score_unrated_last():
    ranked = rank_films(
        [_film("Unknown"), _film("Meh"), _film("Good")], FakeSource(), delay=0
    )
    assert [r.catalog.title for r in ranked] == ["Good", "Meh", "Unknown"]


def test_build_writes_files_without_secret(tmp_path):
    ranked = rank_films([_film("Good"), _film("Unknown")], FakeSource(), delay=0)
    build_site(ranked, tmp_path, secrets=(KEY,))
    data = json.loads((tmp_path / "films.json").read_text())
    assert [f["title"] for f in data["films"]] == ["Good", "Unknown"]
    assert data["films"][1]["score"] is None
    for f in tmp_path.iterdir():
        assert KEY not in f.read_text()
    assert "Good" in (tmp_path / "films.html").read_text()


def test_build_aborts_if_key_leaks(tmp_path):
    ranked = [RankedFilm(_film(KEY), None)]
    with pytest.raises(RuntimeError):
        build_site(ranked, tmp_path, secrets=(KEY,))


def test_html_script_close_escaped(tmp_path):
    build_site([RankedFilm(_film("</script><b>"), None)], tmp_path)
    assert "</script><b>" not in (tmp_path / "films.html").read_text()


def test_landing_page_has_form_and_airlines(tmp_path):
    build_site([RankedFilm(_film("Good"), None)], tmp_path)
    html = (tmp_path / "index.html").read_text()
    for field in ("airline", "flight", "from", "to", "date", "time"):
        assert f'name="{field}"' in html
    for a in SUPPORTED_AIRLINES:
        assert a.name in html
        assert f'value="{a.iata}"' in html
    assert "films.html?" in html
    assert "Good" not in html  # film data lives on films.html only


def test_films_page_has_grid_context_and_back_link(tmp_path):
    build_site([RankedFilm(_film("Good"), None)], tmp_path)
    html = (tmp_path / "films.html").read_text()
    assert 'id="grid"' in html and '"title": "Good"' in html
    assert 'href="index.html"' in html and "Change flight" in html
    assert "textContent" in html and "location.search" not in html.split("<script>")[0]


def test_secret_guard_covers_landing_page(tmp_path, monkeypatch):
    monkeypatch.setattr(static_site, "_LANDING_HTML", static_site._LANDING_HTML + KEY)
    with pytest.raises(RuntimeError):
        build_site([RankedFilm(_film("Good"), None)], tmp_path, secrets=(KEY,))


def test_main_requires_key(monkeypatch, tmp_path):
    monkeypatch.delenv("OMDB_API_KEY", raising=False)
    assert main(["--out", str(tmp_path)]) == 2


def test_title_links_home(tmp_path):
    build_site([], tmp_path)
    for name in ("index.html", "films.html"):
        assert '<a class="home" href="index.html">' in (tmp_path / name).read_text()
