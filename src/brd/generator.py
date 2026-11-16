from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy import stats

from . import effects as E
from . import params as P

FEED_REF_LOGODDS = math.log(0.063 / (1 - 0.063))
CHANNELS = ["sale_barn", "ranch_direct", "backgrounder", "mexico_import"]
MONTH_WEIGHTS = np.array([8, 7, 8, 8, 8, 7, 7, 8, 9, 11, 10, 9], dtype=float)

ORIGIN_MIX = {
    ("sale_barn", "TX"): {"Southeast": 0.45, "Midsouth": 0.25, "TX_local": 0.20, "OK_KS": 0.10},
    ("sale_barn", "KS"): {"OK_KS": 0.40, "Midsouth": 0.25, "Southeast": 0.20, "Mountain": 0.15},
    ("ranch_direct", "TX"): {"TX_local": 0.55, "OK_KS": 0.25, "Mountain": 0.20},
    ("ranch_direct", "KS"): {"OK_KS": 0.50, "Mountain": 0.35, "TX_local": 0.15},
    ("backgrounder", "TX"): {"TX_local": 0.50, "OK_KS": 0.50},
    ("backgrounder", "KS"): {"OK_KS": 0.70, "Mountain": 0.30},
    ("mexico_import", "TX"): {"Mexico_NM": 1.0},
    ("mexico_import", "KS"): {"Mexico_NM": 1.0},
}
PRECON_MIX = {
    "sale_barn": {"none": 0.70, "VAC24": 0.12, "VAC34": 0.10, "VAC45": 0.08},
    "ranch_direct": {"none": 0.20, "VAC24": 0.15, "VAC34": 0.20, "VAC45": 0.45},
    "backgrounder": {"none": 0.15, "VAC24": 0.10, "VAC34": 0.15, "VAC45": 0.60},
    "mexico_import": {"none": 0.60, "VAC24": 0.30, "VAC34": 0.10, "VAC45": 0.00},
}
WEIGHT_SHIFT = {"sale_barn": -20, "ranch_direct": 30, "backgrounder": 60, "mexico_import": -90}
STATE_OF_ORIGIN = {"TX_local": ["TX"], "OK_KS": ["OK", "KS"], "Southeast": ["AL", "GA", "MS", "TN", "FL"],
                   "Midsouth": ["AR", "MO", "LA"], "Mountain": ["CO", "WY", "NM"], "Mexico_NM": ["MX"]}


def _haversine_mi(lat1, lon1, lat2, lon2):
    r = 3958.8
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dl = np.radians(lat2 - lat1), np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * r * np.arcsin(np.sqrt(a))


def _choice(rng, mix: dict, size=None):
    keys, probs = zip(*mix.items())
    probs = np.array(probs, float) / sum(probs)
    return rng.choice(keys, p=probs, size=size)


