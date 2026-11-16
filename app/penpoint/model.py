from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st
from sklearn.metrics import confusion_matrix, roc_auc_score, roc_curve
from sklearn.model_selection import GridSearchCV, StratifiedKFold, cross_val_predict, train_test_split
from sklearn.tree import DecisionTreeClassifier

from . import data as D

CUT = 0.15
SEED = 42
NUM = ["head_count", "arrival_weight_lb", "pen_area_m2", "bunk_m", "pen_area_m2_per_head", "bunk_m_per_head", "haul_hours"]
CATS = {"arrival_quarter": [1, 2, 3, 4], "sex": ["steer", "heifer", "mixed"],
        "preconditioning": ["VAC45", "VAC34", "VAC24", "none", "unknown"], "pre_arrival_vaccinated": ["yes", "no", "unknown"]}
NICE = {"head_count": "head count", "arrival_weight_lb": "average arrival weight", "pen_area_m2": "total pen area",
        "bunk_m": "bunk length", "pen_area_m2_per_head": "pen area per head", "bunk_m_per_head": "bunk length per head",
        "haul_hours": "haul time", "arrival_quarter": "arrival quarter", "sex": "sex", "preconditioning": "preconditioning",
        "pre_arrival_vaccinated": "vaccinated before arrival"}
UNIT = {"head_count": " head", "arrival_weight_lb": " lb", "pen_area_m2": " m²", "bunk_m": " m", "pen_area_m2_per_head": " m²",
        "bunk_m_per_head": " m", "haul_hours": " h"}
QNAME = {1: "Jan to Mar", 2: "Apr to Jun", 3: "Jul to Sep", 4: "Oct to Dec"}
CAT_NICE = {"VAC45": "VAC-45", "VAC34": "VAC-34", "VAC24": "VAC-24", "none": "none", "unknown": "not known", "yes": "yes", "no": "no",
            "steer": "steers", "heifer": "heifers", "mixed": "mixed"}


def features(df: pd.DataFrame) -> pd.DataFrame:
    d = pd.DataFrame(index=df.index)
    hc = df["head_count"].astype(float)
    d["head_count"] = hc
    d["arrival_weight_lb"] = df["arrival_weight_lb"].astype(float)
    if "pen_area_m2" in df:
        d["pen_area_m2"] = df["pen_area_m2"].astype(float)
        d["bunk_m"] = df["bunk_m"].astype(float)
    else:
        d["pen_area_m2"] = df["pen_area_m2_per_head"] * hc
        d["bunk_m"] = df["bunk_cm_per_head"] * hc / 100
    d["pen_area_m2_per_head"] = d["pen_area_m2"] / hc
    d["bunk_m_per_head"] = d["bunk_m"] / hc
    d["haul_hours"] = pd.to_numeric(df["haul_hours"], errors="coerce")
    q = df["arrival_quarter"] if "arrival_quarter" in df else pd.to_datetime(df["arrival_date"]).dt.quarter
    pc = df["preconditioning"].where(df["preconditioning"].isin(CATS["preconditioning"][:4]), "unknown")
    vx = df["pre_arrival_vaccinated"].map(lambda v: "unknown" if D._yn(v) is None else ("yes" if D._yn(v) else "no"))
    for c, vals in CATS.items():
        src = {"arrival_quarter": q, "sex": df["sex"], "preconditioning": pc, "pre_arrival_vaccinated": vx}[c]
        for v in vals:
            d[f"{c}={v}"] = (src == v).astype(float)
    return d


FACTORS = [
    dict(key="precond", name="Preconditioned (VAC-24, 34 or 45)", param="or_preconditioned", kind="or"),
    dict(key="vax", name="Vaccinated before arrival", param="or_pre_arrival_vax_morbidity", kind="or"),
    dict(key="long_haul", name="Hauled 6 hours or more", param="or_long_haul", kind="or"),
    dict(key="sale_barn", name="Bought through a sale barn", param="or_sale_barn", kind="or"),
    dict(key="light", name="Arrival weight (per 100 lb lighter)", param="logodds_per_100lb_lighter", kind="logodds"),
]


