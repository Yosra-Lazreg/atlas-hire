from __future__ import annotations

from datetime import date
import json
from pathlib import Path
import re
from time import perf_counter
from urllib.parse import quote

import pandas as pd
import requests
import yaml

SKILL_PATTERNS = {
    "sql": r"\bsql\b|structured query language",
    "python": r"\bpython\b",
    "excel": r"\bexcel\b|google sheets",
    "power bi": r"power\s*bi",
    "tableau": r"\btableau\b",
    "looker": r"\blooker\b|data studio",
    "statistics": r"statistics|statistical",
    "machine learning": r"machine learning|\bml\b",
    "data visualization": r"data visuali[sz]",
    "data engineering": r"data engineer",
    "data quality": r"data quality",
    "bigquery": r"bigquery",
    "gcp": r"\bgcp\b|google cloud",
    "spark": r"spark|pyspark",
    "airflow": r"airflow",
    "api": r"\bapi\b",
    "power query": r"power query",
    "vba": r"\bvba\b",
    "research": r"\bresearch\b",
    "database": r"\bdatabase\b",
    "information retrieval": r"information retrieval",
}


def _request_json(url: str, timeout: int = 30) -> tuple[object, int, float]:
    started = perf_counter()
    response = requests.get(
        url,
        timeout=timeout,
        headers={"User-Agent": "AtlasHire/0.2 public-read-only"},
    )
    elapsed_ms = round((perf_counter() - started) * 1000, 1)
    response.raise_for_status()
    return response.json(), response.status_code, elapsed_ms


def fetch_lever(site: str, timeout: int = 30) -> list[dict]:
    url = f"https://api.lever.co/v0/postings/{quote(site, safe='')}?mode=json"
    payload, _, _ = _request_json(url, timeout=timeout)
    return payload if isinstance(payload, list) else []


def fetch_ashby(board_name: str, timeout: int = 30) -> list[dict]:
    url = f"https://api.ashbyhq.com/posting-api/job-board/{quote(board_name, safe='')}"
    payload, _, _ = _request_json(url, timeout=timeout)
    if not isinstance(payload, dict):
        return []
    jobs = payload.get("jobs") or []
    return jobs if isinstance(jobs, list) else []


def extract_skills(text: str) -> list[str]:
    lowered = text.lower()
    return sorted(skill for skill, pattern in SKILL_PATTERNS.items() if re.search(pattern, lowered))


def _include_text(title: str, body: str, include_terms: list[str] | None) -> bool:
    terms = [str(term).strip().lower() for term in (include_terms or []) if str(term).strip()]
    if not terms:
        return True
    haystack = f"{title} {body}".lower()
    return any(term in haystack for term in terms)


def _country_from_location(location: str) -> str:
    text = location.lower()
    if "algeria" in text or "algiers" in text or "dz" in text:
        return "DZ"
    if "canada" in text:
        return "CA"
    if "united states" in text or "new york" in text or "us" == text.strip():
        return "US"
    return "INTL"


def lever_rows(
    postings: list[dict],
    site: str,
    observed_at: str | None = None,
    include_terms: list[str] | None = None,
) -> list[dict]:
    observed = observed_at or date.today().isoformat()
    rows = []

    for posting in postings:
        title = str(posting.get("text", "")).strip()
        body = " ".join(
            str(posting.get(key, "") or "")
            for key in ("descriptionPlain", "openingPlain", "additionalPlain")
        )
        if not _include_text(title, body, include_terms):
            continue

        categories = posting.get("categories") or {}
        location = categories.get("location") or "Unspecified"
        all_locations = categories.get("allLocations") or []
        combined_location = " / ".join(dict.fromkeys([str(location)] + [str(item) for item in all_locations]))
        lowered = combined_location.lower()
        work_mode = "remote" if "remote" in lowered else "hybrid" if "hybrid" in lowered else "unknown"
        commitment = categories.get("commitment") or "unknown"
        posting_id = posting.get("id") or title.lower().replace(" ", "-")

        rows.append({
            "opportunity_id": f"{site.upper()}-{posting_id}",
            "company": site,
            "title": title,
            "opportunity_type": commitment,
            "work_mode": work_mode,
            "location": combined_location,
            "country": posting.get("country") or _country_from_location(combined_location),
            "seniority": "unknown",
            "experience_min_years": 0,
            "experience_max_years": 0,
            "skills": "|".join(extract_skills(f"{title} {body}")),
            "languages": "",
            "posted_date": posting.get("createdAt", ""),
            "deadline": "",
            "availability": "live_listing",
            "source_kind": "public_api",
            "source_name": f"{site} Lever API",
            "source_url": posting.get("hostedUrl") or "",
            "apply_url": posting.get("applyUrl") or posting.get("hostedUrl") or "",
            "eligibility": "Verify current location and work authorization.",
            "notes": "Fetched from the public Lever postings endpoint.",
            "observed_at": observed,
        })

    return rows


