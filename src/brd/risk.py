from __future__ import annotations

from functools import lru_cache

import numpy as np
import pandas as pd
from scipy import stats
from scipy.optimize import brentq

from . import effects as E
from . import generator as G
from . import params as P

GRID = np.linspace(-9.0, 2.5, 231)
SIG = E.sigmoid(GRID)
IMPUTABLE = ["pay_weight_lb", "origin_state", "haul_hours", "n_sources", "preconditioning", "pre_arrival_vaccinated"]
RISK_FIELDS = ["arrival_weight_lb", "sex", "market_channel", "pay_weight_lb", "haul_hours", "n_sources",
               "preconditioning", "pre_arrival_vaccinated", "temp_range_wk1_f", "bunk_cm_per_head"]
_GH_X, _GH_W = np.polynomial.hermite.hermgauss(24)


def _to_bool(v):
    return str(v).lower() in ("true", "1", "1.0")


def sample_inputs(lots: pd.DataFrame, history: pd.DataFrame, n: int, rng: np.random.Generator) -> pd.DataFrame:
    rep = lots.loc[lots.index.repeat(n)].reset_index(drop=True)
    rep["draw"] = np.tile(np.arange(n), len(lots))
    h = history
    shrink_fit = h.dropna(subset=["haul_hours", "pay_weight_lb"])
    s_obs = (shrink_fit["pay_weight_lb"] - shrink_fit["arrival_weight_lb"]) / shrink_fit["pay_weight_lb"] * 100
    slope, icpt = np.polyfit(shrink_fit["haul_hours"], s_obs, 1)
    pay_missing = rep["pay_weight_lb"].isna().to_numpy()
    for f in IMPUTABLE:
        if f == "pay_weight_lb":
            continue
        miss = rep[f].isna()
        if not miss.any():
            continue
        rep[f] = rep[f].astype(object)
        for (ch, yd), idx in rep[miss].groupby(["market_channel", "yard_id"]).groups.items():
            pool = h[(h["market_channel"] == ch) & (h["yard_id"] == yd)][f].dropna()
            if len(pool) < 20:
                pool = h[h["market_channel"] == ch][f].dropna()
            if len(pool) == 0:
                pool = h[f].dropna()
            rep.loc[idx, f] = rng.choice(pool.to_numpy(), len(idx))
    if pay_missing.any():
        sh = np.clip(icpt + slope * rep.loc[pay_missing, "haul_hours"].astype(float) + rng.normal(0, 1.2, pay_missing.sum()), 1, 14)
        rep.loc[pay_missing, "pay_weight_lb"] = rep.loc[pay_missing, "arrival_weight_lb"] / (1 - sh / 100)
    rep["pre_arrival_vaccinated"] = rep["pre_arrival_vaccinated"].map(_to_bool)
    rep["n_sources"] = rep["n_sources"].astype(float)
    rep["haul_hours"] = rep["haul_hours"].astype(float)
    rep = rep.drop(columns=[c for c in ("shrink_pct", "long_haul", "arrival_quarter", "season") if c in rep])
    return E.derive(rep)


def _vax_credit_shift(credit: float) -> float:
    return float(np.log(1 - min(max(credit, 0.0), 0.9)))


def expected_morbidity(lp: np.ndarray, sd: float) -> np.ndarray:
    return (E.sigmoid(np.asarray(lp)[..., None] + sd * np.sqrt(2) * _GH_X) * _GH_W).sum(-1) / np.sqrt(np.pi)


