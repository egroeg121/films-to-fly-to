# Decision: Title-matching strategy — BA catalog titles → OMDb records

Status: Accepted (2026-06-07)
Issue: ftft-5yo

## Problem

BA catalog titles are messy: `'The Substance (2024)'`, `'THE SUBSTANCE'`, `'Substance, The'`
all refer to the same film. OMDb's title search is tolerant but not perfect — we need a
normalisation layer to maximise hit rates without burning API quota on failed lookups.

## Strategy (implemented in `prototypes/rating_source/title_matcher.py`)

### 1. Normalisation pipeline

Applied in this order to every raw BA title before any API call:

1. **Extract inline year**: `'Dune (2021)'` → title=`'Dune'`, year=2021
2. **NFC unicode normalise**: collapses accented-character variants
3. **Move trailing article**: `'Substance, The'` → `'The Substance'`
   - Recognised suffixes: `the, a, an, le, la, les, el, los, las, der, die, das, de, het, een`
4. **Lowercase**
5. **Strip punctuation** (replace with space)
6. **Collapse whitespace**

Result: `'The Substance (2024)'` → `('the substance', 2024)`

The normalised string is the cache key. Punctuation becoming spaces is intentional:
OMDb's own matching is robust to spacing (e.g. `'don t look up'` returns _Don't Look Up_).

### 2. Retry ladder

OMDb's `?t=<title>&y=<year>` picks the most popular match automatically (no candidate
list), so we don't need to disambiguate by director/runtime in the normal case. When a
lookup misses we escalate through:

| Step | Query | Reason |
|------|-------|--------|
| 1 | `title + exact year, type=movie` | Happy path |
| 2 | `title + year−1, type=movie` | Release slips (sequel announced for 2024, ships 2025) |
| 3 | `title + year+1, type=movie` | Same drift in the other direction |
| 4 | `title + no year, type=movie` | Year from BA catalog is wrong |
| 5 | `title + year, type=series` | BA includes TV content (mini-series, specials) |

Steps 2–3 only execute if a year was known; step 4 only executes if year was known (avoids
wasting a call on a truly unknown title with no year constraint on first try, which OMDb
handles fine already in step 1).

### 3. Cache

A JSON file maps `(normalised_title, year) → imdbID`. After a successful lookup the
`imdbID` is stored; subsequent calls for the same (title, year) hit the cache and fetch
by `/i=<id>` instead of `/t=<title>`, which is exact and doesn't burn a fuzzy-search slot.

Cache key design: `"the substance|2024"` (pipe-separated, `None` year becomes the string
`"None"` — unambiguous since no real year is the word None).

For the prototype the cache is a `.ftft_title_cache.json` file in the working directory.
Production should migrate this to a small SQLite table or a Parquet column alongside the
catalog snapshot.

### 4. Edge cases

| Case | Handling |
|------|----------|
| Foreign-language titles (`Amélie`, `La La Land`) | No special handling needed — OMDb accepts them; normaliser preserves non-ASCII after NFC |
| Titles with missing year | Inline-year extraction returns `None`; callers should supply year from the BA scrape row when available |
| Sequels with year drift | Steps 2–3 of retry ladder cover ±1 year |
| TV specials / mini-series | Step 5 retries as `type=series` |
| Short films | No special handling; OMDb covers most with `type=movie` |
| Director/runtime disambiguation | Not needed in the OMDb `?t=` path — it returns the most popular match, which is almost always correct for films in a mainstream BA catalog |

## What the caller receives

```python
@dataclass
class MatchResult:
    raw_title: str        # original BA title
    year_used: int | None # year actually sent to OMDb
    normalised: str       # cache key
    result: RatingResult  # score, imdbID, canonical title, year
    cache_hit: bool
    retry_reason: str | None  # None = hit on first try; else e.g. "year_drift(+1)"
```

`retry_reason` is useful for detecting systematic year-drift patterns in the BA catalog
so we can file a follow-up if a large fraction of titles need drift correction.

## Files

| Path | Purpose |
|------|---------|
| `prototypes/rating_source/title_matcher.py` | `normalise_title`, `TitleMatcher`, `TitleCache`, `OmdbRatingSource` with retry |
| `prototypes/rating_source/test_normalise.py` | 15 normalisation unit tests (no API key needed) |
| `prototypes/rating_source/omdb_lookup.py` | Earlier single-call prototype (superseded for production use) |

## Follow-ups (not done here)

- Persistent cache backed by SQLite alongside the BA catalog parquet snapshot.
- Decide what to do when no match survives all retry steps (skip film vs. surface as
  unrated in the ranked list). Filed separately.
- Rate-limit / retry policy for HTTP errors from OMDb (currently a raw `urlopen` —
  needs exponential backoff before production).
