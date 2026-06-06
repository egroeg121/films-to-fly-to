# British Airways in-flight catalog ingestion

Research note for `ftft-93c`. Goal: given a `(flight_number, date)` pair, return the
list of films available on that BA flight.

## TL;DR — recommended approach

1. **Primary**: scrape `entertainment.ba.com` (the public "High Life" catalog
   site) on a **monthly** schedule and store a snapshot per month.
2. **Flight → catalog mapping**: for an arbitrary `(flight_number, date)`, look
   up the **month-of-departure** snapshot. If we later discover the catalog
   varies by aircraft/cabin (see open questions), resolve aircraft type via a
   third-party flight-schedule API (FlightAware / Flightradar24 / AeroDataBox).
3. **Do not depend on the IAG developer "IFE" API.** It existed (`GET
   /rest-v1/v1/ife?when=YYYY-MM-DD&pagename=xml`, client-key header, XML only,
   500 calls/day, 4 rps, valid `when` = today..today+2 months) but the IAG
   developer portal now states "These APIs are no longer supported." The host
   `api.ba.com` still answers but returns 403 without a key, and BA's Mashery
   portal is no longer accepting new registrations as far as we can tell. Treat
   it as a **secondary lead** to revisit only if scraping proves unreliable.

## What we know about the source

### `entertainment.ba.com/en/movies`

- This is the **public-facing** "High Life Entertainment" catalog — same content
  passengers browse pre-flight or on board via Wi-Fi.
- During this investigation the site responded with a generic
  `"We are experiencing high demand on ba.com at the moment"` holding page,
  so we could not pull the live DOM. Any scraper must tolerate that holding
  page (back off + retry) and detect it as distinct from an empty catalog.
- Per BA's published statements ([BA Entertainment FAQ][faq],
  [High Life press release][press]), the catalogue **refreshes monthly**, with
  "some items updated daily or weekly". For our purposes a **monthly snapshot
  granularity** is the right unit of ingestion.

### IAG developer "IFE" API (legacy, mostly dead)

Documented at `developer.iairgroup.com/british_airways/apis/IFE`:

| Field          | Value                                                       |
| -------------- | ----------------------------------------------------------- |
| Endpoint       | `GET https://api.ba.com/rest-v1/v1/ife`                     |
| Auth           | Header `client-key: <mashery key>`                          |
| `when` param   | `YYYY-MM-DD`, range `today .. today + 2 months`             |
| `pagename`     | omit → HTML (first 10 titles only), `=xml` → full XML feed  |
| Rate limit     | 500 calls/day, 4 req/sec                                    |
| Response       | XML only (no JSON variant)                                  |
| Status         | Plans page says "These APIs are no longer supported"        |

Implications even if it came back:
- 2-month forward window — no way to retrieve historical catalogs, so we'd
  *still* need our own monthly snapshots.
- No documented field for aircraft type, route, or cabin in the response (the
  doc page never published a sample XML body), suggesting the catalog returned
  is the single "current month, fleet-wide" list.

### NDC / `developer.ba.com` (current BA developer surface)

- Focused on shopping/booking (Flight Offers, Service List, NDC Order
  management). **No in-flight entertainment endpoint.**
- Confirms there is no first-party replacement for the old IFE API.

## How catalogs vary

What BA publicly states ([BA Entertainment FAQ][faq]):

- "High Life Stream" (the BYOD-via-Wi-Fi flavour) is available on **A380**,
  **selected 787-9 with Thales + Wi-Fi**, and **777-200 with Thales**.
- Seat-back IFE is the default on long-haul; A320/A321 short-haul has no IFE
  (just the magazine).

So the catalog *content* appears to be **one shared monthly list across the
long-haul fleet** (the `entertainment.ba.com` site is not segmented by
aircraft), but **availability** of IFE at all depends on the aircraft type
serving the flight. Practically:

