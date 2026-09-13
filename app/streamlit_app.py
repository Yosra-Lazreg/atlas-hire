from __future__ import annotations

from pathlib import Path
import sys

import pandas as pd
import plotly.express as px
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from opportunity_intel.pipeline import build  # noqa: E402

RAW_PATH = ROOT / "data/raw/opportunities_snapshot.csv"
PROFILE_PATH = ROOT / "config/profile.example.yml"
SCORED_PATH = ROOT / "data/processed/opportunities_scored.csv"
HISTORY_PATH = ROOT / "data/history"
HEALTH_PATH = ROOT / "data/raw/live/source_health.csv"
VALIDATION_PATH = ROOT / "outputs/validation_report.json"

st.set_page_config(page_title="AtlasHire", page_icon="A", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;700&family=Space+Grotesk:wght@500;700&display=swap');
.stApp { background: linear-gradient(135deg, #f5f1e8 0%, #edf4f1 100%); }
html, body, [class*="css"] { font-family: "DM Sans", sans-serif; }
h1, h2, h3 { font-family: "Space Grotesk", sans-serif; }
.hero { padding: 1.4rem 1.6rem; border: 1px solid #d7d0c4; border-radius: 18px; background: linear-gradient(120deg, #fffdf8, #e9f3ef); margin-bottom: 1rem; }
.hero-label { color: #e67e22; text-transform: uppercase; letter-spacing: .14em; font-weight: 700; font-size: .72rem; }
.hero h1 { margin: .25rem 0 .3rem; font-size: 2.5rem; }
.hero p { color: #587083; max-width: 900px; margin-bottom: 0; }
div[data-testid="stMetric"] { background: #fffdf8; border: 1px solid #d7d0c4; border-radius: 14px; padding: .8rem; }
</style>
""", unsafe_allow_html=True)


def ensure_scored_data() -> pd.DataFrame:
    if not SCORED_PATH.exists():
        build(snapshot_path=RAW_PATH, profile_path=PROFILE_PATH, as_of="2026-09-13")
    frame = pd.read_csv(SCORED_PATH)
    for column in ("fit_score", "confidence_score", "final_score"):
        frame[column] = pd.to_numeric(frame[column], errors="coerce").fillna(0)
    return frame


def history_frame() -> pd.DataFrame:
    files = sorted(HISTORY_PATH.glob("scored_*.csv"))
    if not files:
        return pd.DataFrame()
    frames = []
    for path in files:
        item = pd.read_csv(path)
        item["snapshot_date"] = path.stem.replace("scored_", "")
        frames.append(item)
    return pd.concat(frames, ignore_index=True)


df = ensure_scored_data()

st.markdown("""
<div class="hero">
<div class="hero-label">Algeria-first opportunity intelligence</div>
<h1>AtlasHire</h1>
<p>Rank opportunities by fit <b>and</b> ranking confidence, explain the skill gap, surface eligibility risk, and track the market over time.</p>
</div>
""", unsafe_allow_html=True)

pages = st.tabs(["Overview", "Opportunity Explorer", "Skill Gaps", "Market History", "Data Quality"])

with pages[0]:
    a, b, c, d, e = st.columns(5)
    a.metric("All records", len(df))
    b.metric("Algeria records", int((df["country"] == "DZ").sum()))
    c.metric("Priority", int((df["recommendation"] == "Priority").sum()))
    d.metric("Avg score", f"{df['final_score'].mean():.1f}")
    e.metric("Avg confidence", f"{df['confidence_score'].mean():.0f}%")

    left, right = st.columns([1.1, 1])
    with left:
        st.subheader("Recommendation mix")
        mix = df["recommendation"].value_counts().rename_axis("recommendation").reset_index(name="records")
        fig = px.bar(mix, x="records", y="recommendation", orientation="h")
        st.plotly_chart(fig, use_container_width=True)
    with right:
        st.subheader("Top companies by average score")
        company = df.groupby("company", as_index=False)["final_score"].mean().sort_values("final_score", ascending=False).head(10)
        fig = px.bar(company, x="final_score", y="company", orientation="h")
        st.plotly_chart(fig, use_container_width=True)

    st.info("The final score combines fit and evidence confidence. It is a prioritization heuristic, not a hiring prediction.")

with pages[1]:
    st.sidebar.header("Explorer filters")
    statuses = sorted(df["status"].dropna().unique().tolist())
    types = sorted(df["opportunity_type"].dropna().unique().tolist())
    companies = sorted(df["company"].dropna().unique().tolist())
    selected_statuses = st.sidebar.multiselect("Status", statuses, default=[x for x in statuses if x != "expired"])
    selected_types = st.sidebar.multiselect("Type", types, default=types)
    selected_companies = st.sidebar.multiselect("Company", companies, default=companies)
    minimum_score = st.sidebar.slider("Minimum final score", 0, 100, 0, 5)
    search = st.sidebar.text_input(
        "Search title, company, skill, or location",
        placeholder="e.g. python, Yassir, Algiers, data analyst",
    )

    filtered = df[
        df["status"].isin(selected_statuses)
        & df["opportunity_type"].isin(selected_types)
        & df["company"].isin(selected_companies)
        & (df["final_score"] >= minimum_score)
    ].copy()

    if search.strip():
        search_columns = [
            "title", "company", "skills", "location", "opportunity_type",
            "work_mode", "eligibility", "notes", "matched_skills", "missing_skills",
        ]
        available = [c for c in search_columns if c in filtered.columns]
        haystack = filtered[available].fillna("").astype(str).agg(" ".join, axis=1).str.casefold()
        terms = [term for term in search.casefold().split() if term]
        mask = pd.Series(True, index=filtered.index)
        for term in terms:
            mask &= haystack.str.contains(term, regex=False, na=False)
        filtered = filtered.loc[mask].copy()

    st.caption(f"{len(filtered)} opportunity(ies) match the current filters")

    display = filtered.sort_values(["final_score", "confidence_score"], ascending=[False, False]).copy()
    display["Apply"] = display["apply_url"]
    cols = ["final_score", "confidence_score", "recommendation", "company", "title", "opportunity_type", "work_mode", "location", "matched_skills", "missing_skills", "eligibility_flag", "Apply"]
    st.dataframe(display[[c for c in cols if c in display.columns]], use_container_width=True, hide_index=True,
                 column_config={
                     "final_score": st.column_config.NumberColumn("Score", format="%.1f"),
                     "confidence_score": st.column_config.NumberColumn("Confidence", format="%.0f%%"),
                     "Apply": st.column_config.LinkColumn("Source", display_text="Open source"),
                 })

    if not filtered.empty:
        st.subheader("Why this opportunity ranks here")
        selected_id = st.selectbox("Select opportunity", filtered["opportunity_id"].tolist())
        selected = filtered[filtered["opportunity_id"] == selected_id].iloc[0]
        m1, m2, m3 = st.columns(3)
        m1.metric("Final score", f"{selected['final_score']:.1f}")
        m2.metric("Fit", f"{selected['fit_score']:.1f}")
        m3.metric("Confidence", f"{selected['confidence_score']:.0f}%")
        st.write(selected["fit_reasons"])

with pages[2]:
    st.subheader("Most requested missing skills")
    gap_counts = {}
    for value in df.loc[df["status"] != "expired", "missing_skills"].fillna(""):
        for skill in str(value).split("|"):
            if skill:
                gap_counts[skill] = gap_counts.get(skill, 0) + 1
    gap = pd.DataFrame(sorted(gap_counts.items(), key=lambda x: (-x[1], x[0])), columns=["skill", "opportunities"]).head(15)
    if gap.empty:
        st.info("No missing-skill data available.")
    else:
        st.plotly_chart(px.bar(gap, x="opportunities", y="skill", orientation="h"), use_container_width=True)

with pages[3]:
    hist = history_frame()
    st.subheader("Historical score and opportunity trends")
    if hist.empty:
        st.info("History appears after you run `atlashire build` for multiple refresh dates.")
    else:
        trend = hist.groupby("snapshot_date", as_index=False).agg(
            records=("opportunity_id", "count"),
            avg_score=("final_score", "mean"),
            priority=("recommendation", lambda s: int((s == "Priority").sum())),
        )
        trend["avg_score"] = trend["avg_score"].round(2)
        st.dataframe(trend, use_container_width=True, hide_index=True)
        st.plotly_chart(px.line(trend, x="snapshot_date", y="avg_score", markers=True), use_container_width=True)
        st.plotly_chart(px.line(trend, x="snapshot_date", y="records", markers=True), use_container_width=True)

with pages[4]:
    st.subheader("Source health")
    if HEALTH_PATH.exists():
        st.dataframe(pd.read_csv(HEALTH_PATH), use_container_width=True, hide_index=True)
    else:
        st.info("Run `atlashire refresh` to populate source health metrics.")

    st.subheader("Recommendation validation")
    if VALIDATION_PATH.exists():
        validation = pd.read_json(VALIDATION_PATH, typ="series")
        st.json(validation.to_dict())
    else:
        st.info("Run `atlashire validate` to evaluate category agreement and priority precision/recall against the benchmark set.")
