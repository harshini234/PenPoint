from __future__ import annotations

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import data as D
from .. import model as Mo
from .. import theme as T
from ..theme import esc

ss = st.session_state


def render(sub, yard=None):
    {"equations": equations, "works": works, "sources": sources, "reqs": reqs}[sub]()


REQS = [
    ("Enter or upload data and inspect relevant cattle or groups",
     "Import a whole yard (cattle, health records, SenseHub) or add lots and animals by hand; open any lot to see every animal, its treatments "
     "(drug, class, withdrawal) and its lot's averaged values.", [("lots", "add", "Add or import data"), ("lots", "cards", "Lots and cattle")]),
    ("Identify priorities and understand the basis and uncertainty of the assessment",
     "Lots ranked by risk; each shows the decision tree's questions, the starting estimate from similar past lots, the adjustment for its own "
     "haul time, preconditioning, vaccination, channel and weight, and a 90% range.", [("herd", "lots", "Risk overview"), ("options", "today", "Daily action list")]),
    ("Compare management options against a clearly defined current operating approach",
     "Current practice is chosen on Constraints and assumptions. Treatment options compares it with metaphylaxis on every lot, pull-and-treat on "
     "every lot and PenPoint's plan, by cost, cases, deaths and doses, plus each lot's two options.", [("options", "compare", "Treatment options"),
                                                                                                    ("options", "costs", "Lot-level cost analysis")]),
    ("Change relevant inputs, assumptions or constraints and see the consequences",
     "Costs, drug effect, risk-factor odds ratios, protocol, current practice and the deaths margin are editable and saved; Scenario "
     "analysis tries values without saving and shows which lots change.", [("lots", "operation", "Constraints and assumptions"),
                                                                           ("options", "scenario", "Scenario analysis")]),
    ("Produce a clear, usable decision summary",
     "One page per decision date: approaches compared, every lot's risk, reason, costs and recommendation, the protocol on file and a vet "
     "approval line. Downloads as HTML to print or save as PDF.", [("options", "plan", "Decision summary")]),
    ("Make trade-offs visible rather than present a recommendation without context",
     "Cost against antimicrobial doses and deaths for each approach (table and chart); the four outcomes (TP, FP, FN, TN) for each lot; the "
     "no-more-deaths rule is shown wherever it changes a recommendation.", [("options", "compare", "Treatment options")]),
    ("Indicate when the available information cannot support a confident decision",
     "Risk calls are 'Not sure yet' when the 90% range crosses the high-risk line or too few similar lots exist; a lot's option is marked "
     "'Not confident: vet review' when the cheaper option flips across that range.", [("herd", "lots", "Risk overview"), ("options", "compare", "Treatment options")]),
    ("Not a static dashboard of precomputed results",
     "Data live in a database (PostgreSQL via DATABASE_URL); every number is recalculated from the saved data and assumptions on each change.",
     [("lots", "add", "Add or import data")]),
    ("Medication-related recommendations remain subject to veterinary review",
     "Every recommendation carries the vet-review note; drugs come from a protocol your veterinarian sets; late metaphylaxis is framed as a vet "
     "decision; the decision summary has a vet approval line.", [("lots", "operation", "Constraints and assumptions"), ("options", "plan", "Decision summary")]),
]


def reqs():
    T.header("Brief requirements", "Where each dashboard requirement in the hackathon brief is met. Press a button to go there.")
    for i, (req, how, links) in enumerate(REQS):
        with st.container(key=f"card_req_{i}"):
            c1, c2 = st.columns([3, 1.3], vertical_alignment="center")
            c1.html(f'<p class="pp-h" style="font-size:1rem;margin:0">{esc(req)}</p><p style="margin:.25rem 0 0 0;color:var(--muted)">{esc(how)}</p>')
            for sec, sub, lab in links:
                c2.button(lab, key=f"rq_{i}_{sub}", icon=":material/arrow_forward:", width="stretch",
                          on_click=lambda a=sec, b=sub: st.session_state.update(section=a, sub=b, open_lot=None, herd_lot=None))


def _eq(n, formula, words, now=""):
    return (f'<div class="eqrow"><span class="eqn">({n})</span><div><p class="eqf">{esc(formula)}</p><p class="eqw">{esc(words)}</p>'
            f'{f"<p class=eqv>Now: {esc(now)}</p>" if now else ""}</div></div>')


