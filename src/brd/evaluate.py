from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats

from . import generator as G
from . import params as P
from . import risk as R
from .econ import Settings

ASSUMED_EFFECTS = ["or_sale_barn", "or_per_extra_source", "or_long_haul", "logodds_per_100lb_lighter",
                   "logodds_shrink_per_pct", "or_pre_arrival_vax_morbidity", "logodds_sex_heifer", "logodds_sex_mixed",
                   "logodds_temp_swing", "logodds_low_bunk", "logodds_mexico_import", "stressor_synergy_logodds"]


def make_world(seed: int, n_hist: int, n_test: int, scenario: str):
    rng = np.random.default_rng(seed)
    P.clear_overrides()
    true_rr = None
    if scenario == "misspecified":
        r2 = np.random.default_rng(seed + 99)
        for pid in ASSUMED_EFFECTS:
            v = P.get(pid)
            f = r2.uniform(0.4, 1.6)
            P.set_override(pid, float(np.exp(np.log(v) * f)) if pid.startswith("or_") else float(v * f))
        P.set_override("lot_random_sd", P.get("lot_random_sd") * 1.2)
    if scenario == "more_missing":
        P.set_override("missing_rates", {ch: {f: min(0.95, v * 1.5) for f, v in d.items()} for ch, d in P.get("missing_rates").items()})
    if scenario == "weaker_meta":
        true_rr = 0.75

    def world(n, start, end, prefix):
        lots = G.sample_lots(n, rng, start, end, prefix=prefix)
        dr = G.Draws.make(n, rng)
        if true_rr is not None:
            dr.rr = np.full(n, true_rr)
        t = G.assign_outcomes(lots, dr, P.get("lot_intercept"), P.get("lot_random_sd"),
                              P.get("human_call_noise_sd"), P.get("human_call_threshold"))
        t["true_rr"] = dr.rr
        return t, G.mask_missing(t, rng)

    h_truth, h_obs = world(n_hist, "2024-11-01", "2026-09-30", "H")
    t_truth, t_obs = world(n_test, "2026-10-01", "2027-09-30", "T")
    P.clear_overrides()
    return h_obs, t_truth, t_obs


def _min_lambda(ok, hi=2e6) -> float:
    if ok(0.0):
        return 0.0
    if not ok(hi):
        return hi
    lo = 0.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if ok(mid) else (mid, hi)
    return hi


def outcomes(H, p, rr, meta_frac, cfr, s: Settings, w_lb, treat):
    rr_eff = 1 - (1 - rr) * meta_frac
    cases = H * p * np.where(treat, rr_eff, 1.0)
    deaths = cases * cfr
    doses = H * treat + cases * s.doses_per_case
    cost = s.meta_cost * H * treat + cases * s.tx_cost + (cases - deaths) * s.perf_loss + deaths * s.death_cost(w_lb)
    return cases, deaths, doses, cost


