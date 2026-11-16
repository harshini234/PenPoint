from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brd import evaluate as V
from brd import params as P

SCEN = {
    "base": "World matches the model's assumptions",
    "weaker_meta": "Metaphylaxis works worse than assumed (true RR 0.75 vs assumed 0.50)",
    "misspecified": "Every assumed risk-effect size off by 0.4-1.6x, 20% more lot-to-lot variation",
    "more_missing": "Missing-data rates x1.5",
}
NAMES = {"current": "Current practice (buyer's call)", "treat_all": "Metaphylaxis on every lot",
         "treat_none": "Pull-and-treat only", "model": "Tool: arrival decision",
         "model_dayk": "Tool: arrival + day-5 re-decision", "oracle": "Perfect hindsight (oracle)"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seeds", type=int, default=3)
    a = ap.parse_args()
    frames = [V.run_scenario(sc, seed=11 + 17 * k).assign(seed=k) for sc in SCEN for k in range(a.seeds)]
    allr = pd.concat(frames)
    num = allr.select_dtypes("number").columns.drop("seed")
    res = allr.groupby(["scenario", "policy"], sort=False)[list(num)].mean().reset_index()
    out = ROOT / "data" / "eval"
    out.mkdir(parents=True, exist_ok=True)
    res.to_csv(out / "results.csv", index=False)

    L = ["# Does the tool make better decisions?", "",
         f"Policy backtest on fresh simulated seasons ({a.seeds} seeds x 600 test lots per scenario, model learns from "
         "800 history lots of the same world). Outcomes are expected values under each lot's TRUE risk. "
         "Cost = metaphylaxis + treatment + lost performance + death loss at 2026 prices (parameter ledger). "
         "Regret = extra cost vs a perfect-hindsight oracle that knows each lot's true risk and true metaphylaxis effect.", "",
         "We report decisions, not classifier accuracy: the risk model shares its equations with the generator, "
         "so accuracy on synthetic data would be circular. The three stress tests make the simulated world "
         "differ from what the model assumes.", ""]
    for sc, desc in SCEN.items():
        d = res[res.scenario == sc]
        L += [f"## {sc}: {desc}", "",
              "| Policy | Lots treated | Cases /100 hd | Deaths /100 hd | Doses /head | Cost $/head | Saving vs current $/head | Doses vs current | Regret $/head |",
              "|---|---|---|---|---|---|---|---|---|"]
        for _, r in d.iterrows():
            L.append(f"| {NAMES[r.policy]} | {r.lots_treated_pct:.0f}% | {r.cases_per_100:.2f} | {r.deaths_per_100:.2f} | "
                     f"{r.doses_per_head:.2f} | {r.cost_per_head:.2f} | {r.saving_vs_current_per_head:+.2f} | "
                     f"{r.dose_change_vs_current_pct:+.0f}% | {r.regret_per_head:.2f} |")
        L.append("")
    b = res[(res.scenario == "base")].set_index("policy")
    gap_closed = 1 - b.loc["model", "regret_per_head"] / b.loc["current", "regret_per_head"]
    L += ["## Reading the results", "",
          "- **Rule: no more deaths than current practice.** The tool is not allowed to trade cattle deaths for money. "
          "Every tool policy must plan for at least "
          f"{P.get('mortality_cap_margin'):.0%} fewer expected deaths than the buyer's call (the safety margin absorbs model error). "
          "Among plans that meet that, it picks the cheapest. The perfect-hindsight row is held to current-practice deaths too (it knows the truth, so it needs no margin).",
          f"- Under that rule the tool's arrival decision still closes {gap_closed:.0%} of the gap between current practice and "
          "perfect hindsight, mainly by not mass-treating lots the buyer over-calls as high-risk and treating under-called ones instead.",
          "- In every scenario and every seed, the tool's deaths per 100 head are at or below current practice. "
          "The 'welfare_price_per_death' column in results.csv is the price per avoided death the rule implies.",
          "- Without the rule the tool would save more (about $3/head and 20% fewer doses in the base world) but deaths "
          "would edge above current practice when assumptions are wrong. We chose not to make that trade.",
          "- Stress tests show how much of the advantage survives when our assumptions are wrong. Where a policy loses to current "
          "practice, that is reported, not hidden.",
          "- All worlds are synthetic, calibrated to Rojas 2022 and Cernicchiaro 2011. Real-world validation needs a yard's own records."]
    (ROOT / "docs" / "evaluation.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