def equations():
    T.header("Methods and equations", "Every equation PenPoint uses, in plain words, with today's values. Numbers in brackets match the "
             "Show the work notes across the site.")
    M = Mo.get()
    r = Mo.rates(M)
    s = D.settings()
    w = float(ss.lots.arrival_weight_lb.mean()) if len(ss.lots) else 550.0
    p = Mo.mc_parts(s, w)
    me = 1 - s.meta_rr
    sections = [
        ("Lot values", [
            ("1", "Average arrival weight = (sum of every animal's arrival weight) ÷ (number of animals)", "Weight is the one value always taken from the animals."),
            ("2", "Head count (CS) = animals in the lot, including any that died", "Animals moved out or entered by mistake don't count."),
            ("", "Sex, preconditioning, vaccination, haul time, buyer's call: entered once for the lot",
             "If any animal disagrees with the lot, it's a conflict and that value is left out until resolved.")]),
        ("Risk: the decision tree (Rojas et al. 2022 method)", [
            ("", "Predictors: head count, average arrival weight, arrival quarter, sex, total pen area, bunk length, pen area per head, bunk length per head "
                 "(the paper's Table 2), plus preconditioning, vaccination and haul time",
             f"Trained on {M['n_train']} of {M['n_hist']} history lots (75%), tested on the other {M['n_test']} (25%), split so both have the same share of "
             f"high-risk lots, tuned with 10-fold cross-validation. Chosen settings: depth {M['params']['max_depth']}, at least {M['params']['min_samples_leaf']} lots per branch."),
            ("", "High-risk lot = 15% or more of the lot treated for BRD at least once in its first 45 days", "The outcome the tree learns, as in the paper."),
            ("3", "Starting estimate p₀ = (high-risk lots in this lot's branch) ÷ (all lots in that branch)",
             "The share of similar past lots that became high-risk.", f"yard average {M['prevalence']:.1%}"),
            ("3b", "logit(p) = logit(p₀) + Σₖ ln(ORₖ) × (xₖ − x̄ₖ)",
             "Adjusts for this lot's own preconditioning, pre-arrival vaccination, haul ≥ 6 h, sale-barn purchase and weight, relative to the "
             "average of the branch's past lots, so a factor the tree already split on isn't counted twice. Unknown factors add nothing.",
             "ORs: " + ", ".join(f"{f['name'].split(' (')[0].lower()} {Mo.factor_effect(f):.2f}" for f in Mo.FACTORS)),
            ("3c", "Risk score = 100 × p", "A score of 30 means a 30% chance the lot becomes high-risk."),
            ("4", "High risk if the branch share ≥ t*, where t* maximizes Youden's J = Se + Sp − 1", "The cutoff method the paper uses.", f"t* = {M['t_star']:.3f}"),
            ("4a", "Not sure yet if the 90% range (Wilson interval for the branch, shifted by 3b) crosses t*, or the branch has fewer than 20 lots",
             "Flags lots where the data can't support a confident call."),
            ("11c", "Decision confidence: recompute (11) with q at both ends of the 90% range",
             "If the cheaper option differs at the two ends, the lot is marked 'Not confident: vet review'."),
            ("5", "BRD rate so far = cattle treated for BRD at least once ÷ head count", "For lots already on feed.")]),
        ("How accurate the tree is (25% of history held back)", [
            ("6a", "Se = TP ÷ (TP + FN);  Sp = TN ÷ (TN + FP)", "Share of high-risk lots caught; share of low-risk lots correctly passed.",
             f"Se {r['se']:.1%}, Sp {r['sp']:.1%}"),
            ("6b", "PPV = TP ÷ (TP + FP);  NPV = TN ÷ (TN + FN)", "Chance a lot called high really is high; chance a lot called low really is low.",
             f"PPV {r['ppv']:.1%}, NPV {r['npv']:.1%}")]),
        ("Costs (Rojas et al. 2022, economic analysis)", [
            ("10a", "Cost of a death = weight × feeder price + feed and yardage until death + treatment", "", f"${p['death']:,.0f} at {w:,.0f} lb"),
            ("10", "MC = (1 − chance of death) × (treatment + lost gain) + chance of death × cost of a death", "Cost of one sick animal.", f"${p['mc']:,.0f}"),
            ("6", "E[m] = q × m_H + (1 − q) × m_L", "Expected BRD rate of a lot. q = share of high-risk lots in its branch; m_H, m_L = average BRD rates of "
                  "high- and low-risk lots in history.", f"m_H {M['mH']:.1%}, m_L {M['mL']:.1%}"),
            ("1R", "NHCB = TPcost + TNcost + FPcost + FNcost  [Rojas Eq 1]", "Net health cost benefit of a way of deciding."),
            ("7", "TP = CS × (MC × m_H × ME − TC)  [Rojas Eq 3, corrected]",
             "Truly high-risk and treated: sick animals avoided, minus the treatment bill. As printed, Eq 3 multiplies by TC and uses BRD45 (the share of lots "
             "that are high-risk); the units only work with CS and the BRD rate inside a high-risk lot (the paper's Table 3 lists 27%), so PenPoint uses that."),
            ("8", "FP = −CS × TC [Eq 4];  FN = −CS × MC × m_H × ME [Eq 5];  TN = $0 [Eq 2]",
             "Treated but didn't need it; needed it but wasn't treated (savings missed); correctly left alone."),
            ("9", "NHCB per animal = [p × Se × TP + (1 − p)(1 − Sp) × FP + p × (1 − Se) × FN] ÷ CS",
             "How the tree is compared with the buyer's call; p is the share of lots that are high-risk."),
            ("11", "Metaphylaxis: CS × TC + CS × MC × E[m] × (1 − ME);  pull-and-treat: CS × MC × E[m]", "Expected cost of each option for one lot. The cheaper one is recommended."),
            ("11b", "Break-even BRD rate = TC ÷ (MC × ME)", "Metaphylaxis pays above this.", f"{s.meta_cost / (p['mc'] * me):.1%}"),
            ("12", "Expected BRD cases = CS × E[m] × (1 − ME if metaphylaxis, else 1)", ""),
            ("13", f"Antimicrobial doses = CS (if metaphylaxis) + {s.doses_per_case:.2f} × expected cases", "Doses per treated case from the parameter list."),
            ("14", "Plan cost = sum of (11) over arriving lots for the chosen options", ""),
            ("", f"No-more-deaths rule: expected deaths = cases × chance of death; the plan's deaths must be at least {D.margin():.0%} "
                 "below current practice, switching lots to metaphylaxis (cheapest per death avoided first) until they are", "")]),
        ("Lots already on feed", [
            ("18", "F(d) = share of a lot's 45-day BRD cases usually seen by day d", "The onset curve."),
            ("19", "Projected rate = F(d) × (rate so far ÷ F(d)) + (1 − F(d)) × E[m]", "Leans on the lot's own record as days pass."),
            ("20", "Cases still to come = cattle × projected rate × (1 − F(d))", ""),
            ("21", "Late metaphylaxis = cattle × TC + MC × cases to come × (1 − ME × late share)",
             f"Late share {s.late_meta_fraction:.0%}: assumed effect of metaphylaxis given after arrival, relative to on arrival."),
            ("22", "Keep pulling and treating = MC × cases to come", "")]),
        ("Treatment response", [
            ("15", "Metaphylaxis effect so far = 1 − BRD rate so far ÷ expected rate without it by now", ""),
            ("16", "Treatment success = not retreated or dead within 10 days ÷ treated at least 10 days ago", ""),
            ("17", "Retreated = treated 2 or more times ÷ treated", ""),]),
    ]
    for title, eqs in sections:
        with st.container(key=f"card_eq_{title[:8].replace(' ', '_').replace(':', '')}"):
            T.h(title)
            st.html("".join(_eq(*e) for e in eqs))


