# %% [markdown]
# AtlasHire market scan
#
# Executable Jupytext-style analysis script.

# %%
from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/processed/opportunities_scored.csv"

if not DATA.exists():
    raise SystemExit("Run `atlashire build --as-of 2026-09-13` first.")

opportunities = pd.read_csv(DATA)

# %%
print("Records:", len(opportunities))
print(opportunities["status"].value_counts())
print(opportunities["recommendation"].value_counts())

# %%
print(
    opportunities[
        [
            "fit_score",
            "recommendation",
            "company",
            "title",
            "location",
            "missing_skills",
        ]
    ]
    .sort_values("fit_score", ascending=False)
    .head(10)
    .to_string(index=False)
)

# %%
print(
    opportunities.groupby("company", as_index=False)["fit_score"]
    .mean()
    .sort_values("fit_score", ascending=False)
    .to_string(index=False)
)