def learn_yard_offsets(history: pd.DataFrame, n: int = 30, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    draws = sample_inputs(history, history, n, rng)
    lp = E.fixed_logodds(draws).to_numpy().reshape(len(history), n)
    sd = P.get("lot_random_sd")
    rr = np.where(history["metaphylaxis_given"].map(_to_bool), P.get("meta_rr_morbidity"), 1.0)
    head = history["head_count"].to_numpy()
    rows = []
    k = P.get("yard_offset_shrinkage_cases")
    for y in sorted(history["yard_id"].unique()):
        m = (history["yard_id"] == y).to_numpy()
        obs = history.loc[m, "cases_45"].sum()

        def gap(off):
            return (head[m] * rr[m] * expected_morbidity(lp[m] + off, sd).mean(axis=1)).sum() - obs

        raw = brentq(gap, -3, 3)
        w = obs / (obs + k)
        exp0 = gap(0.0) + obs
        rows.append({"yard_id": y, "lots": int(m.sum()), "observed_cases": int(obs), "expected_cases_no_offset": float(exp0),
                     "raw_offset": float(raw), "offset": float(raw * w)})
    return pd.DataFrame(rows)


def prior_from_lp(lp_draws: np.ndarray, sd: float) -> np.ndarray:
    out = np.empty((lp_draws.shape[0], len(GRID)))
    for a in range(0, lp_draws.shape[0], 50):
        dens = stats.norm.pdf(GRID[None, None, :], lp_draws[a:a + 50, :, None], sd).mean(axis=1)
        out[a:a + 50] = dens / dens.sum(axis=1, keepdims=True)
    return out


def buyer_call_likelihood(call) -> np.ndarray:
    if call not in ("high", "low"):
        return np.ones(len(GRID))
    p_high = 1 - stats.norm.cdf((P.get("human_call_threshold") - GRID) / P.get("human_call_noise_sd"))
    return p_high if call == "high" else 1 - p_high


def feed_dip_mean(lam: np.ndarray) -> np.ndarray:
    return P.get("feed_stress_dip_logodds") * np.clip(lam - G.FEED_REF_LOGODDS, 0, None)


def observed_feed_dip(daily_lot: pd.DataFrame) -> float | None:
    d = daily_lot[(daily_lot["day"] >= 2) & (daily_lot["day"] <= 5)]
    if len(d) < 4:
        return None
    return float(1 - (d["feed_pct_bw"] / G.feed_ramp(d["day"])).mean())


def likelihood(head: int, pulls_to_k: int, k: int, rr: float, feed_dip: float | None) -> np.ndarray:
    Fk = float(G.onset_cdf(k))
    p = np.clip(SIG * rr * Fk, 1e-9, 1 - 1e-9)
    lik = stats.binom.pmf(pulls_to_k, head, p)
    if feed_dip is not None:
        lik = lik * stats.norm.pdf(feed_dip, feed_dip_mean(GRID), P.get("feed_signal_noise_sd"))
    return lik


def summarize(w: np.ndarray) -> dict:
    cdf = np.cumsum(w)
    q = lambda a: float(SIG[min(np.searchsorted(cdf, a), len(GRID) - 1)])
    cut = E.logit(P.get("high_risk_cutoff"))
    return {"exp_morbidity": float((w * SIG).sum()), "lo": q(0.1), "hi": q(0.9), "p_high": float(w[GRID >= cut].sum())}


class RiskModel:
    def __init__(self, history: pd.DataFrame, n_draws: int = 200, seed: int = 0, use_feed: bool = True,
                 use_pulls: bool = True, arrival_vax_credit: float = 0.0):
        self.history = history
        self.n = n_draws
        self.seed = seed
        self.use_feed = use_feed
        self.use_pulls = use_pulls
        self.vax_shift = _vax_credit_shift(arrival_vax_credit)
        self.offsets_table = learn_yard_offsets(history)
        self.offsets = dict(zip(self.offsets_table["yard_id"], self.offsets_table["offset"]))
        self.sd = P.get("lot_random_sd")

    def prior(self, lots: pd.DataFrame):
        rng = np.random.default_rng(self.seed)
        draws = sample_inputs(lots.reset_index(drop=True), self.history, self.n, rng)
        lp = E.fixed_logodds(draws, yard_offset=self.offsets).to_numpy().reshape(len(lots), self.n) + self.vax_shift
        w = prior_from_lp(lp, self.sd)
        if "buyer_risk_call" in lots:
            lik = np.vstack([buyer_call_likelihood(c) for c in lots["buyer_risk_call"]])
            w = w * lik
            w = w / w.sum(axis=1, keepdims=True)
        return draws, lp, w

    def assess(self, lots: pd.DataFrame, daily: pd.DataFrame | None = None) -> tuple[pd.DataFrame, np.ndarray, np.ndarray]:
        lots = lots.reset_index(drop=True)
        _, lp, prior_w = self.prior(lots)
        post = prior_w.copy()
        rows = []
        for i, r in lots.iterrows():
            k = int(r.get("days_on_feed", -1)) if pd.notna(r.get("days_on_feed", np.nan)) else -1
            info = "arrival information only"
            if daily is not None and k >= 1 and (self.use_pulls or self.use_feed):
                d = daily[daily["lot_id"] == r["lot_id"]]
                d = d[d["day"] <= k]
                pulls = int(d["pulls"].sum())
                dip = observed_feed_dip(d) if self.use_feed else None
                rr = P.get("meta_rr_morbidity") if _to_bool(r.get("metaphylaxis_given")) else 1.0
                lik = likelihood(int(r["head_count"]), pulls if self.use_pulls else 0, min(k, 45) if self.use_pulls else 0, rr, dip)
                w = prior_w[i] * lik
                if w.sum() > 0:
                    post[i] = w / w.sum()
                info = f"updated with day 0-{k} records ({pulls} pulls" + (", feed dip" if dip is not None else "") + ")"
            s_prior, s_post = summarize(prior_w[i]), summarize(post[i])
            known = np.mean([not pd.isna(r.get(f)) for f in RISK_FIELDS])
            rows.append({"lot_id": r["lot_id"], "completeness": float(known), "basis": info,
                         "prior_exp": s_prior["exp_morbidity"], "prior_p_high": s_prior["p_high"],
                         **{k2: v for k2, v in s_post.items()}})
        return pd.DataFrame(rows), prior_w, post


@lru_cache(maxsize=1)
def onset_peak_density() -> float:
    d = np.diff(np.concatenate([[0.0], G.onset_cdf(np.arange(1, 46))]))
    return float(d.max())


FACTOR_FIELDS = {
    "Preconditioning / weaning": ["preconditioning"], "Pre-arrival vaccination": ["pre_arrival_vaccinated"],
    "Commingled sources": ["n_sources"], "Long haul (>=6 h)": ["haul_hours"],
    "Transport shrink": ["pay_weight_lb", "haul_hours"],
    "Stacked stressors (risk threshold)": ["haul_hours", "n_sources", "preconditioning"],
}


def explain(row: pd.Series, history: pd.DataFrame) -> pd.DataFrame:
    r = row.copy()
    filled = []
    for f in IMPUTABLE:
        if pd.isna(r.get(f)):
            pool = history[(history["market_channel"] == r["market_channel"])][f].dropna()
            if f == "pay_weight_lb":
                r[f] = r["arrival_weight_lb"] / 0.96
            elif pool.dtype == object or f in ("preconditioning", "origin_state", "pre_arrival_vaccinated"):
                r[f] = pool.astype(str).mode().iloc[0] if len(pool) else "none"
            else:
                r[f] = float(pool.median()) if len(pool) else 1.0
            filled.append(f)
    r["pre_arrival_vaccinated"] = _to_bool(r["pre_arrival_vaccinated"])
    for c in ("n_sources", "haul_hours", "pay_weight_lb"):
        r[c] = float(r[c])
    c = E.contributions(r.drop(labels=[x for x in ("shrink_pct", "long_haul", "arrival_quarter", "season") if x in r.index]))
    df = pd.DataFrame({"factor": list(c), "log_odds": list(c.values())})
    df["domain"] = df["factor"].map(E.DOMAINS)
    df["unknown"] = df["factor"].map(lambda f: any(x in filled for x in FACTOR_FIELDS.get(f, [])))
    df = df[df["log_odds"].abs() > 1e-9]
    return df.sort_values("log_odds", key=abs, ascending=False).reset_index(drop=True)
