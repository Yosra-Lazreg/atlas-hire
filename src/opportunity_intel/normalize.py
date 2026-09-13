from __future__ import annotations

from datetime import date
from hashlib import sha1
import re
from pathlib import Path

import pandas as pd

ALIASES = {
    "powerbi": "power bi",
    "power bi": "power bi",
    "power-bi": "power bi",
    "google data studio": "looker",
    "looker studio": "looker",
    "structured query language": "sql",
    "microsoft excel": "excel",
    "statistical analysis": "statistics",
    "data visualisation": "data visualization",
    "ml": "machine learning",
    "google cloud": "gcp",
    "pyspark": "spark",
}

REQUIRED_COLUMNS = (
    "opportunity_id", "company", "title", "opportunity_type", "work_mode",
    "location", "country", "seniority", "experience_min_years",
    "experience_max_years", "skills", "languages", "posted_date", "deadline",
    "availability", "source_kind", "source_name", "source_url", "apply_url",
    "eligibility", "notes", "observed_at",
)


def is_blank(value: object) -> bool:
    if value is None:
        return True
    try:
        if pd.isna(value):
            return True
    except (TypeError, ValueError):
        pass
    return str(value).strip().lower() in {"", "nan", "none", "nat"}


def clean_text(value: object) -> str:
    if is_blank(value):
        return ""
    return re.sub(r"\s+", " ", str(value).strip())


def canonical_skill(value: object) -> str:
    text = clean_text(value).lower()
    text = re.sub(r"[^a-z0-9+#.]+", " ", text).strip()
    return ALIASES.get(text, text)


def split_values(value: object) -> list[str]:
    if is_blank(value):
        return []
    return [item.strip() for item in re.split(r"[|,;]", str(value)) if item.strip()]


def normalize_skill_list(value: object) -> list[str]:
    skills = {canonical_skill(item) for item in split_values(value)}
    return sorted(skill for skill in skills if skill)


def _date_value(value: object) -> date | None:
    if is_blank(value):
        return None
    parsed = pd.to_datetime(value, errors="coerce")
    if pd.isna(parsed):
        return None
    return parsed.date()


def _date_text(value: object) -> str:
    parsed = _date_value(value)
    return parsed.isoformat() if parsed else ""


def _status(row: pd.Series, as_of: date) -> str:
    availability = clean_text(row.get("availability", "")).lower()
    deadline = _date_value(row.get("deadline", ""))

    if deadline and deadline < as_of:
        return "expired"
    if availability == "historical_snapshot":
        return "expired"
    if availability in {"catalog"}:
        return "catalog"
    if availability in {"career_program", "program"}:
        return "program"
    return "active"


def _record_key(row: pd.Series) -> str:
    raw = "|".join(
        clean_text(row.get(column, "")).lower()
        for column in ("company", "title", "location")
    )
    return sha1(raw.encode("utf-8")).hexdigest()[:12]


def normalize_snapshot(
    path: str | Path,
    as_of: str | date | None = None,
) -> pd.DataFrame:
    as_of_date = (
        date.today()
        if as_of is None
        else as_of
        if isinstance(as_of, date)
        else date.fromisoformat(str(as_of))
    )

    frame = pd.read_csv(path, dtype=str, keep_default_na=False)

    for column in REQUIRED_COLUMNS:
        if column not in frame.columns:
            frame[column] = ""

    for column in (
        "company", "title", "opportunity_type", "work_mode", "location",
        "seniority", "availability", "source_kind", "source_name",
        "source_url", "apply_url", "eligibility", "notes",
    ):
        frame[column] = frame[column].map(clean_text)

    frame["country"] = frame["country"].map(lambda value: clean_text(value).upper())
    frame["posted_date"] = frame["posted_date"].map(_date_text)
    frame["deadline"] = frame["deadline"].map(_date_text)
    frame["observed_at"] = frame["observed_at"].map(_date_text)

    frame["skills"] = frame["skills"].map(
        lambda value: "|".join(normalize_skill_list(value))
    )
    frame["languages"] = frame["languages"].map(
        lambda value: "|".join(sorted(set(split_values(value))))
    )

    minimum = pd.to_numeric(frame["experience_min_years"], errors="coerce").fillna(0).clip(lower=0)
    maximum = pd.to_numeric(frame["experience_max_years"], errors="coerce")
    maximum = maximum.fillna(minimum)
    maximum = maximum.where(maximum >= minimum, minimum)

    frame["experience_min_years"] = minimum.round().astype(int)
    frame["experience_max_years"] = maximum.round().astype(int)

    frame["opportunity_id"] = frame["opportunity_id"].map(clean_text)
    missing_id = frame["opportunity_id"].eq("")
    frame.loc[missing_id, "opportunity_id"] = frame.loc[missing_id].apply(
        lambda row: f"generated-{_record_key(row)}", axis=1
    )

    frame["record_key"] = frame.apply(_record_key, axis=1)
    frame = frame.drop_duplicates("record_key", keep="last").copy()

    frame["status"] = frame.apply(lambda row: _status(row, as_of_date), axis=1)

    deadline_values = frame["deadline"].map(_date_value)
    frame["days_to_deadline"] = pd.array(
        [(deadline - as_of_date).days if deadline else None for deadline in deadline_values],
        dtype="Int64",
    )

    quality_flags = []
    for _, row in frame.iterrows():
        flags = []
        if not row["title"]:
            flags.append("missing_title")
        if not row["source_url"]:
            flags.append("missing_source_url")
        if not row["apply_url"]:
            flags.append("missing_apply_url")
        if not row["skills"]:
            flags.append("missing_skills")
        quality_flags.append("|".join(flags))
    frame["quality_flag"] = quality_flags

    status_order = {"active": 0, "program": 1, "catalog": 2, "expired": 3}
    frame["_status_order"] = frame["status"].map(status_order).fillna(9)
    frame = frame.sort_values(
        ["_status_order", "company", "title"],
        ascending=[True, True, True],
    ).drop(columns="_status_order")

    return frame.reset_index(drop=True)
