"""Tests for ratings module and CLI score formatting — no network calls."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from films_to_fly_to.cli import _format_scores
from films_to_fly_to.ratings import (
    MatchResult,
    OmdbRatingSource,
    RatingResult,
    TitleCache,
    TitleMatcher,
    _pick_rt_score,
    _pick_score,
    _safe_int,
    normalise_title,
)


# ---------------------------------------------------------------------------
# _pick_score
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _safe_int
# ---------------------------------------------------------------------------


def test_safe_int_normal():
    assert _safe_int("2024") == 2024


def test_safe_int_range():
    assert _safe_int("2020-2024") == 2020


def test_safe_int_invalid():
    assert _safe_int("N/A") is None


def test_safe_int_non_string():
    assert _safe_int(2024) is None


# ---------------------------------------------------------------------------
# normalise_title
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "raw, expected_norm, expected_year",
    [
        ("The Substance", "the substance", None),
        ("The Substance (2024)", "the substance", 2024),
        ("THE SUBSTANCE", "the substance", None),
        ("Substance, The", "the substance", None),
        ("Prestige, The (2006)", "the prestige", 2006),
        ("Beautiful Mind, A", "a beautiful mind", None),
        ("Top Gun: Maverick (2022)", "top gun maverick", 2022),
        ("Don't Look Up", "don t look up", None),
        ("M*A*S*H", "m a s h", None),
        ("Amélie", "amélie", None),
        ("Avatar: The Way of Water (2022)", "avatar the way of water", 2022),
        ("  Dune   (2021) ", "dune", 2021),
        ("Oppenheimer", "oppenheimer", None),
    ],
)
def test_normalise_title(raw: str, expected_norm: str, expected_year: int | None) -> None:
    norm, year = normalise_title(raw)
    assert norm == expected_norm
    assert year == expected_year


# ---------------------------------------------------------------------------
# TitleMatcher — no network (mock OmdbRatingSource)
# ---------------------------------------------------------------------------


def _make_result(title: str = "Test Film", year: int = 2024, imdb_id: str = "tt1234567", **kwargs) -> RatingResult:
    return RatingResult(
        source="omdb",
        external_id=imdb_id,
        title=title,
        year=year,
        score=kwargs.get("score", 7.5),
        rt_score=kwargs.get("rt_score"),
        score_raw={"imdbRating": "7.5"},
    )


def _make_matcher(source: OmdbRatingSource, tmp_path) -> TitleMatcher:
    cache = TitleCache(tmp_path / "cache.json")
    return TitleMatcher(source, cache)


def test_matcher_happy_path(tmp_path):
    source = MagicMock(spec=OmdbRatingSource)
    source.lookup.return_value = _make_result()
    matcher = _make_matcher(source, tmp_path)

    match = matcher.resolve("The Substance (2024)")

    assert match is not None
    assert match.raw_title == "The Substance (2024)"
    assert match.normalised == "the substance"
    assert match.year_used == 2024
    assert match.retry_reason is None
    assert not match.cache_hit
    source.lookup.assert_called_once_with("the substance", 2024)


def test_matcher_year_drift_minus1(tmp_path):
    source = MagicMock(spec=OmdbRatingSource)
    # First call (exact year) misses, year-1 hits
    source.lookup.side_effect = [None, _make_result(year=2023)]
    matcher = _make_matcher(source, tmp_path)

    match = matcher.resolve("Oppenheimer (2024)")

    assert match is not None
    assert match.retry_reason == "year_drift(-1)"


def test_matcher_year_drift_plus1(tmp_path):
    source = MagicMock(spec=OmdbRatingSource)
    # exact miss, year-1 miss, year+1 hit
    source.lookup.side_effect = [None, None, _make_result(year=2025)]
    matcher = _make_matcher(source, tmp_path)

    match = matcher.resolve("Some Film (2024)")

    assert match is not None
    assert match.retry_reason == "year_drift(+1)"


def test_matcher_year_dropped_fallback(tmp_path):
    source = MagicMock(spec=OmdbRatingSource)
    # exact, year-1, year+1 all miss; no-year hit
    source.lookup.side_effect = [None, None, None, _make_result()]
    matcher = _make_matcher(source, tmp_path)

    match = matcher.resolve("Obscure Film (2024)")

    assert match is not None
    assert match.retry_reason == "year_dropped"


def test_matcher_series_fallback(tmp_path):
    source = MagicMock(spec=OmdbRatingSource)
    source.lookup.return_value = None  # all movie lookups fail
    source.lookup_series.return_value = _make_result(title="TV Special")
    matcher = _make_matcher(source, tmp_path)

    match = matcher.resolve("TV Special (2024)")

    assert match is not None
    assert match.retry_reason == "type=series"


def test_matcher_total_miss(tmp_path):
    source = MagicMock(spec=OmdbRatingSource)
    source.lookup.return_value = None
    source.lookup_series.return_value = None
    matcher = _make_matcher(source, tmp_path)

    assert matcher.resolve("Completely Unknown Film (2024)") is None


def test_matcher_cache_hit(tmp_path):
    source = MagicMock(spec=OmdbRatingSource)
    source.lookup.return_value = _make_result(imdb_id="tt9999999")
    source.fetch_by_id.return_value = _make_result(imdb_id="tt9999999")
    matcher = _make_matcher(source, tmp_path)

    # First call populates cache
    match1 = matcher.resolve("The Substance (2024)")
    assert match1 is not None
    assert not match1.cache_hit

    # Second call should hit cache
    match2 = matcher.resolve("The Substance (2024)")
    assert match2 is not None
    assert match2.cache_hit
    source.fetch_by_id.assert_called_once_with("tt9999999")


def test_matcher_no_year_skips_drift(tmp_path):
    """When no year is known, year-drift and year-dropped steps are skipped."""
    source = MagicMock(spec=OmdbRatingSource)
    source.lookup.return_value = None
    source.lookup_series.return_value = _make_result()
    matcher = _make_matcher(source, tmp_path)

    match = matcher.resolve("Some Film")  # no year at all

    assert match is not None
    assert match.retry_reason == "type=series"
    # Only one movie lookup (no drift calls), then one series lookup
    assert source.lookup.call_count == 1


# ---------------------------------------------------------------------------
# CLI score formatting
# ---------------------------------------------------------------------------


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
