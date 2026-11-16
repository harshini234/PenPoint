from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import data as D
from .. import model as Mo
from .. import theme as T
from ..theme import esc, money
from .common import OPT, OPT_COLOR, analysis, lot_chip, risk_work, sensehub_chip, why_html

ss = st.session_state


def render(sub, yard=None):
    {"compare": compare, "costs": costs, "scenario": scenario, "plan": plan, "today": today, "tracking": tracking}[sub]()


def _need():
    A, s = analysis()
    if A.empty:
        st.info("No cattle yet. Add some under Lot management.")
        st.stop()
    return A, s


def build_actions(A, s):
    acts = []
    L = ss.lots.set_index("lot_id")
    a = D.animal_status()
    sh = D.sensehub_status()
    for lid, g in a[a.status == "Alert"].groupby("lot_id"):
        tags = g.animal_id.tolist()
        acts.append(dict(kind="Check cattle", chip="watch", when="Today", lot=lid,
                         what=f"Check {len(tags)} SenseHub-flagged animal{'s' if len(tags) > 1 else ''} in {L.loc[lid, 'pen']}",
                         why=f"Tags {', '.join(tags[:5])}{'…' if len(tags) > 5 else ''}. Pull and examine any that look sick."
                             + (f" These are {sh['label']}; no report has been uploaded today." if sh and sh["stale"] else "")))
    for lid, g in a[a.status == "In treatment"].groupby("lot_id"):
        acts.append(dict(kind="Re-check", chip="high", when="Today", lot=lid, what=f"Re-check {len(g)} animal{'s' if len(g) > 1 else ''} in treatment in {L.loc[lid, 'pen']}",
                         why="Treated in the last 4 days. Retreat or move to the hospital pen per your vet's protocol."))
    for lid in A.index:
        r, act = L.loc[lid], A.loc[lid, "action"]
        if act == "late":
            acts.append(dict(kind="Vet decision", chip="high", when="Today", lot=lid,
                             what=f"Ask your vet about late metaphylaxis for lot {lid}",
                             why=f"Projected BRD rate {A.loc[lid, 'proj']['proj']:.0%}; treating the rest now is expected to save "
                                 f"{money(A.loc[lid, 'cost_keep'] - A.loc[lid, 'cost_late'])}."))
        elif r.status == "arriving":
            d = pd.Timestamp(r.arrival_date)
            acts.append(dict(kind="Arrival", chip="high" if act == "meta" else "low", when=f"{d:%b %d}", lot=lid,
                             what=f"{OPT[act]} for lot {lid}" + (" (no-more-deaths rule)" if A.loc[lid, "rule_switched"] else ""),
                             why=f"{int(r.active_head)} cattle arriving. Expected cost {money(A.loc[lid, 'econ']['cost_' + act])} vs "
                                 f"{money(A.loc[lid, 'econ']['cost_' + ('pt' if act == 'meta' else 'meta')])} the other way."))
        if r.conflicts:
            acts.append(dict(kind="Fix data", chip="watch", when="Today", lot=lid, what=f"Resolve a conflict in lot {lid}",
                             why=f"{', '.join(D.FIELD_LABEL[f] for f in r.conflicts)} on some animals don't match the lot."))
    pri = {"Vet decision": 0, "Check cattle": 1, "Re-check": 2, "Fix data": 3}
    return sorted([x for x in acts if x["when"] == "Today"], key=lambda x: pri.get(x["kind"], 9)) + [x for x in acts if x["when"] != "Today"]


def today():
    T.header("Daily action list", "What needs attention today, from SenseHub alerts, recent treatments, data conflicts and the plan.", f"{D.AS_OF:%b %d, %Y}")
    A, s = _need()
    acts = build_actions(A, s)
    td = [x for x in acts if x["when"] == "Today"]
    sh = D.sensehub_status()
    if sh and sh["stale"]:
        st.warning(f"SenseHub: the latest report has {sh['label']}. Upload today's report under Lot management, Add.")
    c1, c2 = st.columns([1, 1.3])
    with c1:
        with st.container(key="feature_next"):
            st.html(f'<p class="pp-h" style="color:#fff">Needs you today</p><p class="pp-note" style="color:#BFD3C7">{len(td)} actions</p>')
            for x in td[:6]:
                st.html(f'<div style="padding:10px 0;border-top:1px solid rgba(255,255,255,.12)"><p style="margin:0;color:#fff;font-weight:600">'
                        f'{esc(x["what"])}</p><p style="margin:.15rem 0 0 0;color:#BFD3C7;font-size:.85rem">{esc(x["why"])}</p></div>')
            if not td:
                st.html('<p style="color:#DCE8E0">Nothing urgent today.</p>')
    with c2:
        blocks = ([("More for today", td[6:])] if len(td) > 6 else []) + [("Arrivals coming up", [x for x in acts if x["kind"] == "Arrival"])]
        for i, (title, items) in enumerate(blocks):
            with st.container(key=f"card_act_{i}"):
                T.h(title)
                if not items:
                    st.html('<p class="pp-note">Nothing here.</p>')
                st.html("".join(f'<div class="action"><div class="when">{esc(x["when"])}</div><div><p class="what">{esc(x["what"])}</p>'
                                f'<p class="why">{esc(x["why"])}</p><div style="margin-top:6px">{T.chip(x["kind"], x["chip"])}</div></div></div>' for x in items))
    st.caption(D.VET_NOTE)


def totals(A, s, which):
    L = ss.lots.set_index("lot_id")
    out = dict(cost=0.0, cases=0.0, doses=0.0, deaths=0.0, rows=[])
    for lid in A.index:
        if L.loc[lid, "status"] != "arriving":
            continue
        e = A.loc[lid, "econ"]
        act = A.loc[lid, "action"] if which == "plan" else ("meta" if A.loc[lid, "cur_meta"] else "pt")
        out["cost"] += e["cost_" + act]
        out["cases"] += e["cases_" + act]
        out["doses"] += e["doses_" + act]
        out["deaths"] += e["deaths_" + act]
        out["rows"].append((lid, act, e))
    return out


