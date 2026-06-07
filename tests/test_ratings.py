"""Tests for ratings module — no network calls."""

from films_to_fly_to.ratings import _pick_score, _safe_int


def test_pick_score_imdb():
    payload = {"imdbRating": "7.8", "Ratings": [], "Metascore": "N/A"}
    assert _pick_score(payload) == 7.8


def test_pick_score_falls_back_to_rt():
    payload = {
        "imdbRating": "N/A",
        "Ratings": [
            {"Source": "Rotten Tomatoes", "Value": "92%"},
        ],
    }
    assert abs(_pick_score(payload) - 9.2) < 0.001


def test_pick_score_none_when_missing():
    payload = {"imdbRating": "N/A", "Ratings": []}
    assert _pick_score(payload) is None


def test_safe_int_normal():
    assert _safe_int("2024") == 2024


def test_safe_int_range():
    assert _safe_int("2020-2024") == 2020


def test_safe_int_invalid():
    assert _safe_int("N/A") is None


def test_safe_int_non_string():
    assert _safe_int(2024) is None