def ashby_rows(
    jobs: list[dict],
    board_name: str,
    company: str,
    observed_at: str | None = None,
    include_terms: list[str] | None = None,
) -> list[dict]:
    observed = observed_at or date.today().isoformat()
    rows = []

    for job in jobs:
        if job.get("isListed") is False:
            continue
        title = str(job.get("title") or "").strip()
        location = str(job.get("location") or "Unspecified").strip()
        body = " ".join(str(job.get(key) or "") for key in ("description", "team", "department"))
        if not _include_text(title, body, include_terms):
            continue

        secondary = [str(item.get("location") or "") for item in (job.get("secondaryLocations") or [])]
        locations = " / ".join(dict.fromkeys([location] + [item for item in secondary if item]))
        lower_loc = locations.lower()
        work_mode = "remote" if "remote" in lower_loc else "hybrid" if "hybrid" in lower_loc else "unknown"
        job_url = job.get("jobUrl") or ""
        apply_url = job.get("applyUrl") or job_url
        job_id = job.get("jobUrl", "").rstrip("/").split("/")[-1] or re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")

        rows.append({
            "opportunity_id": f"ASHBY-{board_name.upper()}-{job_id}",
            "company": company,
            "title": title,
            "opportunity_type": "full-time",
            "work_mode": work_mode,
            "location": locations,
            "country": _country_from_location(locations),
            "seniority": "unknown",
            "experience_min_years": 0,
            "experience_max_years": 0,
            "skills": "|".join(extract_skills(f"{title} {body}")),
            "languages": "",
            "posted_date": "",
            "deadline": "",
            "availability": "live_listing",
            "source_kind": "public_api",
            "source_name": f"{company} Ashby Public Job Postings API",
            "source_url": job_url,
            "apply_url": apply_url,
            "eligibility": "Verify current location and work authorization.",
            "notes": "Fetched from Ashby's public Job Postings API.",
            "observed_at": observed,
        })

    return rows


def refresh_source(source: dict, output_dir: str | Path, observed_at: str | None = None) -> dict:
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    observed = observed_at or date.today().isoformat()
    adapter = str(source.get("adapter", "manual")).lower()
    started = perf_counter()
    result = {
        "source_id": source.get("id", ""),
        "adapter": adapter,
        "source_url": source.get("source_url", ""),
        "observed_at": observed,
        "status": "skipped" if adapter == "manual" else "ok",
        "http_status": None,
        "records": 0,
        "latency_ms": None,
        "error": "",
    }

    if not source.get("enabled", True) or adapter == "manual":
        return result

    try:
        if adapter == "lever":
            postings = fetch_lever(str(source["handle"]))
            rows = lever_rows(postings, str(source["handle"]), observed, source.get("include_terms"))
            suffix = "lever"
        elif adapter == "ashby":
            jobs = fetch_ashby(str(source["handle"]))
            rows = ashby_rows(jobs, str(source["handle"]), str(source.get("company", source["id"])), observed, source.get("include_terms"))
            suffix = "ashby"
        else:
            raise ValueError(f"Unsupported adapter: {adapter}")

        pd.DataFrame(rows).to_csv(output_dir / f"{source['id']}_{suffix}.csv", index=False)
        (output_dir / f"{source['id']}_{suffix}.json").write_text(
            json.dumps(postings if adapter == "lever" else jobs, indent=2, ensure_ascii=True), encoding="utf-8"
        )
        result["records"] = len(rows)
    except Exception as exc:
        result["status"] = "error"
        result["error"] = f"{type(exc).__name__}: {exc}"

    result["latency_ms"] = round((perf_counter() - started) * 1000, 1)
    return result


def refresh_config(config_path: str | Path, output_dir: str | Path, observed_at: str | None = None) -> pd.DataFrame:
    config = yaml.safe_load(Path(config_path).read_text(encoding="utf-8")) or {}
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    observed = observed_at or date.today().isoformat()
    results = []
    combined = []

    for source in config.get("sources", []):
        result = refresh_source(source, output_dir, observed)
        results.append(result)
        if result["status"] == "ok":
            adapter = str(source.get("adapter", "")).lower()
            if adapter == "lever":
                csv_path = output_dir / f"{source['id']}_lever.csv"
            else:
                csv_path = output_dir / f"{source['id']}_ashby.csv"
            if csv_path.exists():
                frame = pd.read_csv(csv_path)
                if not frame.empty:
                    combined.append(frame)

    if combined:
        pd.concat(combined, ignore_index=True).to_csv(output_dir / "combined.csv", index=False)
    else:
        # Keep a valid schema even when every live source is unavailable.
        pd.DataFrame(columns=[
            "opportunity_id", "company", "title", "opportunity_type", "work_mode",
            "location", "country", "seniority", "experience_min_years", "experience_max_years",
            "skills", "languages", "posted_date", "deadline", "availability", "source_kind",
            "source_name", "source_url", "apply_url", "eligibility", "notes", "observed_at",
        ]).to_csv(output_dir / "combined.csv", index=False)

    return pd.DataFrame(results)


def save_lever_snapshot(site: str, output_json: str | Path, output_csv: str | Path | None = None) -> int:
    postings = fetch_lever(site)
    rows = lever_rows(postings, site)
    output_json = Path(output_json)
    output_json.parent.mkdir(parents=True, exist_ok=True)
    output_json.write_text(json.dumps(postings, indent=2, ensure_ascii=True), encoding="utf-8")
    if output_csv:
        Path(output_csv).parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(output_csv, index=False)
    return len(rows)
