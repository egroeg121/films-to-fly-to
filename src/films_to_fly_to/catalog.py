"""Scrape the BA High Life entertainment catalog from entertainment.ba.com."""

from __future__ import annotations

import html
import re
import urllib.request
from dataclasses import dataclass


@dataclass
class CatalogFilm:
    title: str
    year: int | None
    genres: list[str]
    rating: str | None  # BA's own age-rating (e.g. "PG", "15") not score
    poster_url: str | None
    detail_url: str | None


CATALOG_URL = "https://entertainment.ba.com/en/movies"
HOLDING_PAGE_MARKER = "high demand"
_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def fetch_catalog(timeout: float = 30.0) -> list[CatalogFilm]:
    """Fetch and parse the current BA film catalog.

    Returns an empty list if the site is behind a holding page.
    Raises urllib.error.URLError on network failure.
    """
    req = urllib.request.Request(CATALOG_URL, headers={"User-Agent": _USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8", errors="replace")

    if HOLDING_PAGE_MARKER in body.lower():
        return []

    return _parse_catalog_html(body)


def _parse_catalog_html(html_text: str) -> list[CatalogFilm]:
    """Extract film cards from the catalog page HTML.

    Selectors identified in ftft-44o:
      Card container: div.flex.flex-col.space-y-4 containing a[href*='/en/content/']
      Title:          .media-title-ellipsis
      Year:           [data-testid=spec-line-year]
      Rating (age):   [data-testid=spec-line-rating]
      Genres:         [data-testid^=spec-line-genre-]
      Poster:         img src
      Detail link:    a[href*='/en/content/'] href
    """
    films: list[CatalogFilm] = []
    seen_titles: set[str] = set()

    # Split on card boundaries — each card has a link to /en/content/
    # We split the HTML by these anchor hrefs and parse each chunk
    card_pattern = re.compile(
        r'<a\s[^>]*href="(/en/content/[^"]+)"[^>]*>.*?</a>',
        re.DOTALL,
    )

    # Find all content links with their surrounding context
    # Strategy: find each film card block by locating the title element
    title_pattern = re.compile(
        r'class="[^"]*media-title-ellipsis[^"]*"[^>]*>([^<]+)<',
        re.IGNORECASE,
    )
    year_pattern = re.compile(
        r'data-testid="spec-line-year"[^>]*>([^<]+)<',
        re.IGNORECASE,
    )
    rating_pattern = re.compile(
        r'data-testid="spec-line-rating"[^>]*>([^<]+)<',
        re.IGNORECASE,
    )
    genre_pattern = re.compile(
        r'data-testid="spec-line-genre-[^"]*"[^>]*>([^<]+)<',
        re.IGNORECASE,
    )
    poster_pattern = re.compile(
        r'<img\s[^>]*src="(https://[^"]*entertainment\.ba\.com[^"]*\.(?:jpg|png|webp)[^"]*)"',
        re.IGNORECASE,
    )
    detail_link_pattern = re.compile(
        r'href="(/en/content/[^"]+)"',
        re.IGNORECASE,
    )

    # Split the page into card-sized chunks around each /en/content/ link
    # We split at every occurrence of the card container class
    card_split = re.compile(
        r'(?=<[^>]+class="[^"]*flex[^"]*flex-col[^"]*space-y-4[^"]*")',
        re.IGNORECASE,
    )
    chunks = card_split.split(html_text)

    for chunk in chunks:
        if "/en/content/" not in chunk:
            continue

        title_m = title_pattern.search(chunk)
        if not title_m:
            continue
        title = html.unescape(title_m.group(1).strip())
        if not title or title in seen_titles:
            continue
        seen_titles.add(title)

        year: int | None = None
        year_m = year_pattern.search(chunk)
        if year_m:
            try:
                year = int(year_m.group(1).strip())
            except ValueError:
                pass

        age_rating: str | None = None
        rating_m = rating_pattern.search(chunk)
        if rating_m:
            age_rating = html.unescape(rating_m.group(1).strip()) or None

        genres = [
            html.unescape(g.strip())
            for g in genre_pattern.findall(chunk)
            if g.strip()
        ]

        poster_url: str | None = None
        poster_m = poster_pattern.search(chunk)
        if poster_m:
            poster_url = poster_m.group(1)

        detail_url: str | None = None
        link_m = detail_link_pattern.search(chunk)
        if link_m:
            detail_url = "https://entertainment.ba.com" + link_m.group(1)

        films.append(
            CatalogFilm(
                title=title,
                year=year,
                genres=genres,
                rating=age_rating,
                poster_url=poster_url,
                detail_url=detail_url,
            )
        )

    return films
