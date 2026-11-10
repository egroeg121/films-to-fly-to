"""Registry of airlines whose in-flight film catalogs we can fetch.

Single source of truth for the landing page's "supported airlines" list and for
resolving a flight number (e.g. ``BA286``) to an airline. Add an airline here
once it has a working catalog fetcher.

Catalogs are fleet-wide per month (see docs/research/ba-ife-aircraft-segmentation.md),
so a flight's route/time does not change which films are shown — only the airline does.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Airline:
    iata: str  # two-character IATA designator, e.g. "BA"
    name: str
    catalog_url: str


SUPPORTED_AIRLINES: tuple[Airline, ...] = (
    Airline(
        iata="BA",
        name="British Airways",
        catalog_url="https://entertainment.ba.com/en/movies",
    ),
)

_FLIGHT_RE = re.compile(r"^\s*([A-Z0-9]{2})\s*(\d{1,4})[A-Z]?\s*$", re.IGNORECASE)


def get_airline(iata: str) -> Airline | None:
    """Return the supported airline with this IATA code (case-insensitive), or None."""
    code = iata.strip().upper()
    return next((a for a in SUPPORTED_AIRLINES if a.iata == code), None)


def airline_for_flight(flight: str) -> Airline | None:
    """Resolve a flight number like ``BA286`` / ``ba 286`` to a supported airline, or None."""
    m = _FLIGHT_RE.match(flight)
    return get_airline(m.group(1)) if m else None
