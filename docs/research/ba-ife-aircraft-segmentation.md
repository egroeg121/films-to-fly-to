# BA IFE catalog: aircraft-type segmentation confirmed absent

Research note for `ftft-pou`. Question: does `entertainment.ba.com` publish
separate film catalogs per aircraft type (A380 / 777 / 787), or is there one
fleet-wide list?

## Verdict: one fleet-wide catalog per month — no aircraft dimension

The catalog is not segmented by aircraft type at any level of the stack.

## Evidence

### 1. Single microsite, no per-aircraft variants

`GET /api/airline-config?microsite=british-airways` returns:

```json
{"group":"BAW","cycles":{"current":{"cycle":"2026-06","startDate":"2026-06-01","endDate":"2026-06-30","defaultLocale":"en_US","locales":["en_US"]},"next":null}}
```

One group code (`BAW`), one cycle, no fleet dimension.

Probing for per-aircraft microsites returns hard 400 errors:

```
GET /api/airline-config?microsite=british-airways-787  → 400 {"error":"Microsite not found: british-airways-787"}
GET /api/airline-config?microsite=british-airways-a380 → 400 {"error":"Microsite not found: british-airways-a380"}
GET /api/airline-config?microsite=british-airways-777  → 400 {"error":"Microsite not found: british-airways-777"}
```

### 2. Aircraft-path URLs redirect to homepage

```
GET /en/787/movies  → 302 Location: /en  (body: "/en")
GET /en/a380/movies → 302 Location: /en
GET /en/777/movies  → 302 Location: /en
```

The server treats `787` / `a380` / `777` as unknown locale prefixes and
redirects to the default locale root, not to aircraft-specific content.

### 3. Query-param filtering is silently ignored

```
GET /en/movies?aircraft=777  → 200, same full catalog page
GET /en/movies?fleet=A380    → 200, same full catalog page
```

The frontend (Next.js) ignores unknown query params; the catalog content
is identical regardless.

### 4. Item-detail schema has no aircraft/fleet field

Each film record looks like:

```json
{
  "id": "b9aebb9c-...",
  "type": "movie",
  "title": "Avatar: Fire and Ash",
  "group": "BAW",
  "providerCmsId": "BAM_2606_AvatarFireAndAsh",
  ...
}
```

The `group` is always `BAW` (British Airways). No `aircraft`, `fleet`,
`cabin`, or `route` field exists at any level of the item schema.

### 5. Asset CDN uses a single path

All poster/thumbnail assets resolve under:
`assets.microsites.anuvu-services.net/microsites/BAW/BAM/...`

`BAW` = airline, `BAM` = catalog module — single path, no per-fleet variants.

### 6. No UI controls for aircraft filtering

The `/en/movies` page has:
- Nav links: Movies, Series, Audio, Games, Kids — content-type only
- Zero `<select>`, `[role="listbox"]`, or `[role="combobox"]` elements
- No aircraft/fleet/cabin text anywhere in the rendered DOM or loaded scripts

## Implication for schema design

**The snapshot schema does NOT need an aircraft-type dimension.**

The correct model remains:

```
catalog_snapshot(cycle: YYYY-MM, title, runtime, genre, year, poster_url, ...)
```

One row per film per monthly cycle. Aircraft type is irrelevant to catalog
content — it only gates whether IFE is available on a given flight at all
(long-haul 777/787/A380 = yes; short-haul A320 = no), which is handled
upstream via the flight→aircraft lookup described in `ba-ingestion.md`.

## What this closes

Open question 2 from `ba-ingestion.md`:

> **Catalog-vs-aircraft segmentation** — does the site actually surface
> different lists per aircraft (e.g. A380 vs 787) via a query param or
> separate URL? Current evidence says no, but worth confirming once we can
> load the real page.

**Confirmed: no.** The site was accessible during this investigation (no
holding page). All probes returned consistent results.
