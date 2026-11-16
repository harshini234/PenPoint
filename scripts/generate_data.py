from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brd import generator as G
from brd import params as P
from brd.schema import lot_columns

AS_OF = pd.Timestamp("2026-11-14")
OUT = ROOT / "data" / "demo"
OBS_EXTRA = ["origin_region"]
OUTCOME_COLS = ["metaphylaxis_given", "cases_45", "morbidity_45", "deaths_45", "mortality_45"]
TRUTH_COLS = ["true_logodds", "p_case_no_meta", "meta_rr", "p_case_observed", "high_observed", "high_counterfactual"]


def build(lots: pd.DataFrame, rng: np.random.Generator):
    draws = G.Draws.make(len(lots), rng)
    out = G.assign_outcomes(lots, draws, P.get("lot_intercept"), P.get("lot_random_sd"),
                            P.get("human_call_noise_sd"), P.get("human_call_threshold"))
    out, daily = G.add_deaths_and_daily(out, rng)
    obs = G.mask_missing(out, rng)
    return out, obs, daily


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--n-history", type=int, default=1500)
    a = ap.parse_args()
    rng = np.random.default_rng(a.seed)
    OUT.mkdir(parents=True, exist_ok=True)

    y = P.load_yards()["yards"]
    pd.DataFrame([{"yard_id": k, **{c: v[c] for c in ("name", "region", "profile", "one_time_capacity_head", "riders",
                                                        "rider_hours_per_day", "hospital_pen_head", "chute_hours_per_day")}}
                  for k, v in y.items()]).to_csv(OUT / "yards.csv", index=False)

    hist = G.sample_lots(a.n_history, rng, "2024-11-01", "2026-09-30", prefix="H")
    h_truth, h_obs, h_daily = build(hist, rng)
    keep = lot_columns()
    h_obs[keep + OUTCOME_COLS].to_csv(OUT / "lots_history.csv", index=False)
    h_daily.to_csv(OUT / "daily_history.csv", index=False)
    h_truth[keep + OBS_EXTRA + OUTCOME_COLS + TRUTH_COLS].to_csv(OUT / "truth_history.csv", index=False)

    inprog = G.sample_lots(36, rng, "2026-10-20", "2026-11-14", prefix="C")
    upcoming = G.sample_lots(18, rng, "2026-11-16", "2026-11-20", prefix="N")
    upcoming["lot_id"] = upcoming["lot_id"].str.replace("N", "C1", regex=False)
    cur = pd.concat([inprog, upcoming], ignore_index=True)
    c_truth, c_obs, c_daily = build(cur, rng)

    arr = pd.to_datetime(c_obs["arrival_date"])
    c_obs["days_on_feed"] = (AS_OF - arr).dt.days
    c_obs["status"] = np.where(c_obs["days_on_feed"] >= 0, "in_progress", "arriving")
    pending = c_obs["status"] == "arriving"
    c_obs["metaphylaxis_given"] = c_obs["metaphylaxis_given"].astype(object)
    c_obs.loc[pending, "metaphylaxis_given"] = None
    c_obs[keep + ["status", "days_on_feed", "metaphylaxis_given"]].to_csv(OUT / "lots_current.csv", index=False)

    dof = c_obs.set_index("lot_id")["days_on_feed"]
    c_daily = c_daily[c_daily["day"] <= c_daily["lot_id"].map(dof)]
    c_daily.to_csv(OUT / "daily_current.csv", index=False)
    c_truth[keep + OBS_EXTRA + OUTCOME_COLS + TRUTH_COLS].to_csv(OUT / "truth_current.csv", index=False)

    print(f"history lots: {len(h_obs)}, daily rows: {len(h_daily)}")
    print(f"current lots: {len(c_obs)} ({(~pending).sum()} in progress, {pending.sum()} arriving), daily rows: {len(c_daily)}")
    print(f"written to {OUT}")


if __name__ == "__main__":
    main()
