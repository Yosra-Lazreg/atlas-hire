from __future__ import annotations

import argparse
from pathlib import Path

from .connectors import refresh_config
from .pipeline import build
from .score import load_profile
from .validation import save_validation_report


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="atlashire", description="Build an explainable opportunity shortlist.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--snapshot", default="data/raw/opportunities_snapshot.csv")
    build_parser.add_argument("--profile", default="config/profile.example.yml")
    build_parser.add_argument("--output-dir", default="outputs")
    build_parser.add_argument("--db-path", default="outputs/atlashire.duckdb")
    build_parser.add_argument("--history-dir", default="data/history")
    build_parser.add_argument("--as-of", default=None, help="ISO date used for expiry classification.")

    refresh_parser = subparsers.add_parser("refresh")
    refresh_parser.add_argument("--config", default="config/sources.yml")
    refresh_parser.add_argument("--output-dir", default="data/raw/live")
    refresh_parser.add_argument("--observed-at", default=None)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("--snapshot", default="data/raw/opportunities_snapshot.csv")
    validate_parser.add_argument("--profile", default="config/profile.example.yml")
    validate_parser.add_argument("--benchmark", default="data/validation/benchmark.csv")
    validate_parser.add_argument("--as-of", default="2026-09-13")
    validate_parser.add_argument("--output", default="outputs/validation_report.json")

    args = parser.parse_args(argv)

    if args.command == "build":
        frame = build(
            snapshot_path=args.snapshot,
            profile_path=args.profile,
            output_dir=args.output_dir,
            db_path=args.db_path,
            as_of=args.as_of,
            history_dir=args.history_dir,
        )
        print(f"Built {len(frame)} scored opportunity records.")
        return

    if args.command == "refresh":
        report = refresh_config(args.config, args.output_dir, args.observed_at)
        path = Path(args.output_dir)
        path.mkdir(parents=True, exist_ok=True)
        report.to_csv(path / "source_health.csv", index=False)
        print(report.to_string(index=False))
        return

    if args.command == "validate":
        # Validate the benchmark against a fresh score output without requiring DuckDB.
        from .normalize import normalize_snapshot
        from .score import score_opportunities
        raw = normalize_snapshot(args.snapshot, as_of=args.as_of)
        scored = score_opportunities(raw, load_profile(args.profile))
        report = save_validation_report(scored, args.benchmark, args.output)
        print(report)
        return

    raise RuntimeError("Unknown command")


if __name__ == "__main__":
    main()