def plan():
    T.header("Decision summary", "The recommended action for each lot against your current practice, ready to review with your veterinarian.", f"{D.AS_OF:%b %d, %Y}")
    A, s = _need()
    st.download_button("Download the decision summary for vet review (HTML; print to PDF)", summary_html(A, s), f"penpoint_decision_summary_{D.AS_OF}.html",
                       "text/html", type="primary", icon=":material/download:")
    unsure = [l for l in A.index if ss.lots.set_index("lot_id").loc[l, "status"] == "arriving" and not A.loc[l, "econ"]["robust"]]
    if unsure:
        st.warning(f"**Not enough information for a confident choice on {len(unsure)} lot{'s' if len(unsure) > 1 else ''}:** {', '.join(unsure)}. "
                   "Across each lot's 90% risk range the cheaper option flips. These are marked for your veterinarian in the summary.")
    L = ss.lots.set_index("lot_id")
    P_, C_ = totals(A, s, "plan"), totals(A, s, "current")
    arr = [l for l in A.index if L.loc[l, "status"] == "arriving"]
    cnt = A.loc[arr, "action"].value_counts()
    with st.container(key="feature_plan"):
        parts = [f"{cnt.get(k, 0)} {txt}" for k, txt in (("meta", "get metaphylaxis on arrival"), ("pt", "pull-and-treat only")) if cnt.get(k, 0)]
        late = int((A.action == "late").sum())
        late_txt = f" {late} lot{'s' if late > 1 else ''} on feed should be discussed with your vet for late metaphylaxis." if late else ""
        st.html(f'<p class="pp-h" style="color:#fff;font-size:1.3rem">PenPoint recommends</p><p style="color:#E7F0EA;margin:.3rem 0 0 0;max-width:70ch">'
                f'Of {len(arr)} lots arriving, {", ".join(parts) or "none need a decision"}.'
                f'{late_txt}'
                f'</p><p style="color:#BFD3C7;font-size:.86rem;margin:.6rem 0 0 0">Expected BRD deaths stay at or below current practice '
                f'({P_["deaths"]:.1f} vs {C_["deaths"]:.1f}). {esc(D.VET_NOTE)}</p>')
    k = st.columns(3)
    tiles = [("Expected health cost, arriving lots", P_["cost"], C_["cost"], lambda v: f"${v:,.0f}", "dollar", "hay"),
             ("Expected BRD cases", P_["cases"], C_["cases"], lambda v: f"{v:,.1f}", "heart", "rust"),
             ("Antimicrobial doses", P_["doses"], C_["doses"], lambda v: f"{v:,.0f}", "pill", "sky")]
    for i, (lab, new, old, fv, ic, tone) in enumerate(tiles):
        with k[i]:
            dlt = new - old
            T.kpi(lab, fv(new), ic, tone, f"{'+' if dlt > 0 else '−'}{fv(abs(dlt))} vs current practice" if abs(dlt) > 1e-9 else "same as current practice",
                  dlt < 0 if abs(dlt) > 1e-9 else None, key=f"tile_p{i}")
    rows = P_["rows"]
    T.work([("11", "Expected cost of a lot = metaphylaxis: CS × TC + CS × MC × E[m] × (1 − ME);  pull-and-treat: CS × MC × E[m]", "See each lot under Lots and costs."),
            ("14", "Expected health cost = sum over arriving lots of (11) for the chosen option",
             " + ".join(f"${e['cost_' + a]:,.0f}" for _, a, e in rows) + f" = ${P_['cost']:,.0f}"),
            ("12", "Expected BRD cases = CS × E[m] × (1 − ME if metaphylaxis, else 1)",
             " + ".join(f"{e['cases_' + a]:.1f}" for _, a, e in rows) + f" = {P_['cases']:.1f}"),
            ("13", f"Antimicrobial doses = CS (if metaphylaxis) + {s.doses_per_case:.2f} × expected cases",
             " + ".join(f"{e['doses_' + a]:.0f}" for _, a, e in rows) + f" = {P_['doses']:.0f}"),
            ("", "Current practice = the same sums, with metaphylaxis wherever current practice would give it",
             f"cost ${C_['cost']:,.0f}, cases {C_['cases']:.1f}, doses {C_['doses']:.0f}",
             "Lots already on feed are not in these totals; their arrival decision is behind them. See Treatment tracking.")])
    with st.container(key="card_plan_list"):
        T.h("Action for each lot", "Grouped by what to do. Colours match the options on every page.")
        groups = {}
        for lid in A.index:
            groups.setdefault(A.loc[lid, "action"], []).append(lid)
        html = []
        for act in ("meta", "pt", "late", "keep", "given"):
            if act not in groups:
                continue
            ids = groups[act]
            chips = " ".join(T.chip(f"{l}, {L.loc[l, 'pen']}" + (" (rule)" if A.loc[l, "rule_switched"] else ""), "ghost", False) for l in ids)
            html.append(f'<div class="action"><div class="when"><span style="display:inline-block;width:10px;height:10px;border-radius:3px;'
                        f'background:{OPT_COLOR[act]};margin-right:6px"></span>{len(ids)} lots</div><div><p class="what">{esc(OPT[act])}</p>'
                        f'<p class="why">{int(L.loc[ids, "active_head"].sum()):,} cattle</p><div style="display:flex;gap:6px;flex-wrap:wrap;margin-top:8px">{chips}</div></div></div>')
        st.html("".join(html))
        if A.rule_switched.any():
            st.caption("(rule) means pull-and-treat was cheaper, but metaphylaxis was kept so expected deaths don't rise above current practice.")


