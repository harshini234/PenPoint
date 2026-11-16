from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st

from .. import data as D
from .. import model as Mo
from .. import theme as T
from ..theme import esc

ss = st.session_state
CHIP_KIND = {"High risk": "high", "Low risk": "low", "Not sure yet": "watch", "No cattle yet": "unknown"}
BAND_COLOR = {"High risk": T.STATUS["high"], "Not sure yet": "#D98F1F", "Low risk": T.STATUS["low"]}
OPT = {"meta": "Metaphylaxis on arrival", "pt": "Pull-and-treat only", "late": "Late metaphylaxis (vet review)", "keep": "Continue pull-and-treat",
       "given": "Metaphylaxis given on arrival"}
OPT_COLOR = {"meta": T.SERIES[1], "pt": T.SERIES[0], "late": T.SERIES[3], "keep": T.SERIES[0], "given": "#8A9791"}


def sensehub_chip():
    s = D.sensehub_status()
    if not s:
        return ""
    return T.chip(s["label"] + (", not updated today" if s["stale"] else ""), "watch" if s["stale"] else "info")


def analysis(s=None, margin=None):
    lots = ss.lots
    s = s or D.settings()
    margin = D.margin() if margin is None else margin
    if lots.empty:
        return pd.DataFrame(), s
    key = (ss.get("_db_v"), tuple(sorted((k, v) for k, v in (ss.get("ops") or {}).items() if str(k).startswith(("or_", "logodds")))))
    if ss.get("_cls_key") != key:
        ss._cls = Mo.classify(lots).set_index("lot_id")
        ss._cls_key = key
    cls = ss._cls
    M = Mo.get()
    rows = []
    for _, r in lots.iterrows():
        c = cls.loc[r.lot_id]
        e = Mo.lot_economics(r, c, s, M)
        rec = dict(lot_id=r.lot_id, cls=c, econ=e, cur_meta=Mo.current_practice_meta(r, s))
        if r.status == "in_progress":
            pj = Mo.on_feed_projection(r, c, s, M)
            act = r.active_head
            left = max(0.0, 1 - pj["F"])
            remaining = act * pj["proj"] * left
            late_eff = (1 - s.meta_rr) * s.late_meta_fraction
            cost_late = act * s.meta_cost + e["MC"] * remaining * (1 - late_eff)
            cost_keep = e["MC"] * remaining
            rec.update(proj=pj, remaining=remaining, late_eff=late_eff, cost_late=cost_late, cost_keep=cost_keep)
            if r.metaphylaxis_given:
                rec["action"] = "given"
            else:
                rec["action"] = "late" if cost_late < cost_keep else "keep"
        else:
            rec["action"] = e["best"]
        rows.append(rec)
    A = pd.DataFrame(rows).set_index("lot_id")
    A["rule_switched"] = False
    arr = [l for l in A.index if lots.set_index("lot_id").loc[l, "status"] == "arriving"]

    def deaths(lid, act):
        e = A.loc[lid, "econ"]
        return e["deaths_meta"] if act == "meta" else e["deaths_pt"]
    cur = sum(deaths(l, "meta" if A.loc[l, "cur_meta"] else "pt") for l in arr)
    plan = sum(deaths(l, A.loc[l, "action"]) for l in arr)
    cands = sorted([l for l in arr if A.loc[l, "action"] == "pt"],
                   key=lambda l: (A.loc[l, "econ"]["cost_meta"] - A.loc[l, "econ"]["cost_pt"]) / max(deaths(l, "pt") - deaths(l, "meta"), 1e-9))
    cap = 1 - margin
    for l in cands:
        if plan <= cur * cap + 1e-9:
            break
        plan += deaths(l, "meta") - deaths(l, "pt")
        A.loc[l, "action"] = "meta"
        A.loc[l, "rule_switched"] = True
    A.attrs["deaths_cur"], A.attrs["deaths_plan"] = cur, plan
    return A, s


def lot_chip(lot_id, A):
    if A is None or lot_id not in getattr(A, "index", []):
        return T.chip("No cattle yet", "unknown")
    c = A.loc[lot_id, "cls"]
    return T.chip(c["chip"], CHIP_KIND[c["chip"]])


def _fx_val(a):
    if a["x"] is None:
        return "not known"
    if a["key"] == "light":
        return f"{-a['x'] * 100:,.0f} lb"
    return "yes" if a["x"] >= 0.5 else "no"


def _fx_bar(a):
    if a["xbar"] is None:
        return "–"
    if a["key"] == "light":
        return f"{-a['xbar'] * 100:,.0f} lb"
    return f"{a['xbar']:.0%} yes"


