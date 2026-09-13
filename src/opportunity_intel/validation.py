from __future__ import annotations

from pathlib import Path
import json

import pandas as pd

LABEL_ORDER = ["Priority", "Check eligibility", "Stretch", "Monitor", "Low-confidence monitor", "Archive"]


def validate_scored(scored: pd.DataFrame, benchmark_path: str | Path) -> dict:
    benchmark = pd.read_csv(benchmark_path, dtype=str)
    merged = benchmark.merge(scored[["opportunity_id", "recommendation", "final_score"]], on="opportunity_id", how="left")
    merged["expected_label"] = merged["expected_label"].fillna("Monitor")
    merged["prediction"] = merged["recommendation"].fillna("missing")

    exact = float((merged["expected_label"] == merged["prediction"]).mean()) if len(merged) else 0.0
    expected_priority = merged["expected_label"] == "Priority"
    predicted_priority = merged["prediction"] == "Priority"
    tp = int((expected_priority & predicted_priority).sum())
    fp = int((~expected_priority & predicted_priority).sum())
    fn = int((expected_priority & ~predicted_priority).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0

    issues = []
    expected_columns = {
        "opportunity_id", "fit_score", "confidence_score", "final_score",
        "status", "recommendation", "source_url", "apply_url",
    }
    missing_columns = sorted(expected_columns - set(scored.columns))
    if missing_columns:
        issues.append("missing_columns:" + ",".join(missing_columns))
    if scored["fit_score"].between(0, 100).eq(False).any():
        issues.append("fit_score_out_of_range")
    if scored["confidence_score"].between(0, 100).eq(False).any():
        issues.append("confidence_out_of_range")
    if scored["opportunity_id"].duplicated().any():
        issues.append("duplicate_opportunity_id")
    if not set(scored["status"].unique()).issubset({"active", "program", "catalog", "expired"}):
        issues.append("unknown_status")

    report = {
        "benchmark_rows": int(len(merged)),
        "exact_category_accuracy": round(exact, 3),
        "priority_precision": round(precision, 3),
        "priority_recall": round(recall, 3),
        "priority_f1": round(f1, 3),
        "data_quality_issues": issues,
        "passed": not issues and exact >= 0.60,
    }
    return report


def save_validation_report(scored: pd.DataFrame, benchmark_path: str | Path, output_path: str | Path) -> dict:
    report = validate_scored(scored, benchmark_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report
