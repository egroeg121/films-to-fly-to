# 0003 — Snapshot cadence pilot (ftft-are)

**Status:** Pilot in progress  
**Issue:** ftft-are

## Context

`ftft-93c` concluded that a **monthly** snapshot of `entertainment.ba.com` is
sufficient, based on BA's published statement that the catalog "refreshes
monthly".  However BA also state "some items updated daily or weekly," which
leaves open the question of whether the catalog churns mid-month.

If films are added or removed between the 1st and last day of a month, a
monthly snapshot could be stale for several weeks, causing the film list shown
to users to be wrong.

## Decision

Run `catalog-snapshot` daily for one month and `catalog-diff` each successive
pair to measure actual churn rate.

| Outcome | Action |
|---------|--------|
| Zero mid-month churn | Keep monthly cadence (as per ftft-93c) |
| Meaningful mid-month churn (≥1 film added or removed) | Escalate to weekly snapshots |

"Meaningful" is intentionally low-bar: even one film change mid-month is worth
capturing, given users care about specific titles.

## Implementation

Two new CLI tools added in this bead:

```bash
# Save today's snapshot (FTFT_SNAPSHOT_DIR defaults to ./snapshots)
catalog-snapshot [--date YYYY-MM-DD] [--dir PATH]

# Diff two snapshots and print a churn report
# exit 0 = no churn, exit 1 = churn detected
catalog-diff snapshots/2026-06-01.jsonl snapshots/2026-06-02.jsonl
```

Snapshots are newline-delimited JSON (`.jsonl`), one record per film per line.
The format is human-readable and diff-friendly without external dependencies.

## How to run the pilot

```bash
# Run daily (e.g. via cron or launchd):
catalog-snapshot --dir snapshots/

# After two or more days have been collected:
for f in snapshots/*.jsonl; do echo "$f"; done | sort | \
  awk 'NR>1 { print prev, $0 } { prev=$0 }' | \
  while read a b; do catalog-diff "$a" "$b"; done
```

## Consequences

- Snapshot files are small (~10-50 KB each); 30 files ≈ 1 MB total.
- If the BA site is behind a holding page on a given day, an empty snapshot
  is saved with a warning.  Those days should be excluded from churn analysis.
- This pilot does not change the production query path; monthly snapshots from
  `ftft-93c` remain the current approach until pilot results are available.