def why_html(c, M):
    base = M["prevalence"]
    lines = "".join(f'<li style="margin:.15rem 0">{esc(p["text"])}</li>' for p in c["path"])
    rows = "".join(
        f'<tr><td style="padding:3px 8px 3px 0">{esc(a["name"])}</td><td style="padding:3px 8px">{esc(_fx_val(a))}</td>'
        f'<td style="padding:3px 8px;color:var(--muted)">{esc(_fx_bar(a))}</td>'
        f'<td style="padding:3px 8px;color:var(--muted)">{"OR" if a["kind"] == "or" else "OR per 100 lb"} {a["eff"]:.2f}</td>'
        f'<td style="padding:3px 0 3px 8px;font-weight:600;color:{"#9A3B27" if a["contrib"] > 0.005 else "#2F6B4F" if a["contrib"] < -0.005 else "inherit"}">'
        f'{"raises" if a["contrib"] > 0.005 else "lowers" if a["contrib"] < -0.005 else "no change"}</td></tr>' for a in c["adj"])
    return (f'<p style="margin:0 0 .2rem 0">The decision tree sorts the lot with these questions:</p>'
            f'<ol style="margin:.2rem 0 .5rem 1.1rem;padding:0">{lines}</ol>'
            f'<p style="margin:.2rem 0 .5rem 0"><b>Starting estimate:</b> in PenPoint\'s training records, {c["leaf_n"]} past lots answered these questions the same way, '
            f'and {c["leaf_high"]} of them ({c["p_leaf"]:.1%}) became high-risk (15% or more treated for BRD in 45 days). Across all past lots the rate is {base:.0%}. '
            f'The count matters because a group of {c["leaf_n"]} lots gives a 90% range of {c["lo0"]:.0%} to {c["hi0"]:.0%}; fewer lots, wider range.</p>'
            f'<p style="margin:.2rem 0 .2rem 0"><b>Adjusted for this lot\'s own details</b> (compared with the average of those past lots, using published effect sizes):</p>'
            f'<table style="font-size:.88rem;border-collapse:collapse;margin:0 0 .4rem 0"><tr style="color:var(--muted)"><td>Factor</td><td style="padding:0 8px">This lot</td>'
            f'<td style="padding:0 8px">Similar past lots</td><td style="padding:0 8px">Effect</td><td style="padding-left:8px">Risk</td></tr>{rows}</table>'
            f'<p style="margin:.2rem 0 0 0"><b>Result:</b> {c["p"]:.1%} chance this lot becomes high-risk (90% range {c["lo"]:.0%} to {c["hi"]:.0%}). '
            f'The high-risk line is {M["t_star"]:.1%}.</p>')


def risk_work(c, M, label="Show the work"):
    terms = [a for a in c["adj"] if a["x"] is not None and a["xbar"] is not None]
    plug = " + ".join(f"ln({a['eff']:.2f})×({a['x']:.2f} − {a['xbar']:.2f})" for a in terms) or "0"
    T.work([
        ("3", "Starting estimate p₀ = high-risk lots in the tree's branch ÷ all lots in the branch",
         f"= {c['leaf_high']} ÷ {c['leaf_n']} = {c['p_leaf']:.3f}"),
        ("3b", "logit(p) = logit(p₀) + Σ ln(ORₖ) × (xₖ − x̄ₖ)",
         f"= {Mo.logit(c['base']):.3f} + [{plug}] = {Mo.logit(c['base']):.3f} + {c['shift']:+.3f} → p = {c['p']:.3f}",
         "xₖ is this lot's value for each factor (1 = yes, 0 = no; weight as −lb/100); x̄ₖ is the average among the branch's past lots. "
         "Only the difference from similar past lots counts, so a factor the tree already used is not counted twice. Unknown factors add nothing. "
         "Odds ratios come from the parameter ledger and can be changed on the Constraints page."),
        ("3c", "Risk score = 100 × p", f"= {c['score']}"),
        ("4", "High risk if p ≥ t*", f"{c['p']:.3f} {'≥' if c['p'] >= M['t_star'] else '<'} t* = {M['t_star']:.3f}, so {c['call'].lower()}",
         "t* maximizes Youden's J = Se + Sp − 1 on the training lots (Rojas et al. 2022)."),
        ("4a", "Not sure yet if the 90% range crosses t*, or the branch has fewer than 20 lots",
         f"Wilson range {c['lo0']:.3f}–{c['hi0']:.3f}, shifted by (3b) to {c['lo']:.3f}–{c['hi']:.3f}; {c['leaf_n']} lots → "
         f"{'not sure yet' if c['unsure'] else 'confident'}"),
    ], label=label)
