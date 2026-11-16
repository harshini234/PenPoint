from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brd.schema import DAILY_FIELDS, LOT_FIELDS, TIERS

OUTCOMES = [
    ("metaphylaxis_given", "bool", "", "Arrival metaphylaxis given under the yard's current practice (blank = decision pending)"),
    ("cases_45", "int", "head", "Animals treated for BRD at least once within 45 days (first treatments) - Rojas outcome definition"),
    ("morbidity_45", "float", "proportion", "cases_45 / head_count"),
    ("deaths_45", "int", "head", "BRD deaths within 45 days"),
    ("mortality_45", "float", "proportion", "deaths_45 / head_count"),
    ("status", "category", "", "lots_current only: in_progress (arrived) or arriving (decision pending)"),
    ("days_on_feed", "int", "days", "lots_current only: days since arrival as of 2026-11-14 (negative = not yet arrived)"),
]
TRUTH = [
    ("origin_region", "Origin region used to compute haul distance"),
    ("true_logodds", "Latent log-odds of an animal becoming a BRD case without metaphylaxis (incl. lot random effect)"),
    ("p_case_no_meta", "Probability an animal becomes a case without metaphylaxis"),
    ("meta_rr", "Relative risk applied if metaphylaxis was given (1 otherwise)"),
    ("p_case_observed", "Probability actually applied under current practice"),
    ("high_observed", "morbidity_45 >= 15%"),
    ("high_counterfactual", "Would have been >= 15% without metaphylaxis"),
]


def main() -> None:
    L = ["# Data dictionary", "",
         "All demo data are **synthetic and fictional** (scripts/generate_data.py). Field definitions live in "
         "`src/brd/schema.py`; this file is generated from it by `scripts/make_data_dictionary.py`.", "",
         "## Data tiers", "", "| Tier | Meaning |", "|---|---|"]
    L += [f"| `{k}` | {v} |" for k, v in TIERS.items()]
    L += ["", "## Lot fields (`lots_history.csv`, `lots_current.csv`) - one row per arrival lot", "",
          "| Field | Type | Unit | Tier | Description | Allowed values | Paperwork it can come from |", "|---|---|---|---|---|---|---|"]
    for f in LOT_FIELDS:
        L.append(f"| `{f.name}` | {f.dtype} | {f.unit} | {f.tier} | {f.description}{' - ' + f.notes if f.notes else ''} | "
                 f"{', '.join(f.allowed)} | {', '.join(f.documents)} |")
    L += ["", "## Outcome / status fields", "", "| Field | Type | Unit | Description |", "|---|---|---|---|"]
    L += [f"| `{a}` | {b} | {c} | {d} |" for a, b, c, d in OUTCOMES]
    L += ["", "## Daily fields (`daily_history.csv`, `daily_current.csv`) - one row per lot per day", "",
          "| Field | Type | Unit | Description |", "|---|---|---|---|"]
    L += [f"| `{f.name}` | {f.dtype} | {f.unit} | {f.description} |" for f in DAILY_FIELDS]
    L += ["", "## Evaluation-only fields (`truth_*.csv`) - never shown in the dashboard", "",
          "Complete inputs (no missing values) plus:", "", "| Field | Description |", "|---|---|"]
    L += [f"| `{a}` | {b} |" for a, b in TRUTH]
    L += ["", "## Yards (`yards.csv`)", "", "Fictional yards from `params/yards.yaml`: riders, rider hours/day, hospital-pen "
          "capacity (head), chute hours/day - the binding constraints used by the feasibility step."]
    (ROOT / "docs" / "data_dictionary.md").write_text("\n".join(L) + "\n")
    print("wrote docs/data_dictionary.md")


if __name__ == "__main__":
    main()