def factor_effect(f):
    ops = st.session_state.get("ops") or {}
    v = float(ops.get(f["param"], D.P.get(f["param"])))
    return math.exp(v) if f["kind"] == "logodds" else v


def factor_matrix(df: pd.DataFrame) -> pd.DataFrame:
    pc = df["preconditioning"].map(lambda v: np.nan if D._none(v) is None or v == "unknown" else float(v in ("VAC45", "VAC34", "VAC24")))
    vx = df["pre_arrival_vaccinated"].map(lambda v: np.nan if D._yn(v) is None else float(D._yn(v)))
    hh = pd.to_numeric(df["haul_hours"], errors="coerce")
    lh = np.where(hh.isna(), np.nan, (hh >= D.P.get("long_haul_hours")).astype(float))
    ch = df["market_channel"] if "market_channel" in df else pd.Series(np.nan, index=df.index)
    sb = ch.map(lambda v: np.nan if D._none(v) is None else float(v == "sale_barn"))
    lt = -pd.to_numeric(df["arrival_weight_lb"], errors="coerce") / 100
    return pd.DataFrame({"precond": pc, "vax": vx, "long_haul": lh, "sale_barn": sb, "light": lt}, index=df.index)


def logit(p):
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.log(p / (1 - p))


def expit(x):
    return 1 / (1 + math.exp(-x))


def wilson(k, n, z=1.645):
    if n == 0:
        return 0.0, 1.0
    p = k / n
    den = 1 + z * z / n
    c = (p + z * z / (2 * n)) / den
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / den
    return max(0.0, c - h), min(1.0, c + h)


@st.cache_resource(show_spinner="Training the decision tree on yard history...")
def train(n_hist: int):
    h = D.load_history().copy()
    X = features(h)
    y = (h["morbidity_45"] >= CUT).astype(int).to_numpy()
    Xtr, Xte, ytr, yte, htr, hte = train_test_split(X, y, h, test_size=0.25, stratify=y, random_state=SEED)
    cv = StratifiedKFold(10, shuffle=True, random_state=SEED)
    grid = GridSearchCV(DecisionTreeClassifier(random_state=SEED),
                        {"max_depth": [2, 3, 4], "min_samples_leaf": [20, 30, 50], "ccp_alpha": [0.0, 0.002, 0.005]},
                        scoring="roc_auc", cv=cv)
    grid.fit(Xtr, ytr)
    tree = grid.best_estimator_
    oof = cross_val_predict(DecisionTreeClassifier(random_state=SEED, **grid.best_params_), Xtr, ytr, cv=cv, method="predict_proba")[:, 1]
    fpr, tpr, thr = roc_curve(ytr, oof)
    j = tpr - fpr
    t_star = float(np.clip(thr[int(np.argmax(j))], 0.0, 1.0))
    pte = tree.predict_proba(Xte)[:, 1]
    call = (pte >= t_star).astype(int)
    tn, fp, fn, tp = confusion_matrix(yte, call, labels=[0, 1]).ravel()
    leaf_tr = tree.apply(Xtr)
    leaves = pd.DataFrame({"leaf": leaf_tr, "y": ytr}).groupby("leaf")["y"].agg(["sum", "count"])
    leaf_x = factor_matrix(htr).assign(leaf=leaf_tr).groupby("leaf").mean()
    buyer = (hte["buyer_risk_call"] == "high").astype(int).to_numpy()
    btn, bfp, bfn, btp = confusion_matrix(yte, buyer, labels=[0, 1]).ravel()
    mH = float(h.loc[h.morbidity_45 >= CUT, "morbidity_45"].mean())
    mL = float(h.loc[h.morbidity_45 < CUT, "morbidity_45"].mean())
    return dict(tree=tree, cols=list(X.columns), t_star=t_star, params=grid.best_params_, cv_auc=float(grid.best_score_),
                test_auc=float(roc_auc_score(yte, pte)), n_train=len(ytr), n_test=len(yte), prevalence=float(y.mean()),
                tp=int(tp), fp=int(fp), tn=int(tn), fn=int(fn), leaves=leaves, leaf_x=leaf_x, mH=mH, mL=mL, n_hist=len(h),
                buyer=dict(tp=int(btp), fp=int(bfp), tn=int(btn), fn=int(bfn)))


