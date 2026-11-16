import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brd.params import ledger_frame

df = ledger_frame()
df.to_csv(ROOT / "params" / "parameter_ledger.csv", index=False)
print(f"{len(df)} parameters -> params/parameter_ledger.csv")
print(df["tag"].value_counts().to_string())