def costs():
    T.header("Lot-level cost analysis", "For each lot: why it got its risk call, the four outcomes of Rojas et al.'s net health cost benefit, and every cost worked out.")
    A, s = _need()
    M = Mo.get()
    L = ss.lots.set_index("lot_id")
    focus = ss.pop("focus_lot", None)
    order = {"High risk": 0, "Not sure yet": 1, "Low risk": 2}
    ids = sorted(A.index, key=lambda l: (L.loc[l, "status"] != "arriving", order[A.loc[l, "cls"]["chip"]], -A.loc[l, "cls"]["p"]))
    for lid in ids:
        r, c, e, act = L.loc[lid], A.loc[lid, "cls"], A.loc[lid, "econ"], A.loc[lid, "action"]
        with st.container(key=f"card_c_{lid}"):
            k1, k2 = st.columns([4, 2], vertical_alignment="center")
            k1.html(f'<div class="lotrow"><div><p class="nm">{esc(lid)}</p><p class="sub">{esc(r.pen)}, {int(r.active_head)} cattle, '
                    f'{"arrives " + pd.Timestamp(r.arrival_date).strftime("%b %d") if r.status == "arriving" else "day " + str(int(r.days_on_feed)) + " on feed"}</p></div>'
                    f'<div style="margin-left:auto">{lot_chip(lid, A)}</div></div>')
            k2.html(f'<p style="margin:0;text-align:right"><span style="display:inline-block;width:10px;height:10px;border-radius:3px;background:{OPT_COLOR[act]};'
                    f'margin-right:6px"></span><b>{esc(OPT[act])}</b></p>')
            with st.expander("Why, and the costs", expanded=lid == focus):
                lot_costs(lid, r, c, e, act, A, s, M)


def lot_costs(lid, r, c, e, act, A, s, M):
    st.html(f'<p class="pp-h" style="font-size:1rem">Why it is {c["chip"].lower()}</p>' + why_html(c, M))
    risk_work(c, M, "Show the work for the risk call")
    if r.status == "in_progress":
        pj = A.loc[lid, "proj"]
        if r.metaphylaxis_given:
            st.html(f'<p style="margin:.6rem 0 0 0">This lot got metaphylaxis on arrival. See Treatment tracking for how it is working.</p>')
            return
        st.html(f'<p class="pp-h" style="font-size:1rem;margin-top:.6rem">Options now (day {pj["d"]} on feed)</p>')
        t = pd.DataFrame([dict(option=OPT["late"], cost=A.loc[lid, "cost_late"]), dict(option=OPT["keep"], cost=A.loc[lid, "cost_keep"])])
        st.dataframe(t, hide_index=True, width="stretch", column_config={"option": "Option", "cost": st.column_config.NumberColumn("Expected cost from here", format="$%.0f")})
        T.work([("5", "BRD rate so far = treated at least once ÷ head count", f"= {pj['sick']} ÷ {pj['CS']} = {pj['so_far']:.1%}"),
                ("18", "Share of a lot's 45-day cases usually seen by this day, F(d)", f"F({pj['d']}) = {pj['F']:.2f}",
                 "From the onset curve used for the demo history."),
                ("19", "Projected 45-day BRD rate = F(d) × (rate so far ÷ F(d)) + (1 − F(d)) × E[m]",
                 f"= {pj['F']:.2f} × ({pj['so_far']:.3f} ÷ {pj['F']:.2f}) + {1 - pj['F']:.2f} × {pj['Em']:.3f} = {pj['proj']:.1%}" if pj["F"] > 0 else f"= E[m] = {pj['Em']:.1%}",
                 "Early on, the tree's estimate counts most; later, the lot's own record does."),
                ("20", "Cases still to come = cattle in the lot × projected rate × (1 − F(d))",
                 f"= {int(r.active_head)} × {pj['proj']:.3f} × {1 - pj['F']:.2f} = {A.loc[lid, 'remaining']:.1f}"),
                ("21", "Late metaphylaxis = cattle × TC + MC × cases to come × (1 − ME × late share)",
                 f"= {int(r.active_head)} × ${e['TC']:.2f} + ${e['MC']:,.0f} × {A.loc[lid, 'remaining']:.1f} × (1 − {A.loc[lid, 'late_eff']:.2f}) = {money(A.loc[lid, 'cost_late'])}",
                 f"Late share = {s.late_meta_fraction:.0%}: metaphylaxis given after arrival is assumed to work this well relative to on arrival."),
                ("22", "Keep pulling and treating = MC × cases to come", f"= ${e['MC']:,.0f} × {A.loc[lid, 'remaining']:.1f} = {money(A.loc[lid, 'cost_keep'])}")])
        return
    st.html('<p class="pp-h" style="font-size:1rem;margin-top:.6rem">Treatment options</p>')
    q = e["q"]
    t = pd.DataFrame([
        dict(option=OPT["meta"], outcome="Truly high-risk (TP)", chance=q, value=e["TP"]),
        dict(option=OPT["meta"], outcome="Truly low-risk (FP)", chance=1 - q, value=e["FP"]),
        dict(option=OPT["pt"], outcome="Truly high-risk (FN)", chance=q, value=e["FN"]),
        dict(option=OPT["pt"], outcome="Truly low-risk (TN)", chance=1 - q, value=0.0)])
    st.dataframe(t, hide_index=True, width="stretch",
                 column_config={"option": "If you choose", "outcome": "And the lot turns out", "chance": st.column_config.NumberColumn("Chance", format="percent"),
                                "value": st.column_config.NumberColumn("Net health cost benefit (Rojas Eqs 2-5)", format="$%.0f")})
    o1, o2 = st.columns(2)
    for col, k in ((o1, "meta"), (o2, "pt")):
        with col:
            T.kpi(OPT[k], money(e["cost_" + k]), "dollar", "sky" if k == "meta" else "pine",
                  "recommended" if act == k else f"{money(e['cost_' + k] - e['cost_' + ('pt' if k == 'meta' else 'meta')], True)} vs the other",
                  True if act == k else None, key=f"tile_{lid}_{k}")
    robust_note(e)
    cur = "meta" if A.loc[lid, "cur_meta"] else "pt"
    st.html(f'<p class="pp-note" style="margin:.4rem 0 0 0">Current practice ({"buyer called it high" if r.buyer_risk_call == "high" else "buyer called it low" if r.buyer_risk_call == "low" else "no buyer call"}) '
            f'would be <b style="color:var(--ink)">{OPT[cur].lower()}</b>, expected {money(e["cost_" + cur])}.'
            + (" PenPoint keeps metaphylaxis here so expected deaths don't rise." if A.loc[lid, "rule_switched"] else "") + '</p>')
    T.work([
        ("3b", "q = chance this lot is truly high-risk (the tree's branch share, adjusted for this lot's own details)",
         f"= {q:.3f} (branch share {c['p_leaf']:.3f}; see the risk work above)", "q weights the true-positive outcome if treated, and the false-negative outcome if not."),
        ("6", "E[m] = q × m_H + (1 − q) × m_L", f"= {q:.3f} × {e['mH']:.3f} + {1 - q:.3f} × {e['mL']:.3f} = {e['Em']:.3f}",
         "m_H and m_L are the average BRD rates of high-risk and low-risk lots in yard history (Rojas: 27.07% and 3.77%)."),
        ("10", "MC = cost of one sick animal", f"= ${e['MC']:,.0f} at {e['w']:,.0f} lb (Constraints shows the parts)"),
        ("7", "TP = CS × (MC × m_H × ME − TC)  [Rojas Eq 3, corrected]",
         f"= {e['CS']} × (${e['MC']:,.0f} × {e['mH']:.3f} × {e['ME']:.2f} − ${e['TC']:.2f}) = {money(e['TP'])}",
         "As printed, Eq 3 multiplies by TC and uses BRD45 (share of lots that are high-risk); the units only work with CS and the BRD rate of a high-risk lot."),
        ("8", "FP = −CS × TC  [Rojas Eq 4];  FN = −CS × MC × m_H × ME  [Eq 5];  TN = $0  [Eq 2]",
         f"FP = −{e['CS']} × ${e['TC']:.2f} = {money(e['FP'])};  FN = −{e['CS']} × ${e['MC']:,.0f} × {e['mH']:.3f} × {e['ME']:.2f} = {money(e['FN'])}"),
        ("11", "Expected cost, metaphylaxis = CS × TC + CS × MC × E[m] × (1 − ME)",
         f"= {e['CS']} × ${e['TC']:.2f} + {e['CS']} × ${e['MC']:,.0f} × {e['Em']:.3f} × {1 - e['ME']:.2f} = {money(e['cost_meta'])}"),
        ("11", "Expected cost, pull-and-treat = CS × MC × E[m]", f"= {e['CS']} × ${e['MC']:,.0f} × {e['Em']:.3f} = {money(e['cost_pt'])}"),
        ("11b", "Metaphylaxis pays when E[m] > TC ÷ (MC × ME)",
         f"{e['Em']:.3f} {'>' if e['Em'] > e['breakeven'] else '≤'} {e['breakeven']:.3f}, so {'metaphylaxis' if e['Em'] > e['breakeven'] else 'pull-and-treat'} is cheaper"),
    ])


