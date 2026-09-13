from pathlib import Path

import pandas as pd

from opportunity_intel.normalize import canonical_skill, normalize_snapshot
from opportunity_intel.score import score_opportunities

ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT = ROOT / "data/raw/opportunities_snapshot.csv"


def test_skill_aliases_are_canonicalized():
    assert canonical_skill("PowerBI") == "power bi"
    assert canonical_skill("Google Data Studio") == "looker"
    assert canonical_skill("Pyspark") == "spark"


def test_expiry_and_program_status_are_distinguished():
    frame = normalize_snapshot(SNAPSHOT, as_of="2026-09-13")

    expired = frame.loc[
        frame["opportunity_id"] == "UN-DV-001", "status"
    ].iloc[0]
    program = frame.loc[
        frame["opportunity_id"] == "OOR-ST-001", "status"
    ].iloc[0]

    assert expired == "expired"
    assert program == "program"


def test_student_profile_prefers_internship_seniority():
    frame = pd.DataFrame(
        [
            {
                "opportunity_id": "intern",
                "company": "Example",
                "title": "Data Analytics Intern",
                "opportunity_type": "internship",
                "work_mode": "remote",
                "location": "Algeria",
                "country": "DZ",
                "seniority": "student",
                "experience_min_years": 0,
                "experience_max_years": 1,
                "skills": "sql|python|excel",
                "status": "active",
                "eligibility": "",
                "notes": "",
            },
            {
                "opportunity_id": "manager",
                "company": "Example",
                "title": "Analytics Manager",
                "opportunity_type": "full-time",
                "work_mode": "hybrid",
                "location": "Algeria",
                "country": "DZ",
                "seniority": "manager",
                "experience_min_years": 8,
                "experience_max_years": 12,
                "skills": "sql|python|excel",
                "status": "active",
                "eligibility": "",
                "notes": "",
            },
        ]
    )

    profile = {
        "country": "Algeria",
        "student": True,
        "experience_years": 0,
        "target_roles": ["Data Analyst", "Data Analytics Intern"],
        "preferred_locations": ["Algeria", "Remote"],
        "skills": {"sql": 0.9, "python": 0.8, "excel": 0.9},
    }

    scored = score_opportunities(frame, profile)
    intern = scored.loc[scored["opportunity_id"] == "intern"].iloc[0]
    manager = scored.loc[scored["opportunity_id"] == "manager"].iloc[0]

    assert intern["seniority_score"] > manager["seniority_score"]
    assert intern["fit_score"] > manager["fit_score"]


def test_blocked_work_authorization_is_visible():
    frame = pd.DataFrame(
        [
            {
                "opportunity_id": "blocked",
                "company": "Example",
                "title": "Data Analyst Intern",
                "opportunity_type": "internship",
                "work_mode": "remote",
                "location": "Remote",
                "country": "US-CA",
                "seniority": "student",
                "experience_min_years": 0,
                "experience_max_years": 1,
                "skills": "sql|python",
                "status": "active",
                "eligibility": "US or Canada work authorization required",
                "notes": "",
            }
        ]
    )

    profile = {
        "country": "Algeria",
        "student": True,
        "experience_years": 0,
        "target_roles": ["Data Analyst"],
        "preferred_locations": ["Remote"],
        "skills": {"sql": 1.0, "python": 1.0},
    }

    scored = score_opportunities(frame, profile)
    assert scored.iloc[0]["eligibility_flag"] == "blocker:work_authorization"
    assert scored.iloc[0]["recommendation"] == "Check eligibility"



def test_advanced_score_has_fit_confidence_and_final_score():
    frame = normalize_snapshot(SNAPSHOT, as_of="2026-09-13")
    profile = {
        "country": "Algeria",
        "student": True,
        "experience_years": 0,
        "target_roles": ["Data Analyst", "Data Analytics Intern"],
        "preferred_locations": ["Algeria", "Remote"],
        "skills": {"sql": 0.9, "python": 0.8, "excel": 0.9, "power bi": 0.8},
    }
    scored = score_opportunities(frame, profile)
    assert scored["fit_score"].between(0, 100).all()
    assert scored["confidence_score"].between(0, 100).all()
    assert scored["final_score"].between(0, 100).all()
    assert "evidence_score" in scored.columns


