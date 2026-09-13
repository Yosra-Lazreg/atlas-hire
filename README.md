# AtlasHire

## Opportunity intelligence for Algerian data students

AtlasHire is an end-to-end analytics project that converts public career metadata into an explainable shortlist of data jobs, internships, and early-career programs.

It is designed for students targeting:

- Data Analyst
- Business Intelligence Analyst
- Business Analyst
- Product Analyst
- Data Analytics Intern
- Junior Data Engineer
- Data Science Intern

This is a decision-support product, not an automatic application bot.

## What this repository demonstrates

- Public-source data ingestion
- Data cleaning and normalization
- Skill alias resolution
- Opportunity deduplication
- Transparent candidate-fit scoring
- Eligibility and experience-gap flags
- DuckDB analytical warehouse
- SQL business analysis
- Interactive Streamlit dashboard
- Automated tests
- GitHub Actions CI
- Data provenance and responsible-use documentation

## Snapshot

The checked-in snapshot is metadata-only and was observed on September 13, 2026.

It does not contain applicant information, CVs, private recruiter data, or automated application functionality. Always verify the original source before applying.

## Architecture

```text
Public career pages / job boards
              |
              v
     Raw opportunity snapshot
              |
              v
   Normalize titles, locations, skills
              |
              v
       Explainable fit scoring
          /          \
         v            v
     DuckDB         CSV outputs
         |
         v
 Streamlit dashboard + SQL analysis
```

## Scoring model

| Component | Weight |
|---|---:|
| Role alignment | 30% |
| Skill overlap | 35% |
| Seniority / experience fit | 15% |
| Location / work mode | 12% |
| Opportunity type | 8% |

Status factors:

- `active`: 1.00
- `program`: 0.95
- `catalog`: 0.65
- `expired`: 0.00

The dashboard explains each recommendation with matched skills, missing skills, experience fit, eligibility flags, and source links.

## Quickstart

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
```

Install:

```bash
python -m pip install -e ".[dev]"
```

Build the snapshot:

```bash
atlashire build --as-of 2026-09-13
```

Run tests:

```bash
pytest -q
```

Run the dashboard:

```bash
streamlit run app/streamlit_app.py
```

## Personalize

Edit:

```text
config/profile.example.yml
```

Replace the example profile values with your real skills and proficiency levels.

Do not claim skills you cannot defend in an interview.

## Refreshing public Lever data

The optional refresh command reads a public Lever endpoint:

```bash
atlashire refresh --lever-site Yassir
```

It only reads public postings and does not submit applications.

## Generated outputs

After a build:

```text
data/processed/opportunities_scored.csv
outputs/priority_shortlist.csv
outputs/skill_gaps.csv
outputs/source_summary.csv
outputs/summary.json
outputs/atlashire.duckdb
```

## Responsible data use

- Prefer official public sources.
- Respect source terms of service and robots policies.
- Do not collect applicant information.
- Do not automate applications.
- Keep career programs separate from confirmed vacancies.
- Keep observation dates and source URLs.
- Verify every opportunity before applying.
- Treat the score as a prioritization aid, not a hiring decision.


## Version 0.2 upgrades

AtlasHire now adds three layers that make the project closer to a deployable analytics product:

### Stronger live-source coverage

The refresh command supports public **Lever** and **Ashby Job Postings** feeds defined in `config/sources.yml`. Lever documents a public postings API that returns published jobs, while Ashby's public Job Postings API exposes currently published job postings for a public job board.

```bash
atlashire refresh
```

The command writes source-level row counts, latency, status, and errors to `data/raw/live/source_health.csv`.

### Historical analysis

Every successful build archives a scored snapshot under `data/history/scored_YYYY-MM-DD.csv` and a compact summary JSON. The dashboard and `notebooks/02_historical_trends.py` use those archives to track opportunity volume and average score over time. No historical rows are fabricated; history appears as real refreshes accumulate.

### Hybrid recommendation + validation

The ranking now separates:

- **Fit**: role, skills, seniority, location, opportunity type
- **Evidence confidence**: source completeness and source quality
- **Final score**: 88% fit + 12% confidence
- **Eligibility risk**: explicit blockers remain visible

The repository also includes a benchmark label file and `atlashire validate`, which reports category accuracy, priority precision/recall/F1, and data-quality invariants.

## Recommended workflow

```bash
atlashire refresh
atlashire build --as-of 2026-09-13
atlashire validate
streamlit run app/streamlit_app.py
```


### Public source coverage

The configured live layer includes one Lever source (Yassir) and four Ashby public job boards (Weaviate, Hire Hangar, E Source, and Super.com), plus manual official career-page sources for Algeria-focused monitoring. The refresh command produces a merged `data/raw/live/combined.csv` and a source-health report.

The Lever postings API exposes published job postings, and Ashby's public Job Postings API exposes currently published postings for a public job board.

### Validation interpretation

The benchmark is a small policy/QA benchmark, not a hiring-outcome dataset. A perfect benchmark result means the recommendation policy behaves consistently on the curated examples; it does **not** mean the score predicts hiring success.