def robust_note(e):
    if e["robust"]:
        st.html(f'<p class="pp-note" style="margin:.4rem 0 0 0">Confident: across the 90% range for this lot\'s risk ({e["Em_lo"]:.1%} to {e["Em_hi"]:.1%} '
                f'expected BRD rate), the same option stays cheaper.</p>')
    else:
        st.warning(f"**The available information can't support a confident choice for this lot.** Across the 90% range of its risk, the expected BRD rate "
                   f"runs from {e['Em_lo']:.1%} to {e['Em_hi']:.1%}, straddling the break-even of {e['breakeven']:.1%}: metaphylaxis would cost "
                   f"{money(e['cost_meta_lo'])} to {money(e['cost_meta_hi'])} and pull-and-treat {money(e['cost_pt_lo'])} to {money(e['cost_pt_hi'])}. "
                   f"Missing details (haul time, preconditioning, vaccination) or a few days of the lot's own treatment record would narrow this. "
                   f"Discuss with your veterinarian.")


STRATS = [("current", "Current practice"), ("plan", "PenPoint plan"), ("all_meta", "Metaphylaxis on every lot"), ("all_pt", "Pull-and-treat on every lot")]


def strategy(A, which, lots=None):
    L = ss.lots.set_index("lot_id")
    out = dict(cost=0.0, cases=0.0, doses=0.0, deaths=0.0, n_meta=0, head=0)
    for lid in (lots if lots is not None else A.index):
        if L.loc[lid, "status"] != "arriving":
            continue
        e = A.loc[lid, "econ"]
        act = {"plan": A.loc[lid, "action"], "current": "meta" if A.loc[lid, "cur_meta"] else "pt", "all_meta": "meta", "all_pt": "pt"}[which]
        for k in ("cost", "cases", "doses", "deaths"):
            out[k] += e[f"{k}_{act}"]
        out["n_meta"] += act == "meta"
        out["head"] += e["CS"]
    return out


def strategy_table(A):
    rows = []
    for k, name in STRATS:
        t = strategy(A, k)
        rows.append(dict(strategy=name, n_meta=t["n_meta"], cost=t["cost"], cost_head=t["cost"] / max(t["head"], 1), cases=t["cases"],
                         deaths=t["deaths"], doses=t["doses"]))
    return pd.DataFrame(rows)


