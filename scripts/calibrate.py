from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

import numpy as np
import yaml
from scipy.optimize import minimize

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from brd import generator as G
from brd import params as P

N, SEED = 4000, 20261114


def main() -> None:
    rng = np.random.default_rng(SEED)
    lots = G.sample_lots(N, rng, "2024-11-01", "2026-09-30")
    draws = G.Draws.make(N, rng)
    T = {
        "prev_high_lots": P.get("target_prev_high_lots"),
        "mean_morbidity": P.get("target_mean_morbidity"),
        "human_sensitivity": P.get("human_sensitivity"),
        "human_specificity": P.get("human_specificity"),
        "fall_incidence": P.get("target_fall_incidence"),
    }

    def loss(x):
        b0, log_sd, log_noise, thr, fall = x
        P.set_override("logodds_fall", fall)
        s = G.summary_stats(G.assign_outcomes(lots, draws, b0, np.exp(log_sd), np.exp(log_noise), thr))
        return sum(((s[k] - v) / v) ** 2 for k, v in T.items())

    best = None
    for start in ([-4.3, np.log(1.25), np.log(2.4), -3.3, 0.8], [-4.1, np.log(1.15), np.log(2.0), -3.1, 0.6], [-4.5, np.log(1.4), np.log(2.8), -3.5, 1.0], [-4.0, np.log(0.95), np.log(2.2), -3.0, 0.7], [-3.9, np.log(0.85), np.log(1.8), -2.9, 0.6]):
        res = minimize(loss, start, method="Nelder-Mead", options={"maxiter": 1200, "xatol": 1e-3, "fatol": 1e-6})
        if best is None or res.fun < best.fun:
            best = res
    b0, log_sd, log_noise, thr, fall = best.x
    vals = {
        "logodds_fall": float(round(fall, 4)),
        "lot_intercept": float(round(b0, 4)),
        "lot_random_sd": float(round(np.exp(log_sd), 4)),
        "human_call_noise_sd": float(round(np.exp(log_noise), 4)),
        "human_call_threshold": float(round(thr, 4)),
    }
    P.set_override("logodds_fall", vals["logodds_fall"])
    s = G.summary_stats(G.assign_outcomes(lots, draws, vals["lot_intercept"], vals["lot_random_sd"],
                                          vals["human_call_noise_sd"], vals["human_call_threshold"]))
    out = {
        "note": "Written by scripts/calibrate.py - do not edit by hand.",
        "date": date.today().isoformat(), "n_lots": N, "seed": SEED, "loss": float(best.fun),
        "values": vals,
        "achieved": {k: float(round(v, 4)) for k, v in s.items()},
        "targets": {k: float(v) for k, v in T.items()},
    }
    path = P.CALIBRATED_PATH
    path.write_text(yaml.safe_dump(out, sort_keys=False))
    print(yaml.safe_dump(out, sort_keys=False))


if __name__ == "__main__":
    main()