def sample_lots(n: int, rng: np.random.Generator, start: str, end: str, prefix: str = "L") -> pd.DataFrame:
    cfg = P.load_yards()
    yards, origins = cfg["yards"], cfg["origins"]
    yid = list(yards)
    cap = np.array([yards[y]["one_time_capacity_head"] for y in yid], float)

    days = pd.date_range(start, end, freq="D")
    w = MONTH_WEIGHTS[days.month - 1]
    dates = rng.choice(days, size=n, p=w / w.sum())

    rows = []
    for i in range(n):
        y = rng.choice(yid, p=cap / cap.sum())
        Y = yards[y]
        st = "TX" if "TX" in Y["region"] else "KS"
        ch = _choice(rng, Y["channel_mix"])
        region = _choice(rng, ORIGIN_MIX[(ch, st)])
        o = origins[region]
        dist = _haversine_mi(o["lat"], o["lon"], Y["lat"], Y["lon"]) * rng.uniform(1.15, 1.35)
        haul = max(1.0, dist / rng.uniform(45, 55) + rng.uniform(0.5, 2.0))
        head = int(np.clip(round(rng.lognormal(math.log(95), 0.5)), 25, 400))
        if ch == "ranch_direct":
            n_src = 1
        elif ch == "backgrounder":
            n_src = int(rng.integers(1, 5))
        elif ch == "mexico_import":
            n_src = int(rng.integers(2, 9))
        else:
            n_src = int(np.clip(rng.poisson(6) + 2, 2, 20))
        sex = _choice(rng, {"steer": 0.55, "heifer": 0.33, "mixed": 0.12 if ch != "sale_barn" else 0.22})
        wt = float(np.clip(rng.normal(Y["weight_mean_lb"] + WEIGHT_SHIFT[ch], Y["weight_sd_lb"]), 350, 1000))
        precon = _choice(rng, PRECON_MIX[ch])
        vacc = bool(precon != "none" or rng.random() < 0.2)
        shrink = float(np.clip(rng.normal(3.0 + 0.22 * haul, 1.2), 1.0, 14.0))
        pay = wt / (1 - shrink / 100)
        month = pd.Timestamp(dates[i]).month
        base = 27 + 3.5 * math.cos(2 * math.pi * (month - 3) / 12) + (1.5 if st == "KS" else 0.0)
        trange = float(np.clip(rng.normal(base, 4.0), 10, 45))
        rows.append(
            dict(
                lot_id=f"{prefix}{i + 1:05d}", yard_id=y, arrival_date=pd.Timestamp(dates[i]).date().isoformat(),
                head_count=head, sex=sex, arrival_weight_lb=round(wt, 0),
                pen_area_m2_per_head=round(rng.normal(Y["pen_area_m2_per_head"], 1.5), 1),
                bunk_cm_per_head=round(rng.normal(Y["bunk_cm_per_head"], 2.0), 1),
                market_channel=ch, pay_weight_lb=round(pay, 0),
                origin_state=rng.choice(STATE_OF_ORIGIN[region]), origin_region=region,
                haul_hours=round(haul, 1), n_sources=n_src, preconditioning=precon,
                pre_arrival_vaccinated=vacc, temp_range_wk1_f=round(trange, 1),
            )
        )
    df = pd.DataFrame(rows).sort_values("arrival_date").reset_index(drop=True)
    return E.derive(df)


@dataclass
class Draws:
    z_re: np.ndarray
    z_human: np.ndarray
    u_cases: np.ndarray
    u_cases_cf: np.ndarray
    rr: np.ndarray

    @classmethod
    def make(cls, n: int, rng: np.random.Generator) -> "Draws":
        rr_e = P.entry("meta_rr_morbidity")
        lo, hi, mid = rr_e["low"], rr_e["high"], rr_e["value"]
        rr = np.exp(np.clip(rng.normal(np.log(mid), 0.2, n), np.log(lo), np.log(hi)))
        return cls(rng.standard_normal(n), rng.standard_normal(n), rng.random(n), rng.random(n), rr)


def assign_outcomes(lots: pd.DataFrame, draws: Draws, b0: float, sd: float, noise_sd: float, thresh: float) -> pd.DataFrame:
    df = lots.copy()
    lp = E.fixed_logodds(df, intercept=b0, yard_offset=P.get("yard_hidden_effect")).to_numpy() + sd * draws.z_re
    p_nometa = E.sigmoid(lp)
    n = df["head_count"].to_numpy()

    perceived = lp + noise_sd * draws.z_human
    call_high = perceived > thresh
    rr = draws.rr
    p_obs = np.where(call_high, p_nometa * rr, p_nometa)

    cases = stats.binom.ppf(draws.u_cases, n, p_obs).astype(int)
    cases_cf = stats.binom.ppf(draws.u_cases_cf, n, p_nometa).astype(int)
    cut = P.get("high_risk_cutoff")

    df["true_logodds"] = lp
    df["p_case_no_meta"] = p_nometa
    df["buyer_risk_call"] = np.where(call_high, "high", "low")
    df["metaphylaxis_given"] = call_high
    df["meta_rr"] = np.where(call_high, rr, 1.0)
    df["p_case_observed"] = p_obs
    df["cases_45"] = cases
    df["morbidity_45"] = cases / n
    df["high_observed"] = df["morbidity_45"] >= cut
    df["high_counterfactual"] = cases_cf / n >= cut
    return df


def summary_stats(df: pd.DataFrame) -> dict:
    hi = df["high_observed"]
    cf = df["high_counterfactual"]
    call = df["buyer_risk_call"] == "high"
    return {
        "prev_high_lots": hi.mean(),
        "mean_morbidity": df["morbidity_45"].mean(),
        "mean_morbidity_high": df.loc[hi, "morbidity_45"].mean(),
        "mean_morbidity_low": df.loc[~hi, "morbidity_45"].mean(),
        "human_sensitivity": (call & cf).sum() / max(cf.sum(), 1),
        "human_specificity": (~call & ~cf).sum() / max((~cf).sum(), 1),
        "share_called_high": call.mean(),
        "fall_incidence": (lambda f: f["cases_45"].sum() / f["head_count"].sum())(
            df[pd.to_datetime(df["arrival_date"]).dt.month.isin([9, 10, 11])]),
        "mean_lot_size": df["head_count"].mean(),
    }


