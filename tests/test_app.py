"""Tests for the FastAPI app (no network: catalog and ratings are stubbed)."""

import pytest
from fastapi.testclient import TestClient
from films_to_fly_to.airlines import SUPPORTED_AIRLINES
from films_to_fly_to.catalog import CatalogFilm
from films_to_fly_to.ratings import RatingResult

from films_to_fly_to import app as app_module


def _rating(title: str, year: int | None) -> RatingResult:
    score = 8.0 if title == "Good Film" else 5.0
    return RatingResult(
        source="omdb", external_id=None, title=title, year=year, score=score
    )


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("OMDB_API_KEY", "fake-key")
    monkeypatch.delenv("FTFT_RATING_PROVIDER", raising=False)
    films = [
        CatalogFilm("Meh Film", 2019, ["Comedy"], "PG", None, None),
        CatalogFilm("Good Film", 2020, ["Drama"], "15", None, None),
    ]
    monkeypatch.setattr(app_module, "_get_catalog", lambda: films)
    monkeypatch.setattr(app_module, "_rating_in_cache", lambda *a, **k: True)
    monkeypatch.setattr(
        app_module, "_get_rating", lambda source, title, year: _rating(title, year)
    )
    return TestClient(app_module.app)


def test_landing_page(client):
    html = client.get("/").text
    assert "Supported airlines" in html
    for a in SUPPORTED_AIRLINES:
        assert a.name in html and a.iata in html
    for field in ("airline", "flight", "from", "to", "date", "time"):
        assert f'name="{field}"' in html


def test_flight_search(client):
    r = client.post(
        "/search", data={"flight": "BA286", "date": "2026-11-12", "time": "09:40"}
    )
    assert r.status_code == 200
    assert "British Airways · BA286 · 2026-11-12 09:40" in r.text
    assert "Change flight" in r.text
    assert r.text.index("Good Film") < r.text.index("Meh Film")


def test_route_search(client):
    r = client.post(
        "/search",
        data={"airline": "BA", "from": "lhr", "to": "jfk", "date": "2026-11-12"},
    )
    assert "British Airways · LHR → JFK · 2026-11-12" in r.text
    assert "Good Film" in r.text


def test_unsupported_flight_prefix(client):
    r = client.post("/search", data={"flight": "XX123", "date": "2026-11-12"})
    assert 'class="error"' in r.text
    assert "British Airways (BA)" in r.text
    assert 'value="XX123"' in r.text and 'value="2026-11-12"' in r.text
    assert "Good Film" not in r.text


def test_missing_flight_and_route(client):
    r = client.post("/search", data={"date": "2026-11-12", "from": "LHR"})
    assert 'class="error"' in r.text
    assert 'value="LHR"' in r.text


def test_missing_date(client):
    r = client.post("/search", data={"flight": "BA286"})
    assert 'class="error"' in r.text


def test_input_escaped(client):
    r = client.post("/search", data={"flight": "<script>", "date": "2026-11-12"})
    assert "&lt;script&gt;" in r.text
    assert 'value="<script>"' not in r.text
