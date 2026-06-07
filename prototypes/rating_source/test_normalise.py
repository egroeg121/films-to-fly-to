"""Unit tests for title normalisation — no API key required.

Run with:
    python prototypes/rating_source/test_normalise.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from title_matcher import normalise_title


def check(raw: str, expected_norm: str, expected_year: int | None) -> None:
    norm, year = normalise_title(raw)
    assert norm == expected_norm, f"{raw!r}: got norm={norm!r}, want {expected_norm!r}"
    assert year == expected_year, f"{raw!r}: got year={year}, want {expected_year}"
    print(f"  ok  {raw!r} -> ({norm!r}, {year})")


print("normalise_title tests")

# Basic case
check("The Substance", "the substance", None)

# Inline year extraction
check("The Substance (2024)", "the substance", 2024)

# All caps
check("THE SUBSTANCE", "the substance", None)

# Article suffix
check("Substance, The", "the substance", None)
check("Prestige, The (2006)", "the prestige", 2006)

# Italian 'Il' is not a recognised article suffix — stays as-is after strip
check("Maestro, Il", "maestro il", None)

# Leading 'A'
check("Beautiful Mind, A", "a beautiful mind", None)

# Punctuation
check("Top Gun: Maverick (2022)", "top gun maverick", 2022)
# Apostrophe becomes a space after punctuation strip — "don t" not "dont"
# OMDb's title search is tolerant of this
check("Don't Look Up", "don t look up", None)
# Asterisks become spaces — "m a s h"; OMDb still matches "MASH" via its own normalisation
check("M*A*S*H", "m a s h", None)

# Unicode normalisation (accented chars preserved but NFC-normalised)
check("Amélie", "amélie", None)
check("Nausicaä of the Valley of the Wind", "nausicaä of the valley of the wind", None)

# Sequel with year
check("Avatar: The Way of Water (2022)", "avatar the way of water", 2022)

# Whitespace collapse
check("  Dune   (2021) ", "dune", 2021)

# No year, no article, no punctuation
check("Oppenheimer", "oppenheimer", None)

print("\nAll tests passed.")
