from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import effects as E
from . import generator as G
from . import params as P
from . import risk as R
from .econ import Settings

ARRIVAL_OPTIONS = {
    "A": "Current practice",
    "B": "Metaphylaxis on arrival",
    "C": "Pull-and-treat only",
    "C+": "Pull-and-treat + extra rider pass",
    "D": "Pull-and-treat, re-decide on day {k}",
}
INPROG_OPTIONS = {"K": "Keep current course", "M": "Metaphylaxis now (late)", "X": "Extra rider pass from today"}
METRICS = ["cases", "deaths", "doses", "cost", "objective", "sick_days", "hosp_peak", "rider_h_day", "chute_min"]


def _rr_samples(s: Settings, n: int, rng) -> np.ndarray:
    lo, hi = np.log(s.meta_rr_low), np.log(s.meta_rr_high)
    return np.exp(np.clip(rng.normal(np.log(s.meta_rr), 0.2, n), lo, hi))


def sample_lambda(weights: np.ndarray, n: int, rng) -> np.ndarray:
    idx = rng.choice(len(R.GRID), size=n, p=weights)
    step = R.GRID[1] - R.GRID[0]
    return R.GRID[idx] + rng.uniform(-step / 2, step / 2, n)


def current_practice_meta(row: pd.Series, s: Settings) -> bool:
    if s.policy == "none":
        return False
    if s.policy == "all_sale_barn":
        return row["market_channel"] == "sale_barn"
    return row.get("buyer_risk_call") == "high"


@dataclass
class LotResult:
    lot_id: str
    table: pd.DataFrame
    samples: dict
    recommended: str
    p_best: float
    confident: bool
    note: str


def _outcomes(H, w_lb, p, rr, meta_frac_remaining, meta_on, extra_ride, s: Settings, days_left: int, meta_head_count):
    rr_eff = 1 - (1 - rr) * meta_frac_remaining
    cases = H * p * np.where(meta_on, rr_eff, 1.0)
    early = P.get("early_detection_mortality_rr")
    mort_mult = 1 - P.get("extra_riding_share_of_early_effect") * (1 - early) if extra_ride else 1.0
    cfr = s.cfr * mort_mult
    deaths = cases * cfr
    doses = meta_head_count * meta_on + cases * s.doses_per_case
    rider_h_day = (P.get("rider_minutes_per_pen_pass") / 60.0) if extra_ride else 0.0
    cost = (s.meta_cost * meta_head_count * meta_on + cases * s.tx_cost + (cases - deaths) * s.perf_loss
            + deaths * s.death_cost(w_lb) + rider_h_day * days_left * s.rider_wage)
    delay = P.get("detection_delay_days")[1 if extra_ride else 0]
    return {
        "cases": cases, "deaths": deaths, "doses": doses, "cost": cost,
        "objective": cost + s.stewardship_per_dose * doses,
        "sick_days": cases * delay,
        "hosp_peak": cases * R.onset_peak_density() * P.get("hospital_stay_days"),
        "rider_h_day": np.full_like(cases, rider_h_day, dtype=float),
        "chute_min": np.full_like(cases, P.get("chute_minutes_meta_per_head") * meta_head_count * float(np.any(meta_on)), dtype=float),
    }


def _late_meta_decision(H, w_lb, post_w: np.ndarray, t: int, s: Settings) -> np.ndarray:
    remaining = (1 - G.onset_cdf(t)) * s.late_meta_fraction * (1 - s.meta_rr)
    exp_p = post_w @ R.SIG
    benefit = H * exp_p * remaining * (s.case_cost(w_lb) + s.stewardship_per_dose * s.doses_per_case)
    costm = H * (s.meta_cost + s.stewardship_per_dose)
    return benefit > costm