def test_recommendation_policy_prioritizes_local_student_pathways_and_flags_international_uncertainty():
    frame = normalize_snapshot(SNAPSHOT, as_of="2026-09-13")
    profile = {
        "country": "Algeria",
        "student": True,
        "experience_years": 0,
        "target_roles": ["Data Analyst", "Data Analytics Intern"],
        "preferred_locations": ["Algeria", "Remote"],
        "skills": {"sql": 0.9, "python": 0.8, "excel": 0.9, "power bi": 0.8},
    }
    scored = score_opportunities(frame, profile)
    local_student = scored.loc[scored["opportunity_id"] == "OOR-ST-001", "recommendation"].iloc[0]
    intl = scored.loc[scored["opportunity_id"] == "UN-IAH-001", "recommendation"].iloc[0]
    assert local_student == "Priority"
    assert intl == "Check eligibility"


def test_expired_records_archive_before_eligibility_rules():
    frame = normalize_snapshot(SNAPSHOT, as_of="2026-09-13")
    profile = {
        "country": "Algeria",
        "student": True,
        "experience_years": 0,
        "target_roles": ["Data Analyst"],
        "preferred_locations": ["Algeria", "Remote"],
        "skills": {"sql": 1.0},
    }
    scored = score_opportunities(frame, profile)
    result = scored.loc[scored["opportunity_id"] == "ESR-DA-001", "recommendation"].iloc[0]
    assert result == "Archive"


def test_public_connector_transformers_keep_source_links():
    from opportunity_intel.connectors import ashby_rows, lever_rows

    lever = lever_rows([{
        "id": "abc",
        "text": "Data Analyst",
        "descriptionPlain": "Python SQL",
        "categories": {"location": "Algiers", "commitment": "Full-time"},
        "hostedUrl": "https://jobs.lever.co/example/abc",
        "applyUrl": "https://jobs.lever.co/example/abc/apply",
    }], "Example", observed_at="2026-09-13", include_terms=["data"])
    ashby = ashby_rows([{
        "title": "Analytics Intern",
        "location": "Algeria / Remote",
        "isListed": True,
        "jobUrl": "https://jobs.ashbyhq.com/example/job/123",
        "applyUrl": "https://jobs.ashbyhq.com/example/job/123",
        "team": "Data",
        "department": "Analytics",
    }], "example", "Example", observed_at="2026-09-13", include_terms=["analytics"])

    assert lever[0]["source_url"].startswith("https://jobs.lever.co/")
    assert ashby[0]["source_url"].startswith("https://jobs.ashbyhq.com/")
    assert "python" in lever[0]["skills"]
    assert "analytics" in ashby[0]["title"].lower()


def test_search_matches_across_fields_and_multiple_terms():
    frame = pd.DataFrame([
        {
            "title": "Data Analyst",
            "company": "Yassir",
            "skills": "excel|python|sql",
            "location": "Algiers",
            "opportunity_type": "full-time",
            "work_mode": "onsite",
            "eligibility": "Algeria-based role",
            "notes": "",
            "matched_skills": "python|sql",
            "missing_skills": "power bi",
        },
        {
            "title": "Applied Research Intern",
            "company": "Weaviate",
            "skills": "machine learning|python",
            "location": "Worldwide",
            "opportunity_type": "internship",
            "work_mode": "remote",
            "eligibility": "Verify regional restrictions",
            "notes": "",
            "matched_skills": "python",
            "missing_skills": "sql",
        },
    ])

    def search_rows(data, query):
        columns = [
            "title", "company", "skills", "location", "opportunity_type",
            "work_mode", "eligibility", "notes", "matched_skills", "missing_skills",
        ]
        haystack = data[columns].fillna("").astype(str).agg(" ".join, axis=1).str.casefold()
        mask = pd.Series(True, index=data.index)
        for term in query.casefold().split():
            mask &= haystack.str.contains(term, regex=False, na=False)
        return data.loc[mask]

    assert len(search_rows(frame, "python")) == 2
    assert len(search_rows(frame, "Yassir Algiers")) == 1
    assert search_rows(frame, "Yassir Algiers").iloc[0]["company"] == "Yassir"
