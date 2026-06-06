# Decision: Rating data source for MVP

Status: Accepted (2026-06-06)
Issue: ftft-0qw

## Decision

Use **OMDb** (omdbapi.com) as the rating source for the MVP, with a thin adapter
interface so we can add TMDb or other sources later without changing the caller.

## Why OMDb

The MVP needs a single API call per film that returns a usable score and a stable
identifier we can cache against. OMDb gives both in one round-trip:

- **One call, multiple scores**: IMDb rating and Rotten Tomatoes critic score are
  in the same response payload. The user's brief named "RT or Letterboxd"; OMDb
  delivers RT directly.
- **IMDb ID as the join key**: every successful lookup returns `imdbID`, which
  is the canonical identifier the rest of the pipeline (catalog dedupe, title
  matching — see ftft-5yo) can pivot on. TMDb forces a second call to retrieve
  the IMDb ID.
- **Free tier is enough for the MVP**: 1,000 requests/day, no credit card. A BA
  long-haul catalog is roughly 200–400 films; one flight's worth of lookups fits
  comfortably, and the resolved-ID cache (ftft-5yo) means we only pay the lookup
  cost the first time we see a title.
- **Title + year query works**: OMDb accepts `?t=<title>&y=<year>`, which matches
  the normalisation strategy already planned in ftft-5yo.

## What we give up

- **Letterboxd** has no public API. Scraping film pages would be brittle (HTML
  changes, rate-limiting, ToS exposure) and was rejected as MVP-unsuitable.
- **TMDb** has a more generous free tier and a nicer API, but only ships its own
  audience score — not RT, not IMDb. If we later want TMDb's metadata (posters,
  cast) we can add it as a second adapter; the rating-for-ranking remit is better
  served by OMDb today.
- **OMDb is third-party reseller-style data** — if it ever goes dark we need a
  fallback. The adapter shape below makes that swap a few hundred lines, not a
  rewrite.

## Adapter shape

```python
class RatingSource(Protocol):
    def lookup(self, title: str, year: int | None) -> RatingResult | None: ...

@dataclass
class RatingResult:
    source: str            # "omdb"
    external_id: str       # IMDb ID, e.g. "tt1630029"
    title: str             # canonical title from the source
    year: int | None
    score: float | None    # normalised 0–10
    score_raw: dict        # original payload fields for debugging
```

Callers depend on `RatingSource`, not on OMDb. A `TmdbRatingSource` or a cached
`CompositeRatingSource` slot in without touching the ranker.

## Score normalisation

OMDb returns several score formats (IMDb is "8.4", RT is "92%", Metacritic is
"78"). For the MVP we rank by the IMDb rating (already 0–10, widest title
coverage). If IMDb is missing we fall back to RT/100 \* 10. Both decisions live
in the adapter so the ranker only sees `score: float | None`.

## Signup / key steps

1. Visit https://www.omdbapi.com/apikey.aspx
2. Pick the **FREE (1,000 daily limit)** plan
3. Enter an email; OMDb mails a verification link
4. Click the link; the key becomes active
5. Set the key locally:
   ```bash
   export OMDB_API_KEY=<your-key>
   ```
   And in the project, prefer a `.env` file loaded via `python-dotenv` — never
   commit the key.

## Prototype

See `prototypes/rating_source/omdb_lookup.py`. Run it with:

```bash
export OMDB_API_KEY=<your-key>
python prototypes/rating_source/omdb_lookup.py "The Substance" --year 2024
```

It exercises the adapter shape end-to-end against the live API.

## Follow-ups (filed as separate beads, not done here)

- Persistent cache for resolved `(title, year) -> imdbID` lookups (touches
  ftft-5yo).
- Decide what to do when OMDb has no record (skip vs. surface as unrated).
- Rate-limit / retry policy when we move beyond the prototype.
