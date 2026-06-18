"""CLI: measure OMDb rating hit rate against a sample of BA catalog films.

Usage:
    export OMDB_API_KEY=<your-key>
    uv run python -m films_to_fly_to.cli_hitrate              # live catalog fetch
    uv run python -m films_to_fly_to.cli_hitrate --limit 20   # first 20 films
    uv run python -m films_to_fly_to.cli_hitrate --verbose     # show per-film detail
    uv run python -m films_to_fly_to.cli_hitrate --cache-file /tmp/ftft.json

Exit codes:
    0  hit rate ≥ 80%
    1  hit rate < 80%
    2  configuration error (missing API key)
    3  catalog fetch failed
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from films_to_fly_to.catalog import fetch_catalog
from films_to_fly_to.ratings import OmdbRatingSource, TitleCache, TitleMatcher


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure OMDb rating hit rate for BA catalog.")
    parser.add_argument("--limit", type=int, default=None, help="Max number of films to test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print per-film result")
    parser.add_argument(
        "--cache-file",
        default=".ftft_title_cache.json",
        help="Path to JSON cache file (default: .ftft_title_cache.json)",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("OMDB_API_KEY")
    if not api_key:
        print("error: set OMDB_API_KEY in the environment", file=sys.stderr)
        return 2

    print("Fetching BA catalog...", flush=True)
    try:
        films = fetch_catalog()
    except Exception as exc:
        print(f"error: catalog fetch failed: {exc}", file=sys.stderr)
        return 3

    if not films:
        print("error: catalog returned empty (holding page?)", file=sys.stderr)
        return 3

    if args.limit:
        films = films[: args.limit]

    print(f"Testing {len(films)} films against OMDb...\n", flush=True)

    source = OmdbRatingSource(api_key)
    cache = TitleCache(Path(args.cache_file))
    matcher = TitleMatcher(source, cache)

    hits = 0
    misses = 0
    scored = 0
    retry_counts: Counter[str] = Counter()
    miss_list: list[str] = []

    for film in films:
        match = matcher.resolve(film.title, film.year)

        if match is None:
            misses += 1
            miss_list.append(f"  MISS  {film.title!r} ({film.year})")
            if args.verbose:
                print(f"MISS  {film.title!r} ({film.year})")
        else:
            hits += 1
            if match.result.score is not None:
                scored += 1
            reason = match.retry_reason or "direct"
            retry_counts[reason] += 1
            if args.verbose:
                flags = f"[{reason}{'  cache' if match.cache_hit else ''}]"
                print(
                    f"HIT   {film.title!r} ({film.year}) -> "
                    f"{match.result.title!r} ({match.result.year})  "
                    f"score={match.result.score}  {flags}"
                )

    total = hits + misses
    hit_pct = 100 * hits / total if total else 0.0
    scored_pct = 100 * scored / total if total else 0.0

    print()
    print(f"Results: {hits}/{total} hits ({hit_pct:.1f}%)  {scored}/{total} scored ({scored_pct:.1f}%)")

    if retry_counts:
        print("\nHit breakdown by retry path:")
        for reason, count in sorted(retry_counts.items(), key=lambda x: -x[1]):
            print(f"  {reason:20s}  {count}")

    if miss_list:
        print(f"\nMisses ({len(miss_list)}):")
        for line in miss_list:
            print(line)

    return 0 if hit_pct >= 80.0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