def works():
    T.header("Model validation", "How the decision tree did on history lots it never saw, and what it is worth against the buyer's call.")
    M = Mo.get()
    r, b = Mo.rates(M), Mo.rates(M["buyer"])
    c1, c2 = st.columns(2)
    for col, name, cm, rt in ((c1, "Decision tree", M, r), (c2, "Buyer's call (current practice)", M["buyer"], b)):
        with col:
            with st.container(key=f"card_cm_{name[:5]}"):
                T.h(name, f"{M['n_test']} held-back lots.")
                st.html(f'<table style="width:100%;border-collapse:collapse;font-size:.92rem">'
                        f'<tr><td></td><td style="color:var(--muted);padding:4px">Truly high</td><td style="color:var(--muted);padding:4px">Truly low</td></tr>'
                        f'<tr><td style="color:var(--muted);padding:4px">Called high</td><td style="padding:4px"><b>{cm["tp"]}</b> TP</td><td style="padding:4px"><b>{cm["fp"]}</b> FP</td></tr>'
                        f'<tr><td style="color:var(--muted);padding:4px">Called low</td><td style="padding:4px"><b>{cm["fn"]}</b> FN</td><td style="padding:4px"><b>{cm["tn"]}</b> TN</td></tr></table>'
                        f'<p style="margin:.6rem 0 0 0">Se {rt["se"]:.1%}, Sp {rt["sp"]:.1%}, PPV {rt["ppv"]:.1%}, NPV {rt["npv"]:.1%}, accuracy {rt["acc"]:.1%}</p>')
    st.html(f'<p class="pp-note">Tree AUC {M["test_auc"]:.3f} on held-back lots ({M["cv_auc"]:.3f} in cross-validation). Rojas et al. reported 0.682 for their tree, '
            f'Se 44.7% and Sp 83.7%; the buyer (human) in their data had Se 83.75% and Sp 59.79%.</p>')
    s = D.settings()
    w = float(ss.lots.arrival_weight_lb.mean()) if len(ss.lots) else 550.0
    MC = Mo.mc_parts(s, w)["mc"]
    ME, TC, CS = 1 - s.meta_rr, s.meta_cost, 100
    ps = np.linspace(0, 1, 41)
    tree = [Mo.nhcb_method(M, p, M["mH"], MC, ME, TC, CS) for p in ps]
    buyer = [Mo.nhcb_method(M["buyer"], p, M["mH"], MC, ME, TC, CS) for p in ps]
    with st.container(key="card_nhcbcurve"):
        T.h("Tree vs buyer's call, by share of high-risk lots", "Like the paper's figure: NHCB per animal of the tree minus the buyer's. Above $0, the tree saves money.")
        fig = go.Figure()
        fig.add_scatter(x=100 * ps, y=np.array(tree) - np.array(buyer), mode="lines", line=dict(color=T.SERIES[0], width=2.5),
                        hovertemplate="%{x:.0f}% high-risk lots: %{y:$.2f} per animal<extra></extra>")
        fig.add_hline(y=0, line=dict(color="#9AA8A1", width=1))
        fig.add_vline(x=100 * M["prevalence"], line=dict(color="#9AA8A1", dash="dot", width=1), annotation_text="this yard's history",
                      annotation_font_color=T.MUTED)
        fig.update_layout(xaxis_title="Share of arriving lots that are high-risk (%)", yaxis_title="Tree minus buyer ($ per animal)", yaxis_tickprefix="$")
        T.chart(fig, 340)
        i = int(np.argmin(abs(ps - M["prevalence"])))
        T.work([("9", "NHCB per animal = [p × Se × TP + (1 − p)(1 − Sp) × FP + p × (1 − Se) × FN] ÷ CS",
                 f"at p = {ps[i]:.2f}: tree ${tree[i]:.2f}, buyer ${buyer[i]:.2f}; difference {tree[i] - buyer[i]:+.2f} $ per animal",
                 f"Using MC ${MC:,.0f}, ME {ME:.2f}, TC ${TC:.2f}, m_H {M['mH']:.3f}. CS cancels out per animal.")])
    st.caption("Training data: the paper's data are proprietary, so the tree learns from PenPoint's simulated yard history, calibrated to the paper's published "
               "figures (about 10% high-risk lots; 27% and 4% BRD rates in high- and low-risk lots). A yard's own records would replace it.")


def sources():
    from brd import params as P
    T.header("Parameter sources", "Every number PenPoint uses, where it comes from, and how firm it is.")
    led = P.ledger_frame()
    q = st.text_input("Search", placeholder="e.g. metaphylaxis")
    v = led if not q else led[led.description.str.contains(q, case=False) | led.id.str.contains(q, case=False)]
    v = v.assign(value=v["value"].astype(str))
    st.dataframe(v[["id", "description", "value", "unit", "tag", "source", "link", "location", "notes"]], hide_index=True, width="stretch", height=560,
                 column_config={"link": st.column_config.LinkColumn("Link"), "id": "Parameter", "description": "What it is", "tag": "Evidence"})
    st.caption("Obs: reported in the source. Est: our estimate from sources. Calibrated: fitted so simulated history matches published figures. Assume: our assumption.")