OPT_DESC = {"current": "What the yard does now", "plan": "PenPoint's recommendation", "all_meta": "Treat every arriving lot on arrival",
            "all_pt": "Treat only cattle that get sick"}


def _delta(new, old, unit, fmt, fewer="fewer", more="more"):
    d = new - old
    if abs(d) < 1e-6:
        return "same as now"
    return f"{fmt(abs(d))}{unit} {fewer if d < 0 else more} than now"


def compare():
    T.header("Treatment options", "How to handle the lots arriving this week, what each choice is expected to cost, and how it compares with "
             "what the yard does now.", f"{D.AS_OF:%b %d, %Y}")
    A, s = _need()
    L = ss.lots.set_index("lot_id")
    arr = [l for l in A.index if L.loc[l, "status"] == "arriving"]
    pol = {"buyer_high": "metaphylaxis when the buyer calls a lot high-risk", "all_sale_barn": "metaphylaxis on every sale-barn lot",
           "none": "no metaphylaxis"}[s.policy]
    if not arr:
        st.info("No lots are due to arrive, so there is no arrival decision to make. Lots already on feed are below.")
    else:
        S = strategy_table(A).set_index("strategy")
        cur, plan_ = S.loc["Current practice"], S.loc["PenPoint plan"]
        meta = [l for l in arr if A.loc[l, "action"] == "meta"]
        pt = [l for l in arr if A.loc[l, "action"] == "pt"]
        unsure = [l for l in arr if not A.loc[l, "econ"]["robust"]]
        with st.container(key="feature_plan"):
            st.html(f'<p class="pp-h" style="color:#fff;font-size:1.3rem;margin:0">Recommended plan</p>'
                    f'<p style="color:#E7F0EA;margin:.35rem 0 0 0;max-width:72ch">'
                    + (f'Give metaphylaxis on arrival to <b>{len(meta)} lot{"s" if len(meta) != 1 else ""}</b> ({esc(", ".join(meta))})' if meta else "No lot needs metaphylaxis")
                    + (f' and pull-and-treat the other <b>{len(pt)}</b> ({esc(", ".join(pt))}).' if pt else ".") + '</p>'
                    f'<div style="display:flex;gap:34px;flex-wrap:wrap;margin:.9rem 0 .2rem 0">'
                    + "".join(f'<div><p style="color:#BFD3C7;font-size:.82rem;margin:0">{lab}</p><p style="color:#fff;font-size:1.35rem;font-weight:650;margin:0">{val}</p>'
                              f'<p style="color:{T.HAY};font-size:.82rem;margin:0">{dl}</p></div>'
                              for lab, val, dl in (("Expected health cost", f"${plan_.cost:,.0f}", _delta(plan_.cost, cur.cost, "", lambda v: f"${v:,.0f}", "less", "more")),
                                                   ("Expected BRD deaths", f"{plan_.deaths:.1f}", _delta(plan_.deaths, cur.deaths, "", lambda v: f"{v:.1f}")),
                                                   ("Antibiotic doses", f"{plan_.doses:,.0f}", _delta(plan_.doses, cur.doses, "", lambda v: f"{v:,.0f}"))))
                    + '</div>'
                    f'<p style="color:#BFD3C7;font-size:.84rem;margin:.6rem 0 0 0">Compared with the yard\'s current approach ({esc(pol)}). '
                    f'For your veterinarian to review before any treatment.</p>')
        if unsure:
            st.warning(f"**Close call on {', '.join(unsure)}.** The records can't tell which option is cheaper for "
                       f"{'this lot' if len(unsure) == 1 else 'these lots'}. Decide with your veterinarian; details below.")
        with st.container(key="card_opts"):
            T.h("The four options", f"Expected over the first 45 days for the {len(arr)} arriving lots ({int(sum(A.loc[l, 'econ']['CS'] for l in arr)):,} cattle).")
            cols = st.columns(4)
            for col, (k, name) in zip(cols, STRATS):
                r_ = S.loc[name]
                hi = k == "plan"
                col.html(f'<div style="border:1px solid {"#2F6B4F" if hi else "var(--line)"};border-radius:14px;padding:14px 16px;'
                         f'background:{"#EEF5F0" if hi else "transparent"};height:100%">'
                         f'<p style="margin:0;font-weight:650">{esc(name)}</p><p class="pp-note" style="margin:.1rem 0 .7rem 0">{esc(OPT_DESC[k])}</p>'
                         f'<p class="pp-note" style="margin:0">Health cost</p><p style="margin:0 0 .4rem 0;font-size:1.15rem;font-weight:650">${r_.cost:,.0f}</p>'
                         f'<p class="pp-note" style="margin:0">BRD deaths</p><p style="margin:0 0 .4rem 0;font-weight:600">{r_.deaths:.1f}</p>'
                         f'<p class="pp-note" style="margin:0">Antibiotic doses</p><p style="margin:0;font-weight:600">{r_.doses:,.0f}</p></div>')
            st.caption("Treating only sick cattle costs least but loses the most cattle; treating every lot loses the fewest but uses the most antibiotics. "
                       f"PenPoint picks the cheaper option for each lot while keeping expected deaths at least {D.margin():.0%} below the current approach.")
        with st.container(key="card_lots_opts"):
            T.h("Lot by lot", "Expected cost of each option for the lot. The recommendation is in bold.")
            for l in arr:
                e, c = A.loc[l, "econ"], A.loc[l, "cls"]
                act = A.loc[l, "action"]
                if not e["robust"]:
                    why = "Close call: the records can't tell which is cheaper. Discuss with your veterinarian."
                elif A.loc[l, "rule_switched"]:
                    why = "Pull-and-treat is cheaper, but metaphylaxis keeps expected deaths below the current approach."
                elif act == "meta":
                    why = "Metaphylaxis is cheaper: enough of these cattle are likely to get sick."
                else:
                    why = "Pull-and-treat is cheaper: too few cattle are likely to get sick to justify treating them all."
                k1, k2, k3, k4 = st.columns([2.2, 1.3, 1.3, .8], vertical_alignment="center")
                k1.html(f'<p style="margin:0;font-weight:650">{esc(l)} <span style="font-weight:400;color:var(--muted)">{esc(L.loc[l, "pen"])}, {e["CS"]} cattle</span></p>'
                        f'<div style="margin:.25rem 0">{lot_chip(l, A)}</div><p class="pp-note" style="margin:0">{esc(why)}</p>')
                for col, kk in ((k2, "meta"), (k3, "pt")):
                    b = act == kk
                    col.html(f'<p class="pp-note" style="margin:0">{esc(OPT[kk])}</p><p style="margin:0;font-size:1.05rem;{"font-weight:700;color:#2F6B4F" if b else "color:var(--muted)"}">'
                             f'{money(e["cost_" + kk])}{" ✓" if b else ""}</p>')
                k4.button("Details", key=f"det_{l}", type="tertiary", on_click=lambda lid=l: ss.update(sub="costs", focus_lot=lid))
                st.html('<div style="border-top:1px solid var(--line);margin:.2rem 0 .4rem 0"></div>')
    on = [l for l in A.index if L.loc[l, "status"] == "in_progress" and not L.loc[l, "metaphylaxis_given"] and A.loc[l, "action"] == "late"]
    if on:
        with st.container(key="card_onfeed"):
            T.h("Lots on feed to discuss with your veterinarian", "More cattle are getting sick than expected; treating the rest of the lot now is "
                "expected to cost less than continuing to treat them one by one.")
            for l in on:
                st.html(f'<p style="margin:.2rem 0"><b>{esc(l)}</b> ({esc(L.loc[l, "pen"])}, day {int(L.loc[l, "days_on_feed"])}): '
                        f'{A.loc[l, "proj"]["so_far"]:.0%} treated so far. Late metaphylaxis {money(A.loc[l, "cost_late"])} vs continuing '
                        f'{money(A.loc[l, "cost_keep"])}.</p>')
    if arr:
        ex = A.loc[arr[0], "econ"]
        T.work([
            ("11", "Cost of metaphylaxis = cattle × drug cost + cattle × cost of a sick animal × expected BRD rate × (1 − share prevented)",
             f"lot {arr[0]}: {ex['CS']} × ${ex['TC']:.2f} + {ex['CS']} × ${ex['MC']:,.0f} × {ex['Em']:.3f} × {1 - ex['ME']:.2f} = {money(ex['cost_meta'])}"),
            ("11", "Cost of pull-and-treat = cattle × cost of a sick animal × expected BRD rate",
             f"lot {arr[0]}: {ex['CS']} × ${ex['MC']:,.0f} × {ex['Em']:.3f} = {money(ex['cost_pt'])}"),
            ("6", "Expected BRD rate = q × m_H + (1 − q) × m_L", f"q = chance the lot is high-risk ({ex['q']:.3f}); m_H = {ex['mH']:.3f}, m_L = {ex['mL']:.3f}"),
            ("1-5", "Rojas et al. (2022) net health cost benefit: TP = CS(MC·m_H·ME − TC), FP = −CS·TC, FN = −CS·MC·m_H·ME, TN = 0",
             "Shown for each lot under Lot-level cost analysis."),
            ("12-13", "Cases = cattle × expected rate × (1 − ME if metaphylaxis); deaths = cases × chance a case dies; doses = cattle (if metaphylaxis) + doses per case × cases",
             "Summed over the arriving lots for each option."),
            ("11c", "Close call = the cheaper option changes between the low and high end of the lot's 90% risk range", "")])


