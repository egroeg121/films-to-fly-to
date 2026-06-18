"""Tests for ratings module and CLI score formatting — no network calls."""

from films_to_fly_to.cli import _format_scores
from films_to_fly_to.ratings import RatingResult, _pick_rt_score, _pick_score, _safe_int


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


def test_pick_rt_score_present():
    payload = {
        "imdbRating": "7.8",
        "Ratings": [
            {"Source": "Internet Movie Database", "Value": "7.8/10"},
            {"Source": "Rotten Tomatoes", "Value": "85%"},
        ],
    }
    assert _pick_rt_score(payload) == 85


def test_pick_rt_score_missing():
    payload = {"imdbRating": "7.8", "Ratings": []}
    assert _pick_rt_score(payload) is None


def test_pick_rt_score_na():
    payload = {"imdbRating": "7.8", "Ratings": [{"Source": "Rotten Tomatoes", "Value": "N/A%"}]}
    assert _pick_rt_score(payload) is None


def test_safe_int_normal():
    assert _safe_int("2024") == 2024


def test_safe_int_range():
    assert _safe_int("2020-2024") == 2020


def test_safe_int_invalid():
    assert _safe_int("N/A") is None


def test_safe_int_non_string():
    assert _safe_int(2024) is None


def _make_result(**kwargs) -> RatingResult:
    defaults = dict(source="omdb", external_id="tt123", title="Test", year=2024, score=None, rt_score=None)
    return RatingResult(**{**defaults, **kwargs})


def test_format_scores_both():
    r = _make_result(score=7.4, rt_score=85)
    assert _format_scores(r) == "IMDb 7.4 | RT 85%"


def test_format_scores_imdb_only():
    r = _make_result(score=6.5, rt_score=None)
    assert _format_scores(r) == "IMDb 6.5"


def test_format_scores_rt_only():
    r = _make_result(score=None, rt_score=72)
    assert _format_scores(r) == "RT 72%"


def test_format_scores_none_rating():
    assert _format_scores(None) == "unrated"


def test_format_scores_no_scores():
    r = _make_result(score=None, rt_score=None)
    assert _format_scores(r) == "unrated"
