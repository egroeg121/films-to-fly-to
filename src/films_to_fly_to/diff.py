"""Diff two catalog snapshots to detect churn (ftft-are).

Usage::

    from films_to_fly_to.diff import diff_snapshots
    result = diff_snapshots(films_a, films_b)
    print(result.summary())
"""

from __future__ import annotations

from dataclasses import dataclass

from films_to_fly_to.catalog import CatalogFilm


@dataclass
class CatalogDiff:
    added: list[CatalogFilm]    # in *b* but not *a*
    removed: list[CatalogFilm]  # in *a* but not *b*
    unchanged: list[CatalogFilm]

    @property
    def has_churn(self) -> bool:
        return bool(self.added or self.removed)

    def summary(self, label_a: str = "before", label_b: str = "after") -> str:
        lines = [
            f"Catalog diff ({label_a} → {label_b}):",
            f"  {len(self.added):3d} added    {len(self.removed):3d} removed    {len(self.unchanged):3d} unchanged",
        ]
        if self.added:
            lines.append("  Added:")
            for f in sorted(self.added, key=lambda x: x.title):
                year = f" ({f.year})" if f.year else ""
                lines.append(f"    + {f.title}{year}")
        if self.removed:
            lines.append("  Removed:")
            for f in sorted(self.removed, key=lambda x: x.title):
                year = f" ({f.year})" if f.year else ""
                lines.append(f"    - {f.title}{year}")
        return "\n".join(lines)


def diff_snapshots(
    a: list[CatalogFilm],
    b: list[CatalogFilm],
) -> CatalogDiff:
    """Compare two film lists by normalised title.

    Comparison is case-insensitive and strips extra whitespace so minor
    formatting differences do not register as churn.
    """
    def key(f: CatalogFilm) -> str:
        return f.title.strip().casefold()

    a_by_key = {key(f): f for f in a}
    b_by_key = {key(f): f for f in b}

    a_keys = set(a_by_key)
    b_keys = set(b_by_key)

    added = [b_by_key[k] for k in sorted(b_keys - a_keys)]
    removed = [a_by_key[k] for k in sorted(a_keys - b_keys)]
    unchanged = [a_by_key[k] for k in sorted(a_keys & b_keys)]

    return CatalogDiff(added=added, removed=removed, unchanged=unchanged)