def scenario():
    from .common import analysis as _an
    T.header("Scenario analysis", "Change prices, drug effect, current practice or the deaths margin here and see what happens to the plan. "
             "Nothing here is saved; set permanent values under Constraints and assumptions.")
    A0, s0 = _need()
    c1, c2 = st.columns([1, 1.6])
    with c1:
        with st.container(key="card_sc_in"):
            T.h("What if…")
            tc = st.slider("Metaphylaxis cost, TC ($ per head)", 5.0, 80.0, float(s0.meta_cost), 0.5)
            me = st.slider("Share of cases metaphylaxis prevents, ME", 0.1, 0.9, float(round(1 - s0.meta_rr, 2)), 0.01)
            fp = st.slider("Feeder price ($ per cwt)", 150.0, 500.0, float(s0.feeder_price_cwt), 5.0)
            cfr = st.slider("Chance a sick animal dies", 0.02, 0.30, float(s0.cfr), 0.005)
            pol = {"Buyer's high-risk call": "buyer_high", "Every sale-barn lot": "all_sale_barn", "No metaphylaxis": "none"}
            cur = [k for k, v in pol.items() if v == s0.policy][0]
            policy = pol[st.radio("Current practice gives metaphylaxis on", list(pol), index=list(pol).index(cur))]
            mg = st.slider("No-more-deaths margin", 0.0, 0.3, float(D.margin()), 0.01)
    s1 = s0.with_(meta_cost=tc, meta_rr=1 - me, feeder_price_cwt=fp, cfr=cfr, policy=policy)
    A1, _ = _an(s1, mg)
    S0, S1 = strategy_table(A0), strategy_table(A1)
    with c2:
        with st.container(key="card_sc_out"):
            T.h("Consequences for the arriving lots", "Saved assumptions → this scenario.")
            rows = []
            for i, (k, name) in enumerate(STRATS):
                rows.append(dict(strategy=name, cost0=S0.cost[i], cost1=S1.cost[i], deaths0=S0.deaths[i], deaths1=S1.deaths[i], doses0=S0.doses[i],
                                 doses1=S1.doses[i], meta1=S1.n_meta[i]))
            st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", column_config={
                "strategy": "Approach", "cost0": st.column_config.NumberColumn("Cost now", format="$%,.0f"),
                "cost1": st.column_config.NumberColumn("Cost in scenario", format="$%,.0f"), "deaths0": st.column_config.NumberColumn("Deaths now", format="%.2f"),
                "deaths1": st.column_config.NumberColumn("Deaths in scenario", format="%.2f"), "doses0": st.column_config.NumberColumn("Doses now", format="%,.0f"),
                "doses1": st.column_config.NumberColumn("Doses in scenario", format="%,.0f"), "meta1": "Lots on metaphylaxis"})
            L = ss.lots.set_index("lot_id")
            ch = [l for l in A0.index if A0.loc[l, "action"] != A1.loc[l, "action"]]
            if ch:
                st.html("<p style='margin:.4rem 0 .2rem 0'><b>Lots whose recommendation changes:</b></p>" + "".join(
                    f"<p style='margin:0'>{esc(l)} ({esc(L.loc[l, 'pen'])}): {esc(OPT[A0.loc[l, 'action']])} → <b>{esc(OPT[A1.loc[l, 'action']])}</b></p>" for l in ch))
            else:
                st.html("<p style='margin:.4rem 0 0 0'>No lot's recommendation changes in this scenario.</p>")
            w = float(ss.lots.arrival_weight_lb.mean())
            mc = Mo.mc_parts(s1, w)["mc"]
            st.html(f"<p class='pp-note' style='margin:.4rem 0 0 0'>Break-even BRD rate in this scenario: {tc / (mc * me):.1%} "
                    f"(now {s0.meta_cost / (Mo.mc_parts(s0, w)['mc'] * (1 - s0.meta_rr)):.1%}), at the yard's average weight of {w:,.0f} lb.</p>")
        with st.container(key="card_sc_me"):
            T.h("How the plan's cost depends on ME", "Expected health cost of the arriving lots as the metaphylaxis effect changes, other inputs as in the scenario.")
            xs = np.round(np.linspace(0.2, 0.8, 13), 2)
            ys = {k: [] for k, _ in STRATS}
            for x in xs:
                Ax, _ = _an(s1.with_(meta_rr=1 - x), mg)
                for k, _ in STRATS:
                    ys[k].append(strategy(Ax, k)["cost"])
            fig = go.Figure()
            for i, (k, name) in enumerate(STRATS):
                fig.add_scatter(x=xs, y=ys[k], mode="lines", name=name, line=dict(width=2.5 if k == "plan" else 1.6, color=[T.SERIES[2], T.SERIES[1], T.SERIES[3], T.SERIES[0]][i]))
            fig.add_vline(x=me, line=dict(color="#9AA8A1", dash="dot"))
            fig.update_layout(height=300, xaxis_title="ME (share of cases prevented)", yaxis_title="Expected health cost ($)", yaxis_tickprefix="$")
            T.chart(fig)


