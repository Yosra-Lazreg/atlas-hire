from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
HISTORY = ROOT / "data/history"
files = sorted(HISTORY.glob("scored_*.csv"))

if not files:
    raise SystemExit("No history snapshots yet. Run `atlashire build` after each refresh.")

frames = []
for path in files:
    frame = pd.read_csv(path)
    frame["snapshot_date"] = path.stem.replace("scored_", "")
    frames.append(frame)

history = pd.concat(frames, ignore_index=True)
print("Snapshots:", history["snapshot_date"].nunique())
print("Rows:", len(history))
print("\nAverage final score by snapshot:")
print(history.groupby("snapshot_date")["final_score"].mean().round(2))
print("\nOpportunity count by company and snapshot:")
print(history.groupby(["snapshot_date", "company"]).size().unstack(fill_value=0))