def get():
    return train(len(D.load_history()))


def rates(c):
    tp, fp, tn, fn = c["tp"], c["fp"], c["tn"], c["fn"]
    return dict(se=tp / max(tp + fn, 1), sp=tn / max(tn + fp, 1), ppv=tp / max(tp + fp, 1), npv=tn / max(tn + fn, 1),
                acc=(tp + tn) / max(tp + fp + tn + fn, 1))


def _split_text(col, thr, left):
    if "=" in col:
        base, val = col.split("=", 1)
        val = int(val) if base == "arrival_quarter" else val
        shown = QNAME[val] if base == "arrival_quarter" else CAT_NICE.get(val, val)
        return f"{NICE[base].capitalize()} is {'not ' if left else ''}{shown}"
    return f"{NICE[col].capitalize()} is {'at most' if left else 'over'} {thr:,.1f}{UNIT.get(col, '')}"


def classify(lots: pd.DataFrame) -> pd.DataFrame:
    M = get()
    if lots.empty:
        return pd.DataFrame(columns=["lot_id", "score", "call", "leaf_n", "leaf_high", "lo", "hi", "path", "missing"])
    X = features(lots)[M["cols"]]
    FX = factor_matrix(lots)
    tree = M["tree"].tree_
    rows = []
    for i, (_, x) in enumerate(X.iterrows()):
        node, path = 0, []
        while tree.children_left[node] != -1:
            f = M["cols"][tree.feature[node]]
            thr = tree.threshold[node]
            v = x[f]
            if pd.isna(v):
                go_left = bool(tree.missing_go_to_left[node]) if hasattr(tree, "missing_go_to_left") else True
                note = " (not known, so PenPoint follows the branch most lots without it took)"
            else:
                go_left = v <= thr
                note = ""
            nl = int(tree.n_node_samples[tree.children_left[node] if go_left else tree.children_right[node]])
            path.append(dict(text=_split_text(f, thr, go_left) + note, feature=f.split("=")[0], value=None if pd.isna(v) else float(v), n=nl))
            node = tree.children_left[node] if go_left else tree.children_right[node]
        lf = M["leaves"].loc[node]
        k, n = int(lf["sum"]), int(lf["count"])
        p_leaf = k / n
        lo0, hi0 = wilson(k, n)
        adj, shift = [], 0.0
        fx, mx = FX.iloc[i], M["leaf_x"].loc[node]
        for f in FACTORS:
            xv, xb = fx[f["key"]], mx[f["key"]]
            eff = factor_effect(f)
            if pd.isna(xv) or pd.isna(xb):
                adj.append(dict(**f, x=None, xbar=None if pd.isna(xb) else float(xb), eff=eff, contrib=0.0))
                continue
            cc = math.log(eff) * (float(xv) - float(xb))
            shift += cc
            adj.append(dict(**f, x=float(xv), xbar=float(xb), eff=eff, contrib=cc))
        base = p_leaf if 0 < k < n else (k + 0.5) / (n + 1)
        p = expit(logit(base) + shift)
        lo, hi = expit(logit(max(lo0, 1e-4)) + shift), expit(logit(min(hi0, 1 - 1e-4)) + shift)
        call = "High risk" if p >= M["t_star"] else "Low risk"
        unsure = (lo < M["t_star"] <= hi) or n < 20
        miss = [NICE[c] for c in ("haul_hours",) if pd.isna(x[c])]
        miss += [NICE[c] for c in ("preconditioning", "pre_arrival_vaccinated") if x[f"{c}=unknown"] == 1]
        rows.append(dict(lot_id=lots.iloc[i]["lot_id"], score=round(100 * p), p=p, p_leaf=p_leaf, base=base, shift=shift, adj=adj, call=call,
                         unsure=bool(unsure), chip="Not sure yet" if unsure else call, leaf_n=n, leaf_high=k, lo=lo, hi=hi, lo0=lo0, hi0=hi0,
                         path=path, missing=miss, leaf=int(node)))
    return pd.DataFrame(rows)


