"""Tests for catalog HTML parser."""

from films_to_fly_to.catalog import _parse_catalog_html


SAMPLE_CARD = """
<div class="flex flex-col space-y-4 some-other-class">
  <a href="/en/content/avatar-fire-and-ash" class="some-link">
    <img src="https://c.entertainment.ba.com/poster/avatar.jpg" alt="poster" />
  </a>
  <span class="media-title-ellipsis">Avatar: Fire and Ash</span>
  <span data-testid="spec-line-year">2025</span>
  <span data-testid="spec-line-rating">PG</span>
  <span data-testid="spec-line-genre-0">Action</span>
  <span data-testid="spec-line-genre-1">Adventure</span>
</div>
<div class="flex flex-col space-y-4 some-other-class">
  <a href="/en/content/conclave" class="some-link">
    <img src="https://c.entertainment.ba.com/poster/conclave.jpg" alt="poster" />
  </a>
  <span class="media-title-ellipsis">Conclave</span>
  <span data-testid="spec-line-year">2024</span>
  <span data-testid="spec-line-rating">15</span>
  <span data-testid="spec-line-genre-0">Drama</span>
  <span data-testid="spec-line-genre-1">Thriller</span>
</div>
"""


def test_parse_two_films():
    films = _parse_catalog_html(SAMPLE_CARD)
    assert len(films) == 2

    avatar = films[0]
    assert avatar.title == "Avatar: Fire and Ash"
    assert avatar.year == 2025
    assert avatar.rating == "PG"
    assert "Action" in avatar.genres
    assert "Adventure" in avatar.genres
    assert avatar.detail_url == "https://entertainment.ba.com/en/content/avatar-fire-and-ash"

    conclave = films[1]
    assert conclave.title == "Conclave"
    assert conclave.year == 2024
    assert conclave.rating == "15"
    assert "Drama" in conclave.genres


def test_parse_deduplicates():
    doubled = SAMPLE_CARD + SAMPLE_CARD
    films = _parse_catalog_html(doubled)
    assert len(films) == 2


def test_parse_holding_page_returns_empty():
    from films_to_fly_to.catalog import HOLDING_PAGE_MARKER
    # The fetch_catalog function checks for the marker before parsing;
    # here we just verify _parse_catalog_html handles a page with no /en/content/ links
    films = _parse_catalog_html("<html><body>No films here</body></html>")
    assert films == []
