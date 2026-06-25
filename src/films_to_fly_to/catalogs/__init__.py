"""Airline catalog registry with flight-prefix dispatch."""

from __future__ import annotations

from typing import Callable

from films_to_fly_to.catalog import CatalogFilm, fetch_catalog as fetch_ba_catalog

AIRLINE_NAMES: dict[str, str] = {
    'BA': 'British Airways',
    'VS': 'Virgin Atlantic',
    'KL': 'KLM',
    'AA': 'American Airlines',
    'EK': 'Emirates',
    'SQ': 'Singapore Airlines',
}


def _not_implemented(prefix: str) -> Callable[[], list[CatalogFilm]]:
    def _fetcher() -> list[CatalogFilm]:
        raise NotImplementedError(f"{AIRLINE_NAMES.get(prefix, prefix)} catalog not yet implemented")
    return _fetcher


def fetch_virgin_catalog() -> list[CatalogFilm]:
    return _not_implemented('VS')()


def fetch_klm_catalog() -> list[CatalogFilm]:
    return _not_implemented('KL')()


def fetch_aa_catalog() -> list[CatalogFilm]:
    return _not_implemented('AA')()


def fetch_emirates_catalog() -> list[CatalogFilm]:
    return _not_implemented('EK')()


def fetch_singapore_catalog() -> list[CatalogFilm]:
    return _not_implemented('SQ')()


AIRLINE_CATALOG: dict[str, Callable[[], list[CatalogFilm]]] = {
    'BA': fetch_ba_catalog,
    'VS': fetch_virgin_catalog,
    'KL': fetch_klm_catalog,
    'AA': fetch_aa_catalog,
    'EK': fetch_emirates_catalog,
    'SQ': fetch_singapore_catalog,
}


def get_catalog_for_flight(flight: str) -> list[CatalogFilm]:
    """Return the film catalog for the airline identified by the flight prefix."""
    prefix = flight[:2].upper()
    fetcher = AIRLINE_CATALOG.get(prefix)
    if not fetcher:
        raise ValueError(f'Unsupported airline: {prefix}')
    return fetcher()


def airline_name_for_flight(flight: str) -> str:
    """Return the human-readable airline name for a flight prefix."""
    prefix = flight[:2].upper()
    return AIRLINE_NAMES.get(prefix, prefix)
