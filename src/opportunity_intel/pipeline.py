from __future__ import annotations

from datetime import date
import json
from pathlib import Path

import pandas as pd

from .normalize import normalize_snapshot
from .score import load_profile, score_opportunities


def _write_warehouse(frame: pd.DataFrame, path: Path) -> None:
    try:
        import duckdb
    except ImportError as exc:
        raise RuntimeError("DuckDB is required for warehouse output. Install with `pip install -e .`.") from exc
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(str(path))
    connection.register("scored_frame", frame)
    connection.execute("create or replace table opportunities as select * from scored_frame")
    connection.execute("""
        create or replace view priority_opportunities as
        select * from opportunities
        where status <> 'expired'
          and recommendation in ('Priority', 'Check eligibility')
    """)
    connection.close()


def _write_skill_gaps(frame: pd.DataFrame, path: Path) -> None:
    counts: dict[str, int] = {}
    active = frame[frame["status"] != "expired"]
    for value in active["missing_skills"].fillna(""):
        for skill in str(value).split("|"):
            if skill:
                counts[skill] = counts.get(skill, 0) + 1
    pd.DataFrame(sorted(counts.items(), key=lambda item: (-item[1], item[0])), columns=["skill", "opportunity_count"]).to_csv(path, index=False)


def _history_summary(scored: pd.DataFrame, as_of_date: date, history_dir: Path) -> None:
    history_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = history_dir / f"scored_{as_of_date.isoformat()}.csv"
    scored.to_csv(snapshot_path, index=False)

    summary = {
        "as_of": as_of_date.isoformat(),
        "records": int(len(scored)),
        "active_records": int((scored["status"] == "active").sum()),
        "program_records": int((scored["status"] == "program").sum()),
        "expired_records": int((scored["status"] == "expired").sum()),
        "priority_records": int((scored["recommendation"] == "Priority").sum()),
        "avg_final_score": round(float(scored["final_score"].mean()), 2) if len(scored) else 0.0,
    }
    (history_dir / f"summary_{as_of_date.isoformat()}.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")


def build(
    snapshot_path: str | Path,
    profile_path: str | Path,
    output_dir: str | Path = "outputs",
    db_path: str | Path = "outputs/atlashire.duckdb",
    as_of: str | date | None = None,
    history_dir: str | Path = "data/history",
) -> pd.DataFrame:
    as_of_date = date.today() if as_of is None else as_of if isinstance(as_of, date) else date.fromisoformat(str(as_of))

    raw = normalize_snapshot(snapshot_path, as_of=as_of_date)
    profile = load_profile(profile_path)
    scored = score_opportunities(raw, profile)

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    scored_path = Path("data/processed/opportunities_scored.csv")
    scored_path.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(scored_path, index=False)

    scored[scored["recommendation"].isin(["Priority", "Check eligibility", "Stretch"])].to_csv(output_dir / "priority_shortlist.csv", index=False)
    _write_skill_gaps(scored, output_dir / "skill_gaps.csv")

    source_summary = scored.groupby(["source_name", "status"], dropna=False).size().reset_index(name="records").sort_values(["source_name", "status"])
    source_summary.to_csv(output_dir / "source_summary.csv", index=False)

    confidence_summary = scored.groupby("recommendation", dropna=False)["confidence_score"].agg(["count", "mean"]).reset_index()
    confidence_summary.to_csv(output_dir / "confidence_summary.csv", index=False)

    summary = {
        "as_of": as_of_date.isoformat(),
        "records": int(len(scored)),
        "active_records": int((scored["status"] == "active").sum()),
        "program_records": int((scored["status"] == "program").sum()),
        "expired_records": int((scored["status"] == "expired").sum()),
        "priority_records": int((scored["recommendation"] == "Priority").sum()),
        "check_eligibility_records": int((scored["recommendation"] == "Check eligibility").sum()),
        "avg_final_score": round(float(scored["final_score"].mean()), 2) if len(scored) else 0.0,
        "avg_confidence": round(float(scored["confidence_score"].mean()), 2) if len(scored) else 0.0,
        "top_companies": {str(key): int(value) for key, value in scored["company"].value_counts().head(10).items()},
    }
    (output_dir / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    _history_summary(scored, as_of_date, Path(history_dir))
    _write_warehouse(scored, Path(db_path))
    return scored
