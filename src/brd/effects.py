from __future__ import annotations

import numpy as np
import pandas as pd

from . import params as P

DOMAINS = {
    "Arrival weight": "biological",
    "Sex mix": "biological",
    "Sale-barn purchase": "operational",
    "Mexico-origin (hypothesis)": "operational",
    "Preconditioning / weaning": "operational",
    "Pre-arrival vaccination": "operational",
    "Commingled sources": "operational",
    "Long haul (>=6 h)": "operational",
    "Transport shrink": "operational",
    "Bunk space": "operational",
    "Stacked stressors (risk threshold)": "operational",
    "Arrival season": "environmental",
    "Week-1 temperature swings": "environmental",
}


def season_of(month: pd.Series) -> pd.Series:
    return month.map(lambda m: "winter" if m in (12, 1, 2) else "spring" if m in (3, 4, 5) else "summer" if m in (6, 7, 8) else "fall")


def derive(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["arrival_date"] = pd.to_datetime(out["arrival_date"])
    out["arrival_quarter"] = out["arrival_date"].dt.quarter
    out["season"] = season_of(out["arrival_date"].dt.month)
    out["shrink_pct"] = (out["pay_weight_lb"] - out["arrival_weight_lb"]) / out["pay_weight_lb"] * 100
    out["long_haul"] = np.where(out["haul_hours"].isna(), np.nan, (out["haul_hours"] >= P.get("long_haul_hours")).astype(float))
    return out


def _flag(series_bool, isna):
    return np.where(isna, np.nan, series_bool.astype(float))


def stressors(d: pd.DataFrame) -> pd.DataFrame:
    s = pd.DataFrame(index=d.index)
    s["long_haul"] = _flag(d["haul_hours"] >= P.get("long_haul_hours"), d["haul_hours"].isna())
    s["commingled"] = _flag(d["n_sources"] >= P.get("stressor_commingling_sources"), d["n_sources"].isna())
    s["freshly_weaned"] = _flag(d["preconditioning"].isin(["none", "VAC24"]), d["preconditioning"].isna())
    s["light_weight"] = (d["arrival_weight_lb"] < P.get("stressor_light_weight_lb")).astype(float)
    return s


def fixed_logodds(df: pd.DataFrame, intercept: float | None = None, yard_offset: dict | None = None) -> pd.Series:
    b0 = P.get("lot_intercept") if intercept is None else intercept
    d = derive(df) if "season" not in df else df
    lp = pd.Series(b0, index=d.index, dtype=float)
    for k, v in contribution_frame(d).items():
        lp += v
    if yard_offset:
        lp += d["yard_id"].map(yard_offset).fillna(0.0).astype(float)
    return lp


def contribution_frame(d: pd.DataFrame) -> dict[str, pd.Series]:
    ch = d["market_channel"]
    frac = P.get("precon_effect_fraction")
    seas = dict(zip(["winter", "spring", "summer"], P.get("logodds_season")))
    seas["fall"] = P.get("logodds_fall")
    st = stressors(d)
    n_stress = st.fillna(0).sum(axis=1)
    return {
        "Sale-barn purchase": np.log(P.get("or_sale_barn")) * (ch == "sale_barn"),
        "Mexico-origin (hypothesis)": P.get("logodds_mexico_import") * (ch == "mexico_import"),
        "Preconditioning / weaning": np.log(P.get("or_preconditioned")) * d["preconditioning"].map(frac).astype(float),
        "Pre-arrival vaccination": np.log(P.get("or_pre_arrival_vax_morbidity")) * d["pre_arrival_vaccinated"].astype(float),
        "Commingled sources": np.log(P.get("or_per_extra_source")) * (d["n_sources"].astype(float) - 1).clip(0, 9),
        "Long haul (>=6 h)": np.log(P.get("or_long_haul")) * d["long_haul"].astype(float),
        "Arrival weight": P.get("logodds_per_100lb_lighter") * (700 - d["arrival_weight_lb"]) / 100,
        "Transport shrink": P.get("logodds_shrink_per_pct") * (d["shrink_pct"] - 4).clip(lower=0),
        "Sex mix": P.get("logodds_sex_heifer") * (d["sex"] == "heifer") + P.get("logodds_sex_mixed") * (d["sex"] == "mixed"),
        "Arrival season": d["season"].map(seas).astype(float),
        "Week-1 temperature swings": P.get("logodds_temp_swing") * (d["temp_range_wk1_f"] > 30),
        "Bunk space": P.get("logodds_low_bunk") * (d["bunk_cm_per_head"] < 23),
        "Stacked stressors (risk threshold)": P.get("stressor_synergy_logodds") * (n_stress >= 3),
    }


def contributions(row: pd.Series) -> dict[str, float]:
    d = derive(pd.DataFrame([row]))
    return {k: float(v.iloc[0]) for k, v in contribution_frame(d).items()}


def table_a1_checklist(row: pd.Series) -> pd.DataFrame:
    r = derive(pd.DataFrame([row])).iloc[0]

    def known(v):
        return not (v is None or (isinstance(v, float) and np.isnan(v)))

    items = [
        ("Transportation", "operational", "Journey >= 6 h",
         (r["haul_hours"] >= P.get("long_haul_hours")) if known(r["haul_hours"]) else None),
        ("Commingling", "operational", f">= {P.get('stressor_commingling_sources')} sources mixed",
         (r["n_sources"] >= P.get("stressor_commingling_sources")) if known(r["n_sources"]) else None),
        ("Weaning time", "operational", "Freshly weaned (no 34/45-day program)",
         (r["preconditioning"] in ("none", "VAC24")) if known(r["preconditioning"]) else None),
        ("Vaccination status", "operational", "No respiratory vaccination before arrival",
         (str(r["pre_arrival_vaccinated"]).lower() in ("false", "0", "0.0")) if known(r["pre_arrival_vaccinated"]) else None),
        ("Health history", "operational", "Unknown health background",
         (not known(r["preconditioning"]) and not known(r["pre_arrival_vaccinated"]))),
        ("Risk classification", "operational", "Buyer called the lot high-risk",
         (r.get("buyer_risk_call") == "high") if known(r.get("buyer_risk_call")) else None),
        ("Stocking density", "operational", "Bunk < 23 cm/head",
         (r["bunk_cm_per_head"] < 23) if known(r["bunk_cm_per_head"]) else None),
        ("Weight", "biological", f"Light arrival weight (< {P.get('stressor_light_weight_lb')} lb)",
         r["arrival_weight_lb"] < P.get("stressor_light_weight_lb")),
        ("Season", "environmental", "Fall arrival (Sep-Nov)", r["season"] == "fall"),
        ("Weather", "environmental", "Week-1 temperature swings > 30 F",
         (r["temp_range_wk1_f"] > 30) if known(r["temp_range_wk1_f"]) else None),
    ]
    return pd.DataFrame(items, columns=["risk_factor", "domain", "high_risk_state", "met"])


def sigmoid(x):
    return 1 / (1 + np.exp(-x))


def logit(p):
    return np.log(p / (1 - p))
