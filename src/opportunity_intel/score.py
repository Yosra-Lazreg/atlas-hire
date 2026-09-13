from __future__ import annotations

from pathlib import Path
import re

import pandas as pd
import yaml

from .normalize import canonical_skill, clean_text, normalize_skill_list

WEIGHTS = {
    "role_score": 0.26,
    "skill_score": 0.34,
    "seniority_score": 0.14,
    "location_score": 0.10,
    "opportunity_score": 0.08,
    "evidence_score": 0.08,
}

STATUS_FACTORS = {"active": 1.00, "program": 0.97, "catalog": 0.70, "expired": 0.00}


def load_profile(path: str | Path) -> dict:
    with Path(path).open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle) or {}


def _tokens(value: object) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", clean_text(value).lower()))


def _profile_skills(profile: dict) -> dict[str, float]:
    raw = profile.get("skills") or {}
    if isinstance(raw, list):
        return {canonical_skill(item): 1.0 for item in raw}
    result = {}
    for name, value in raw.items():
        try:
            score = float(value)
        except (TypeError, ValueError):
            score = 0.0
        result[canonical_skill(name)] = max(0.0, min(1.0, score))
    return result


def _target_roles(profile: dict) -> list[str]:
    roles = profile.get("target_roles") or ["Data Analyst"]
    return [clean_text(role).lower() for role in roles if clean_text(role)]


def _role_score(title: object, targets: list[str]) -> tuple[float, str]:
    title_text = clean_text(title).lower()
    title_tokens = _tokens(title_text)
    best = 0.0
    best_target = ""
    for target in targets:
        if target in title_text:
            if 1.0 > best:
                best = 1.0
                best_target = target
            continue
        target_tokens = _tokens(target)
        if not target_tokens:
            continue
        overlap = len(title_tokens & target_tokens) / len(target_tokens)
        if "analyst" in title_tokens and "analyst" in target_tokens:
            overlap += 0.10
        if overlap > best:
            best = min(overlap, 1.0)
            best_target = target
    return round(best, 3), best_target


def _skill_score(required_value: object, profile_skills: dict[str, float]) -> tuple[float, list[str], list[str]]:
    required = normalize_skill_list(required_value)
    if not required:
        return 0.40, [], []
    matched = [skill for skill in required if skill in profile_skills]
    missing = [skill for skill in required if skill not in profile_skills]
    score = sum(profile_skills.get(skill, 0.0) for skill in required) / len(required)
    return round(score, 3), matched, missing


def _seniority_score(row: dict, profile: dict) -> float:
    experience = float(profile.get("experience_years", 0) or 0)
    minimum = float(row.get("experience_min_years", 0) or 0)
    opportunity_type = clean_text(row.get("opportunity_type", "")).lower()
    seniority = clean_text(row.get("seniority", "")).lower()
    student = bool(profile.get("student", False))
    if student and opportunity_type in {"internship", "apprenticeship", "program"}:
        return 1.0
    gap = minimum - experience
    if gap <= 0:
        return 1.0
    if gap <= 1:
        return 0.72
    if gap <= 3:
        return 0.40
    if seniority in {"senior", "manager", "mid-senior"}:
        return 0.10
    return 0.20


def _location_score(row: dict, profile: dict) -> float:
    location = clean_text(row.get("location", "")).lower()
    mode = clean_text(row.get("work_mode", "")).lower()
    country = clean_text(row.get("country", "")).upper()
    profile_country = clean_text(profile.get("country", "Algeria")).upper()
    profile_country = {"ALGERIA": "DZ", "ALGERIE": "DZ"}.get(profile_country, profile_country)
    preferences = profile.get("preferred_locations") or []
    if isinstance(preferences, str):
        preferences = [preferences]
    preferences = [clean_text(v).lower() for v in preferences]
    if any(value and value in location for value in preferences):
        return 1.0
    if country and country == profile_country:
        return 0.90
    if "remote" in f"{location} {mode}" and any("remote" in value for value in preferences):
        return 0.90
    if country == "INTL" and "remote" in f"{location} {mode}":
        return 0.65
    return 0.25


def _opportunity_score(row: dict, profile: dict) -> float:
    opportunity_type = clean_text(row.get("opportunity_type", "")).lower()
    seniority = clean_text(row.get("seniority", "")).lower()
    student = bool(profile.get("student", False))
    if student and opportunity_type in {"internship", "apprenticeship", "program"}:
        return 1.0
    if seniority in {"manager", "senior"}:
        return 0.15
    if opportunity_type == "full-time":
        return 0.75
    return 0.55


def _eligibility_flag(row: dict, profile: dict) -> str:
    text = " ".join(clean_text(row.get(column, "")).lower() for column in ("eligibility", "notes", "location"))
    country = clean_text(profile.get("country", "Algeria")).upper()
    if country in {"ALGERIA", "ALGERIE"}:
        country = "DZ"
    if any(phrase in text for phrase in ("us or canada", "us/canada", "u.s. or canada", "us and canada")) and country not in {"US", "CA"}:
        return "blocker:work_authorization"
    if "does not include algeria" in text and country == "DZ":
        return "blocker:country_scope"
    if "citizenship required" in text and country not in {"US", "CA"}:
        return "blocker:citizenship"
    if any(term in text for term in ("must be authorized", "eligibility", "verify", "must be confirmed", "regional restrictions")):
        return "verify:eligibility"
    return ""


