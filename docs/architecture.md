# AtlasHire Engineering Architecture

AtlasHire is organized as a small analytics product rather than a single dashboard script.

## Data flow

`config/sources.yml` -> public source connectors -> `data/raw/live/` -> normalized snapshot -> scoring -> `data/processed/` + DuckDB + dashboard.

## Live adapters

The repository supports public Lever postings and Ashby's public Job Postings API. Each source has a configuration record, observation timestamp, row count, latency, and error state in `source_health.csv`.

## Historical layer

Each build archives a dated scored snapshot in `data/history/`. Trend analysis never invents historical records; it only visualizes snapshots that actually exist.

## Recommendation layer

The score is a hybrid of fit and evidence confidence. Fit covers role, skill, experience, location, and opportunity type. Evidence confidence covers field completeness and source quality. Eligibility blockers are surfaced separately.

## Validation layer

`data/validation/benchmark.csv` provides a small benchmark policy set. `atlashire validate` calculates category agreement, priority precision, priority recall, priority F1, and data-quality invariants. This is a QA benchmark, not a claim of predictive hiring accuracy.