def summary_html(A, s):
    L = ss.lots.set_index("lot_id")
    S = strategy_table(A)
    rows = []
    for l in A.index:
        r, c, e = L.loc[l], A.loc[l, "cls"], A.loc[l, "econ"]
        act = A.loc[l, "action"]
        if r.status == "arriving":
            cost = f"{money(e['cost_meta'])} / {money(e['cost_pt'])}"
        elif act in ("late", "keep"):
            cost = f"{money(A.loc[l, 'cost_late'])} / {money(A.loc[l, 'cost_keep'])} (late / continue)"
        else:
            cost = "–"
        why = "; ".join(p["text"] for p in c["path"])
        rows.append(f"<tr><td>{esc(l)}</td><td>{esc(r.pen)}</td><td>{int(r.active_head)}</td><td>{esc(c['chip'])} ({c['score']})</td>"
                    f"<td>{esc(why)}</td><td>{esc(cost)}</td><td><b>{esc(OPT[act])}</b>{' (deaths rule)' if A.loc[l, 'rule_switched'] else ''}"
                    f"{'' if e['robust'] or r.status != 'arriving' else '<br><i>Not confident: information is insufficient</i>'}</td><td></td></tr>")
    strat = "".join(f"<tr><td>{esc(x.strategy)}</td><td>${x.cost:,.0f}</td><td>{x.cases:.1f}</td><td>{x.deaths:.2f}</td><td>{x.doses:,.0f}</td></tr>"
                    for x in S.itertuples())
    pr = ss.protocol
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>PenPoint decision summary {D.AS_OF}</title>
<style>body{{font-family:Georgia,serif;max-width:1000px;margin:2rem auto;color:#1d2a24;line-height:1.45}}h1{{font-size:1.6rem;margin:0}}
table{{border-collapse:collapse;width:100%;font-size:.85rem;margin:.6rem 0 1.2rem}}td,th{{border:1px solid #cfd8d3;padding:5px 7px;text-align:left;vertical-align:top}}
th{{background:#eef3f0}}.note{{font-size:.85rem;color:#4a5a52}}</style></head><body>
<h1>BRD decision summary: {esc(ss.yard['name'])}</h1><p class="note">Prepared {D.AS_OF:%B %d, %Y} by PenPoint. Decision support only: every medication decision
is subject to review and approval by the attending veterinarian.</p>
<h2>Approaches compared (arriving lots, first 45 days)</h2><table><tr><th>Approach</th><th>Expected health cost</th><th>BRD cases</th><th>BRD deaths</th>
<th>Antimicrobial doses</th></tr>{strat}</table>
<p class="note">Current practice: {esc({"buyer_high": "metaphylaxis when the buyer calls a lot high-risk", "all_sale_barn": "metaphylaxis on every sale-barn lot", "none": "no metaphylaxis"}[s.policy])}.
Assumptions: metaphylaxis ${s.meta_cost:.2f}/head, prevents {1 - s.meta_rr:.0%} of cases; case fatality {s.cfr:.1%}; feeder price ${s.feeder_price_cwt:.0f}/cwt.
The plan keeps expected BRD deaths at least {D.margin():.0%} below current practice.</p>
<h2>Lot by lot</h2><table><tr><th>Lot</th><th>Pen</th><th>Head</th><th>Risk (score)</th><th>Why (decision tree)</th><th>Expected cost: metaphylaxis / pull-and-treat</th>
<th>Recommended</th><th>Vet approval</th></tr>{''.join(rows)}</table>
<h2>Protocol on file</h2><p class="note">Metaphylaxis: {esc(pr['metaphylaxis']['drug'])} ({esc(pr['metaphylaxis']['product'])}), {esc(pr['metaphylaxis']['drug_class'])},
{pr['metaphylaxis']['withdrawal_days']:.0f}-day withdrawal. First treatment: {esc(pr['first']['drug'])} ({esc(pr['first']['product'])}). Retreatment:
{esc(pr['retreat']['drug'])} ({esc(pr['retreat']['product'])}). {esc(D.PROTOCOL_NOTE)}</p>
<p>Reviewed by (veterinarian): ______________________ &nbsp; Date: ____________ &nbsp; Signature: ______________________</p>
<p class="note">Method: risk from a decision tree (Rojas et al. 2022 method) adjusted for each lot's preconditioning, vaccination, haul time, purchase channel and
weight; costs from the net health cost benefit (Rojas et al. 2022, Eqs 1-5). Full equations: PenPoint, About the model.</p></body></html>"""


def tracking():
    T.header("Treatment response", "Which lots and cattle were treated, with what, and how well treatment is working.", f"{D.AS_OF:%b %d, %Y}")
    A, s = _need()
    L = ss.lots.set_index("lot_id")
    ev = ss.events
    tx = ev[ev.type.isin(D.TREAT)]
    a = D.animal_status()
    rows = []
    for lid in A.index:
        r = L.loc[lid]
        if r.status != "in_progress":
            continue
        g = tx[tx.lot_id == lid]
        firsts = g[g.type == "BRD treatment"].groupby("animal_id")["day"].min()
        old = firsts[firsts <= r.days_on_feed - 10]
        retx = g.groupby("animal_id").size()
        died = set(a[(a.lot_id == lid) & (a.status == "Dead")].animal_id)
        later = g.merge(old.rename("d0"), left_on="animal_id", right_index=True)
        fail = set(later[(later.type == "Retreatment") & (later.day <= later.d0 + 10)].animal_id) | (set(old.index) & died)
        pj = A.loc[lid, "proj"]
        exp_now = pj["Em"] * pj["F"]
        rows.append(dict(lot=lid, pen=r.pen, day=int(r.days_on_feed), meta="Yes" if r.metaphylaxis_given else "No",
                         treated=len(firsts), rate=pj["so_far"], expected=exp_now * (s.meta_rr if r.metaphylaxis_given else 1.0),
                         effect=(1 - pj["so_far"] / exp_now) if (r.metaphylaxis_given and exp_now > 0) else np.nan,
                         success=(1 - len(fail) / len(old)) if len(old) else np.nan, n_old=len(old),
                         retreat=(retx >= 2).sum() / len(retx) if len(retx) else np.nan, died=len(died)))
    T_ = pd.DataFrame(rows)
    if T_.empty:
        st.info("No lots on feed yet.")
        return
    k = st.columns(4)
    with k[0]:
        T.kpi("Lots that got metaphylaxis", f"{(T_.meta == 'Yes').sum()} of {len(T_)}", "pill", "sky", key="tile_t1")
    with k[1]:
        T.kpi("Cattle treated for BRD", f"{int(T_.treated.sum())}", "heart", "rust", key="tile_t2")
    with k[2]:
        tot_old = T_.n_old.sum()
        succ = np.nansum(T_.success * T_.n_old) / tot_old if tot_old else np.nan
        T.kpi("Treatment success", "–" if np.isnan(succ) else f"{succ:.0%}", "check", "pine", "no retreat or death in 10 days", None, key="tile_t3")
    with k[3]:
        T.kpi("Died", f"{int(T_.died.sum())}", "alert", "amber", key="tile_t4")
    st.dataframe(T_.drop(columns=["n_old"]), hide_index=True, width="stretch",
                 column_config={"lot": "Lot", "pen": "Pen", "day": "Day on feed", "meta": "Metaphylaxis on arrival", "treated": "Treated for BRD",
                                "rate": st.column_config.NumberColumn("BRD rate so far", format="percent"),
                                "expected": st.column_config.NumberColumn("Expected by now", format="percent"),
                                "effect": st.column_config.NumberColumn("Metaphylaxis effect", format="percent"),
                                "success": st.column_config.NumberColumn("Treatment success", format="percent"),
                                "retreat": st.column_config.NumberColumn("Retreated", format="percent"), "died": "Died"})
    ex = T_.iloc[0]
    T.work([("5", "BRD rate so far = cattle treated at least once ÷ head count", f"e.g. lot {ex.lot}: {ex.treated} treated → {ex.rate:.1%}"),
            ("", "Expected by now = E[m] × F(d), × (1 − ME) if the lot got metaphylaxis",
             "E[m] from the tree (eq. 6); F(d) is the share of 45-day cases usually seen by day d (eq. 18)."),
            ("15", "Metaphylaxis effect so far = 1 − BRD rate so far ÷ expected rate without metaphylaxis at this day",
             "Shown only for lots that got metaphylaxis; compare with ME on the Constraints page."),
            ("16", "Treatment success = treated at least 10 days ago and not retreated or dead within 10 days ÷ treated at least 10 days ago", ""),
            ("17", "Retreated = cattle treated 2 or more times ÷ cattle treated", "")])