def _evidence_score(row: dict) -> float:
    fields = ["source_url", "apply_url", "skills", "location", "observed_at"]
    completeness = sum(bool(clean_text(row.get(field, ""))) for field in fields) / len(fields)
    source_kind = clean_text(row.get("source_kind", "")).lower()
    source_bonus = 1.0 if source_kind in {"public_api", "official_job_board", "official_career_page"} else 0.70
    return round(min(1.0, 0.65 * completeness + 0.35 * source_bonus), 3)


def _recommendation(
    final_score: float,
    status: str,
    eligibility_flag: str,
    confidence_score: float,
    row: dict,
    profile: dict,
) -> str:
    if status == "expired":
        return "Archive"
    if status == "catalog":
        return "Monitor"
    if eligibility_flag.startswith("blocker:"):
        return "Check eligibility"
    country = clean_text(row.get("country", "")).upper()
    opportunity_type = clean_text(row.get("opportunity_type", "")).lower()
    student = bool(profile.get("student", False))
    # International or otherwise uncertain eligibility is surfaced before fit.
    if eligibility_flag == "verify:eligibility" and country != "DZ":
        return "Check eligibility"
    if confidence_score < 0.50:
        return "Low-confidence monitor"
    # Student pathways in the user's home market are intentionally prioritized.
    if student and country == "DZ" and opportunity_type in {"internship", "apprenticeship", "program"} and final_score >= 58:
        return "Priority"
    if final_score >= 78:
        return "Priority"
    if final_score >= 62:
        return "Stretch"
    return "Monitor"


def score_opportunities(frame: pd.DataFrame, profile: dict) -> pd.DataFrame:
    if frame.empty:
        return frame.copy()

    profile_skills = _profile_skills(profile)
    targets = _target_roles(profile)
    metrics = []

    for row in frame.to_dict(orient="records"):
        role, matched_target = _role_score(row.get("title", ""), targets)
        skill, matched, missing = _skill_score(row.get("skills", ""), profile_skills)
        seniority = _seniority_score(row, profile)
        location = _location_score(row, profile)
        opportunity = _opportunity_score(row, profile)
        evidence = _evidence_score(row)
        status = clean_text(row.get("status", "active")).lower()
        eligibility = _eligibility_flag(row, profile)

        raw_score = (
            role * WEIGHTS["role_score"]
            + skill * WEIGHTS["skill_score"]
            + seniority * WEIGHTS["seniority_score"]
            + location * WEIGHTS["location_score"]
            + opportunity * WEIGHTS["opportunity_score"]
            + evidence * WEIGHTS["evidence_score"]
        )
        fit_score = round(100 * raw_score * STATUS_FACTORS.get(status, 0.50), 1)
        # Confidence is independent of fit: it answers "how trustworthy is the ranking?"
        confidence_score = round(100 * evidence * (0.75 if not eligibility.startswith("blocker:") else 0.45), 1)
        final_score = round(fit_score * 0.88 + confidence_score * 0.12, 1)

        reasons = [
            f"role={role:.2f}", f"skills={skill:.2f}", f"seniority={seniority:.2f}",
            f"location={location:.2f}", f"opportunity={opportunity:.2f}", f"evidence={evidence:.2f}",
        ]
        if matched_target:
            reasons.append(f"target={matched_target}")
        if matched:
            reasons.append("matched=" + ", ".join(matched))
        if missing:
            reasons.append("missing=" + ", ".join(missing))
        if eligibility:
            reasons.append(eligibility)

        metrics.append({
            "role_score": role,
            "skill_score": skill,
            "seniority_score": seniority,
            "location_score": location,
            "opportunity_score": opportunity,
            "evidence_score": evidence,
            "fit_score": fit_score,
            "confidence_score": confidence_score,
            "final_score": final_score,
            "matched_skills": "|".join(matched),
            "missing_skills": "|".join(missing),
            "eligibility_flag": eligibility,
            "fit_reasons": "; ".join(reasons),
            "recommendation": _recommendation(
                final_score, status, eligibility, confidence_score / 100, row, profile
            ),
        })

    scored = frame.copy()
    metric_frame = pd.DataFrame(metrics, index=scored.index)
    for column in metric_frame.columns:
        scored[column] = metric_frame[column]

    recommendation_order = {
        "Priority": 0, "Check eligibility": 1, "Stretch": 2,
        "Monitor": 3, "Low-confidence monitor": 4, "Archive": 5,
    }
    scored["_recommendation_order"] = scored["recommendation"].map(recommendation_order).fillna(9)
    scored = scored.sort_values(["_recommendation_order", "final_score"], ascending=[True, False])
    return scored.drop(columns="_recommendation_order").reset_index(drop=True)