def evaluate_lot(row: pd.Series, post_w: np.ndarray, s: Settings, n: int = 400, seed: int = 0,
                 use_feed: bool = True) -> LotResult:
    rng = np.random.default_rng(seed)
    H = int(row["head_count"])
    w_lb = float(row["arrival_weight_lb"])
    lam = sample_lambda(post_w, n, rng)
    p = E.sigmoid(lam)
    rr = _rr_samples(s, n, rng)
    status = row.get("status", "arriving")
    k = int(row.get("days_on_feed", 0)) if pd.notna(row.get("days_on_feed", np.nan)) else 0
    out: dict[str, dict] = {}

    if status == "in_progress":
        given = R._to_bool(row.get("metaphylaxis_given"))
        days_left = max(45 - k, 0)
        frac_left = (1 - G.onset_cdf(k)) * s.late_meta_fraction
        base_meta = np.full(n, given)
        out["K"] = _outcomes(H, w_lb, p, rr, 1.0, base_meta, False, s, days_left, 0 if given else 0)
        if given:
            out["K"]["doses"] = out["K"]["doses"] + H
        if not given:
            out["M"] = _outcomes(H, w_lb, p, rr, frac_left, np.ones(n, bool), False, s, days_left, H)
        out["X"] = _outcomes(H, w_lb, p, rr, 1.0, base_meta, True, s, days_left, 0)
        if given:
            out["X"]["doses"] = out["X"]["doses"] + H
        labels = INPROG_OPTIONS
    else:
        t = s.decision_day
        cur = current_practice_meta(row, s)
        out["A"] = _outcomes(H, w_lb, p, rr, 1.0, np.full(n, cur), False, s, 45, H)
        out["B"] = _outcomes(H, w_lb, p, rr, 1.0, np.ones(n, bool), False, s, 45, H)
        out["C"] = _outcomes(H, w_lb, p, rr, 1.0, np.zeros(n, bool), False, s, 45, H)
        out["C+"] = _outcomes(H, w_lb, p, rr, 1.0, np.zeros(n, bool), True, s, 45, H)
        Ft = float(G.onset_cdf(t))
        pulls = rng.binomial(H, np.clip(p * Ft, 0, 1))
        dip = R.feed_dip_mean(lam) + rng.normal(0, P.get("feed_signal_noise_sd"), n) if use_feed else None
        prior_w = post_w[None, :]
        lik = stats.binom.pmf(pulls[:, None], H, np.clip(R.SIG[None, :] * Ft, 1e-9, 1 - 1e-9))
        if use_feed:
            lik = lik * stats.norm.pdf(dip[:, None], R.feed_dip_mean(R.GRID)[None, :], P.get("feed_signal_noise_sd"))
        pw = prior_w * lik
        pw = pw / np.clip(pw.sum(axis=1, keepdims=True), 1e-300, None)
        decide = _late_meta_decision(H, w_lb, pw, t, s)
        frac_left = (1 - Ft) * s.late_meta_fraction
        out["D"] = _outcomes(H, w_lb, p, rr, frac_left, decide, False, s, 45, H)
        out["D"]["chute_min"] = np.where(decide, P.get("chute_minutes_meta_per_head") * H, 0.0)
        out["D"]["p_treat"] = decide.astype(float)
        labels = {k2: v.format(k=t) for k2, v in ARRIVAL_OPTIONS.items()}
        labels["A"] = "Current practice (" + ("metaphylaxis" if cur else "pull-and-treat") + ")"

    rows = []
    for o, m in out.items():
        r = {"option": o, "label": labels[o]}
        for met in METRICS:
            v = m[met]
            r[met] = float(np.mean(v))
            r[met + "_lo"] = float(np.quantile(v, 0.1))
            r[met + "_hi"] = float(np.quantile(v, 0.9))
        if "p_treat" in m:
            r["p_treat"] = float(np.mean(m["p_treat"]))
        rows.append(r)
    tab = pd.DataFrame(rows)
    opts = [o for o in out if o != "A"]
    obj = np.vstack([out[o]["objective"] for o in opts])
    best_each = np.argmin(obj, axis=0)
    rec_i = int(np.argmin(obj.mean(axis=1)))
    rec = opts[rec_i]
    p_best = float(np.mean(best_each == rec_i))
    tab["p_best"] = [float(np.mean(best_each == opts.index(o))) if o in opts else np.nan for o in tab["option"]]
    srt = np.sort(obj.mean(axis=1))
    gap = (srt[1] - srt[0]) / H if len(srt) > 1 else np.inf
    if status != "in_progress":
        p_meta = float(np.mean(out["B"]["objective"] < np.minimum(out["C"]["objective"], out["C+"]["objective"])))
        p_best = p_meta if rec == "B" else 1 - p_meta
        confident = p_best >= 0.7 or gap >= 5.0
    else:
        p_meta = float("nan")
        confident = p_best >= 0.6 or gap >= 5.0
    base = "A" if status != "in_progress" else "K"
    tab["vs_current_cost_per_head"] = (tab["cost"] - tab.loc[tab.option == base, "cost"].iloc[0]) / H
    tab["vs_current_doses_per_head"] = (tab["doses"] - tab.loc[tab.option == base, "doses"].iloc[0]) / H
    if status != "in_progress" and rec == "D":
        pt = float(np.mean(out["D"]["p_treat"]))
        note = (f"No metaphylaxis on arrival; review the day-{s.decision_day} pull and feed records. They would trigger "
                f"metaphylaxis in {pt:.0%} of plausible scenarios. Metaphylaxis on arrival pays off in only {p_meta:.0%}."
                + ("" if confident else " The arrival information alone cannot support a confident call."))
    elif status != "in_progress":
        note = (f"{labels[rec]}: the metaphylaxis-vs-pull-and-treat call goes this way in {p_best:.0%} of plausible scenarios."
                + ("" if confident else " The available information cannot support a confident call - see what information would settle it."))
    else:
        note = (f"{labels[rec]} is best in {p_best:.0%} of plausible scenarios."
                + ("" if confident else " The available information cannot support a confident choice."))
    res = LotResult(row["lot_id"], tab, out, rec, p_best, confident, note)
    res.p_meta = p_meta
    return res


def value_of_information(row: pd.Series, draws: pd.DataFrame, lp: np.ndarray, s: Settings, sd: float) -> pd.DataFrame:
    H = int(row["head_count"])
    w_lb = float(row["arrival_weight_lb"])
    em = R.expected_morbidity(lp, sd)
    case_val = float(s.case_cost(w_lb)) + s.stewardship_per_dose * s.doses_per_case
    obj_meta = H * (s.meta_cost + s.stewardship_per_dose) + H * em * s.meta_rr * case_val
    obj_none = H * em * case_val
    now = min(obj_meta.mean(), obj_none.mean())
    rows = []
    for f in R.IMPUTABLE:
        if not pd.isna(row.get(f)):
            continue
        v = draws[f]
        if v.dtype == object or f in ("preconditioning", "pre_arrival_vaccinated", "origin_state"):
            groups = v.astype(str)
        else:
            groups = pd.qcut(v.astype(float).rank(method="first"), 5, labels=False)
        g = pd.DataFrame({"g": groups.to_numpy(), "m": obj_meta, "n": obj_none}).groupby("g").agg(["mean", "size"])
        wts = g[("m", "size")] / g[("m", "size")].sum()
        known = (wts * np.minimum(g[("m", "mean")], g[("n", "mean")])).sum()
        rows.append({"field": f, "value_per_head": max(now - known, 0.0) / H})
    return pd.DataFrame(rows).sort_values("value_per_head", ascending=False) if rows else pd.DataFrame(columns=["field", "value_per_head"])