- Short-haul intra-Europe BA flights on A320-family → **no films**, regardless
  of catalog.
- Long-haul on 777/787/A380 → catalog-of-the-month applies.

This means we *do* need a `flight_number → aircraft_type` lookup, even if only
to decide whether a film catalog is offered at all.

## Flight → aircraft-type lookup

BA's own Flight Status API on the IAG portal is also part of the deprecated
Mashery set, so we should not rely on it. Viable alternatives:

| Source           | Notes                                                          |
| ---------------- | -------------------------------------------------------------- |
| FlightAware AeroAPI | Per-flight history incl. aircraft type. Paid, well documented. |
| Flightradar24    | Has the data on public pages but no official cheap API tier.   |
| AeroDataBox      | RapidAPI; cheap, has flight-by-number → aircraft.              |
| OAG Flight Info  | Authoritative schedules incl. equipment. Enterprise pricing.   |

Recommendation: **AeroDataBox** for the prototype (cheapest path to working
ingestion), revisit if volume grows.

## Proposed ingestion pipeline

```
                            ┌─────────────────────────┐
   monthly cron (1st)  ───▶ │ scrape_ba_catalog.py    │
                            │  - fetch /en/movies     │
                            │  - parse film cards     │
                            │  - tolerate holding pg  │
                            └────────────┬────────────┘
                                         │
                              ┌──────────▼──────────┐
                              │ catalogs/ba/YYYY-MM │  (snapshot table:
                              │   films.parquet     │   month, title, runtime,
                              └──────────┬──────────┘   genre, year, poster_url)
                                         │
   query: (flight_no, date)              │
                ┌────────────────────────┼────────────────────┐
                ▼                        ▼                    ▼
       AeroDataBox lookup       month = date[:7]      films = catalog[month]
       → aircraft type                                       │
                │                                            │
                ▼                                            │
       if aircraft ∈ {A380,777,787,...}  ──── yes ────▶ return films
       else (short-haul A320 etc.)         ──── return [] (no IFE)
```

## Open questions to settle next

1. **DOM structure of `entertainment.ba.com/en/movies`** when not in
   holding-page mode — needs a fetch from a non-rate-limited path, or
   `playwright` against a real browser to bypass the queue. File as follow-up
   bead before writing the scraper.
2. **Catalog-vs-aircraft segmentation** — does the site actually surface
   different lists per aircraft (e.g. A380 vs 787) via a query param or
   separate URL? Current evidence says no, but worth confirming once we can
   load the real page.
3. **Historical snapshots** — neither the website nor the (dead) IFE API
   exposes past months. Our archive only goes as far back as the date we start
   snapshotting. Make sure the first cron run lands before any downstream
   consumer needs historical data.
4. **Rate of change within a month** — BA say "some items updated
   daily/weekly". If that turns out to mean films get added/removed mid-month
   we may need weekly snapshots, not monthly. Detect by diffing the first few
   monthly snapshots day-over-day during a pilot.
5. **Mashery key revival** — confirm whether the IFE API is genuinely dead, or
   just hidden behind a registration wall we haven't asked for. Low priority
   given the 2-month forward limit makes it strictly worse than scraping.

## References

- BA Entertainment FAQ: <https://www.britishairways.com/content/information/entertainment/information-and-faqs> [faq]
- BA press release (catalog refresh / Thales / High Life Stream): <https://mediacentre.britishairways.com/pressrelease/details/17354> [press]
- IAG Developer Programs (BA index): <https://developer.iairgroup.com/british_airways>
- (Legacy) IFE API doc: <https://developer.iairgroup.com/british_airways/apis/IFE>
- NDC / current BA developer surface: <https://developer.ba.com/>
- AeroDataBox (candidate flight-info source): <https://aerodatabox.com/>

[faq]: https://www.britishairways.com/content/information/entertainment/information-and-faqs
[press]: https://mediacentre.britishairways.com/pressrelease/details/17354