def _trunc_gamma_days(rng, k, mean, size, lo=1, hi=45):
    scale = mean / k
    a, b = stats.gamma.cdf([lo - 0.5, hi + 0.49], k, scale=scale)
    u = rng.uniform(a, b, size)
    return np.clip(np.round(stats.gamma.ppf(u, k, scale=scale)), lo, hi).astype(int)


def feed_ramp(days):
    days = np.asarray(days, float)
    return 1.4 + (2.5 - 1.4) * (1 - np.exp(-days / 6.0))


def onset_cdf(day):
    k, mean = P.get("onset_gamma_shape"), P.get("onset_mean_day")
    scale = mean / k
    a, b = stats.gamma.cdf([0.5, 45.49], k, scale=scale)
    return np.clip((stats.gamma.cdf(np.asarray(day, float) + 0.49, k, scale=scale) - a) / (b - a), 0, 1)


def add_deaths_and_daily(df: pd.DataFrame, rng: np.random.Generator) -> tuple[pd.DataFrame, pd.DataFrame]:
    k, mean = P.get("onset_gamma_shape"), P.get("onset_mean_day")
    cfr = P.get("case_fatality")
    lag = P.get("death_lag_mean_days")
    sick_red = P.get("sick_feeding_reduction")
    dip = P.get("feed_stress_dip_logodds")
    ref = FEED_REF_LOGODDS
    days = np.arange(0, 46)
    ramp = feed_ramp(days)

    deaths_tot, recs = [], []
    for r in df.itertuples(index=False):
        c = int(r.cases_45)
        pull_days = _trunc_gamma_days(rng, k, mean, c) if c else np.array([], int)
        dies = rng.random(c) < cfr
        death_days = pull_days[dies] + np.round(rng.gamma(2.0, lag / 2.0, dies.sum())).astype(int)
        death_days = death_days[death_days <= 45]
        pulls = np.bincount(pull_days, minlength=46)[:46]
        deaths = np.bincount(death_days, minlength=46)[:46] if len(death_days) else np.zeros(46, int)
        sick = np.zeros(46)
        for d0 in pull_days:
            sick[max(d0 - 2, 0): min(d0 + 5, 46)] += 1
        sick_frac = sick / r.head_count
        stress = np.zeros(46)
        stress[2:6] = dip * max(r.true_logodds - ref, 0.0)
        feed = ramp * (1 - sick_red * sick_frac) * (1 - stress) * rng.normal(1.0, 0.025, 46)
        deaths_tot.append(len(death_days))
        for d in days:
            recs.append((r.lot_id, int(d), int(pulls[d]), int(deaths[d]), round(float(feed[d]), 3)))
    out = df.copy()
    out["deaths_45"] = deaths_tot
    out["mortality_45"] = out["deaths_45"] / out["head_count"]
    daily = pd.DataFrame(recs, columns=["lot_id", "day", "pulls", "deaths", "feed_pct_bw"])
    return out, daily


def mask_missing(truth: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    rates = P.get("missing_rates")
    obs = truth.copy()
    for f in {f for fields in rates.values() for f in fields}:
        if obs[f].dtype == bool or obs[f].dtype.kind in "iu":
            obs[f] = obs[f].astype(object) if obs[f].dtype == bool else obs[f].astype(float)
    for ch, fields in rates.items():
        idx = obs.index[obs["market_channel"] == ch]
        for f, pr in fields.items():
            m = rng.random(len(idx)) < pr
            obs.loc[idx[m], f] = np.nan
    obs["shrink_pct"] = (obs["pay_weight_lb"] - obs["arrival_weight_lb"]) / obs["pay_weight_lb"] * 100
    obs["long_haul"] = np.where(obs["haul_hours"].isna(), np.nan, (obs["haul_hours"] >= P.get("long_haul_hours")).astype(float))
    obs["preconditioning"] = obs["preconditioning"].astype(object)
    obs["pre_arrival_vaccinated"] = obs["pre_arrival_vaccinated"].astype(object)
    return obs