def run_scenario(scenario: str, seed: int = 11, n_hist: int = 800, n_test: int = 600, s: Settings | None = None,
                 margin: float | None = None) -> pd.DataFrame:
    s = s or Settings()
    h_obs, truth, obs = make_world(seed, n_hist, n_test, scenario)
    model = R.RiskModel(h_obs, n_draws=100, seed=seed)
    _, lp, prior_w = model.prior(obs.drop(columns=["metaphylaxis_given"]))
    H = truth["head_count"].to_numpy()
    w = truth["arrival_weight_lb"].to_numpy()
    p_true = truth["p_case_no_meta"].to_numpy()
    lam_true = truth["true_logodds"].to_numpy()
    rr_true = truth["true_rr"].to_numpy()
    cfr = s.cfr
    t = s.decision_day
    Ft = float(G.onset_cdf(t))
    late_frac = (1 - Ft) * s.late_meta_fraction

    exp_p = prior_w @ R.SIG
    case_val = s.case_cost(w) + s.stewardship_per_dose * s.doses_per_case
    cur_treat = truth["metaphylaxis_given"].to_numpy().astype(bool)

    def arrival_rule(lam):
        d_meta, d_none = H * exp_p * s.meta_rr * cfr, H * exp_p * cfr
        return H * (s.meta_cost + s.stewardship_per_dose) + H * exp_p * s.meta_rr * case_val + lam * d_meta < H * exp_p * case_val + lam * d_none

    def est_deaths(treat, p_est, frac=1.0):
        return float((H * p_est * np.where(treat, 1 - (1 - s.meta_rr) * frac, 1.0) * cfr).sum())

    margin = 1 - (P.get("mortality_cap_margin") if margin is None else margin)
    cap = est_deaths(cur_treat, exp_p) * margin
    lam_arr = _min_lambda(lambda l: est_deaths(arrival_rule(l), exp_p) <= cap + 1e-9)
    model_treat = arrival_rule(lam_arr)

    rng = np.random.default_rng(seed + 1)
    pulls = rng.binomial(H, np.clip(p_true * Ft, 0, 1))
    dip = R.feed_dip_mean(lam_true) + rng.normal(0, P.get("feed_signal_noise_sd"), len(H))
    lik = stats.binom.pmf(pulls[:, None], H[:, None], np.clip(R.SIG[None, :] * Ft, 1e-9, 1 - 1e-9))
    lik *= stats.norm.pdf(dip[:, None], R.feed_dip_mean(R.GRID)[None, :], P.get("feed_signal_noise_sd"))
    post = prior_w * lik
    post /= np.clip(post.sum(axis=1, keepdims=True), 1e-300, None)
    post_p = post @ R.SIG
    remaining = (1 - Ft) * s.late_meta_fraction * (1 - s.meta_rr)

    def hybrid(lam):
        arr = arrival_rule(lam)
        benefit = H * post_p * remaining * (s.case_cost(w) + s.stewardship_per_dose * s.doses_per_case + lam * cfr)
        late = ~arr & (benefit > H * (s.meta_cost + s.stewardship_per_dose))
        return arr, late

    def hybrid_deaths(lam):
        arr, late = hybrid(lam)
        f = np.where(arr, s.meta_rr, np.where(late, 1 - (1 - s.meta_rr) * late_frac, 1.0))
        return float((H * post_p * f * cfr).sum())

    cap_k = float((H * post_p * np.where(cur_treat, s.meta_rr, 1.0) * cfr).sum()) * margin
    lam_k = _min_lambda(lambda l: hybrid_deaths(l) <= cap_k + 1e-9)
    hyb_arr, hyb_late = hybrid(lam_k)

    pol = {
        "current": (truth["metaphylaxis_given"].to_numpy().astype(bool), 1.0),
        "treat_all": (np.ones(len(H), bool), 1.0),
        "treat_none": (np.zeros(len(H), bool), 1.0),
        "model": (model_treat, 1.0),
    }
    res = {}
    for name, (treat, frac) in pol.items():
        res[name] = outcomes(H, p_true, rr_true, frac, cfr, s, w, treat)
    a_ = outcomes(H, p_true, rr_true, 1.0, cfr, s, w, hyb_arr)
    l_ = outcomes(H, p_true, rr_true, late_frac, cfr, s, w, hyb_late)
    res["model_dayk"] = tuple(np.where(hyb_arr, x, y) for x, y in zip(a_, l_))
    pol["model_dayk"] = (hyb_arr | hyb_late, None)
    c_meta = outcomes(H, p_true, rr_true, 1.0, cfr, s, w, np.ones(len(H), bool))
    c_none = outcomes(H, p_true, rr_true, 1.0, cfr, s, w, np.zeros(len(H), bool))
    obj_meta = c_meta[3] + s.stewardship_per_dose * c_meta[2]
    obj_none = c_none[3] + s.stewardship_per_dose * c_none[2]
    cur_true_deaths = outcomes(H, p_true, rr_true, 1.0, cfr, s, w, cur_treat)[1].sum()
    lam_o = _min_lambda(lambda l: np.where(obj_meta + l * c_meta[1] < obj_none + l * c_none[1], c_meta[1], c_none[1]).sum() <= cur_true_deaths + 1e-9)
    o = obj_meta + lam_o * c_meta[1] < obj_none + lam_o * c_none[1]
    res["oracle"] = tuple(np.where(o, a, b) for a, b in zip(c_meta, c_none))
    treated = {**{k: v[0] for k, v in pol.items()}, "oracle": o}

    head = H.sum()
    oracle_obj = res["oracle"][3].sum() + s.stewardship_per_dose * res["oracle"][2].sum()
    rows = []
    for name, (cases, deaths, doses, cost) in res.items():
        obj = cost.sum() + s.stewardship_per_dose * doses.sum()
        rows.append({"scenario": scenario, "policy": name, "lots_treated_pct": 100 * treated[name].mean(),
                     "cases_per_100": 100 * cases.sum() / head, "deaths_per_100": 100 * deaths.sum() / head,
                     "doses_per_head": doses.sum() / head, "cost_per_head": cost.sum() / head,
                     "regret_per_head": (obj - oracle_obj) / head})
    out = pd.DataFrame(rows)
    out["welfare_price_per_death"] = out["policy"].map({"model": lam_arr, "model_dayk": lam_k, "oracle": lam_o}).fillna(0.0)
    cur = out.loc[out.policy == "current"].iloc[0]
    out["saving_vs_current_per_head"] = cur["cost_per_head"] - out["cost_per_head"]
    out["dose_change_vs_current_pct"] = 100 * (out["doses_per_head"] / cur["doses_per_head"] - 1)
    return out
