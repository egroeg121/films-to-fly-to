"""Tests for snapshot persistence and catalog diff logic (ftft-are)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

import pytest

from films_to_fly_to.catalog import CatalogFilm
from films_to_fly_to.diff import CatalogDiff, diff_snapshots
from films_to_fly_to.snapshot import load_snapshot, save_snapshot, snapshot_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _film(title: str, year: int = 2024) -> CatalogFilm:
    return CatalogFilm(title=title, year=year, genres=["Drama"], rating="PG", poster_url=None, detail_url=None)


# ---------------------------------------------------------------------------
# snapshot round-trip
# ---------------------------------------------------------------------------

def test_save_and_load_snapshot(tmp_path: Path) -> None:
    films = [_film("Conclave"), _film("Avatar: Fire and Ash", 2025)]
    day = date(2026, 6, 1)
    path = save_snapshot(films, day, snapshot_dir=tmp_path)

    assert path == snapshot_path(tmp_path, day)
    assert path.exists()

    loaded = load_snapshot(path)
    assert len(loaded) == 2
    assert loaded[0].title == "Conclave"
    assert loaded[1].title == "Avatar: Fire and Ash"
    assert loaded[1].year == 2025


def test_snapshot_file_is_valid_jsonl(tmp_path: Path) -> None:
    films = [_film("The Brutalist")]
    save_snapshot(films, date(2026, 6, 1), snapshot_dir=tmp_path)
    path = tmp_path / "2026-06-01.jsonl"
    lines = [l for l in path.read_text().splitlines() if l.strip()]
    assert len(lines) == 1
    record = json.loads(lines[0])
    assert record["title"] == "The Brutalist"


def test_save_snapshot_creates_dir(tmp_path: Path) -> None:
    nested = tmp_path / "a" / "b"
    save_snapshot([_film("X")], date(2026, 6, 1), snapshot_dir=nested)
    assert (nested / "2026-06-01.jsonl").exists()


def test_load_empty_snapshot(tmp_path: Path) -> None:
    p = tmp_path / "2026-06-01.jsonl"
    p.write_text("")
    assert load_snapshot(p) == []


# ---------------------------------------------------------------------------
# diff logic
# ---------------------------------------------------------------------------

def test_diff_no_change() -> None:
    films = [_film("A"), _film("B")]
    result = diff_snapshots(films, films)
    assert not result.has_churn
    assert len(result.unchanged) == 2
    assert result.added == []
    assert result.removed == []


def test_diff_added_film() -> None:
    a = [_film("A"), _film("B")]
    b = [_film("A"), _film("B"), _film("C")]
    result = diff_snapshots(a, b)
    assert result.has_churn
    assert len(result.added) == 1
    assert result.added[0].title == "C"
    assert result.removed == []


def test_diff_removed_film() -> None:
    a = [_film("A"), _film("B"), _film("C")]
    b = [_film("A"), _film("C")]
    result = diff_snapshots(a, b)
    assert result.has_churn
    assert result.removed[0].title == "B"
    assert result.added == []


def test_diff_case_insensitive() -> None:
    a = [_film("Avatar: Fire and Ash")]
    b = [_film("AVATAR: FIRE AND ASH")]
    result = diff_snapshots(a, b)
    assert not result.has_churn


def test_diff_whitespace_insensitive() -> None:
    a = [_film("  Conclave  ")]
    b = [_film("Conclave")]
    result = diff_snapshots(a, b)
    assert not result.has_churn


def test_diff_summary_no_churn() -> None:
    films = [_film("A")]
    result = diff_snapshots(films, films)
    summary = result.summary()
    assert "0 added" in summary
    assert "0 removed" in summary


def test_diff_summary_with_churn() -> None:
    a = [_film("Old Film")]
    b = [_film("New Film")]
    result = diff_snapshots(a, b)
    summary = result.summary(label_a="day1", label_b="day2")
    assert "day1 → day2" in summary
    assert "+ New Film" in summary
    assert "- Old Film" in summary