def mc_parts(s, w):
    death = float(s.death_cost(w))
    surv = s.tx_cost + s.perf_loss
    return dict(death=death, surv=surv, mc=(1 - s.cfr) * surv + s.cfr * death)


def lot_economics(row, cls, s, M=None):
    M = M or get()
    r = rates(M)
    CS = int(row["head_count"])
    w = float(row["arrival_weight_lb"])
    MC = mc_parts(s, w)["mc"]
    TC, ME = s.meta_cost, 1 - s.meta_rr
    q = float(cls["p"])
    Em = q * M["mH"] + (1 - q) * M["mL"]
    cost_meta = CS * TC + CS * MC * Em * (1 - ME)
    cost_pt = CS * MC * Em
    TP = CS * (MC * M["mH"] * ME - TC)
    FP = -CS * TC
    FN = -CS * MC * M["mH"] * ME
    out = dict(CS=CS, w=w, MC=MC, TC=TC, ME=ME, q=q, Em=Em, mH=M["mH"], mL=M["mL"], ppv=r["ppv"], npv=r["npv"],
               cost_meta=cost_meta, cost_pt=cost_pt, TP=TP, FP=FP, FN=FN, TN=0.0, breakeven=TC / (MC * ME),
               cases_meta=CS * Em * (1 - ME), cases_pt=CS * Em, doses_meta=CS + s.doses_per_case * CS * Em * (1 - ME),
               doses_pt=s.doses_per_case * CS * Em, deaths_meta=CS * Em * (1 - ME) * s.cfr, deaths_pt=CS * Em * s.cfr)
    out["best"] = "meta" if cost_meta < cost_pt else "pt"
    for tag, qq in (("lo", float(cls["lo"])), ("hi", float(cls["hi"]))):
        e = qq * M["mH"] + (1 - qq) * M["mL"]
        out[f"Em_{tag}"] = e
        out[f"cost_meta_{tag}"] = CS * TC + CS * MC * e * (1 - ME)
        out[f"cost_pt_{tag}"] = CS * MC * e
    best_lo = "meta" if out["cost_meta_lo"] < out["cost_pt_lo"] else "pt"
    best_hi = "meta" if out["cost_meta_hi"] < out["cost_pt_hi"] else "pt"
    out["robust"] = best_lo == best_hi == out["best"]
    return out


def on_feed_projection(row, cls, s, M=None):
    M = M or get()
    ev = st.session_state.events
    d = int(row["days_on_feed"])
    CS = int(row["head_count"])
    sick = int(ev[(ev.lot_id == row["lot_id"]) & (ev.type == "BRD treatment")].animal_id.nunique())
    F = float(D.G.onset_cdf(np.array([min(d, 45)]))[0])
    q = float(cls["p"])
    Em = q * M["mH"] + (1 - q) * M["mL"]
    so_far = sick / max(CS, 1)
    proj = F * (so_far / F if F > 0 else 0) + (1 - F) * Em if F > 0 else Em
    return dict(sick=sick, so_far=so_far, F=F, Em=Em, proj=proj, d=d, CS=CS)


def nhcb_method(c, p, mH, MC, ME, TC, CS):
    r = rates(c)
    TP = CS * (MC * mH * ME - TC)
    FP = -CS * TC
    FN = -CS * MC * mH * ME
    v = p * r["se"] * TP + (1 - p) * (1 - r["sp"]) * FP + p * (1 - r["se"]) * FN
    return v / CS


def current_practice_meta(row, s):
    pol = s.policy
    if pol == "none":
        return False
    if pol == "all_sale_barn":
        return row.get("market_channel") == "sale_barn"
    return row.get("buyer_risk_call") == "high"
