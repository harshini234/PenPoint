from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from .. import data as D
from .. import model as Mo
from .. import theme as T
from ..theme import esc
from .common import BAND_COLOR, analysis, lot_chip, risk_work, sensehub_chip, why_html

ss = st.session_state


def render(sub, yard=None):
    if ss.get("herd_lot") and ss.herd_lot in set(ss.lots.lot_id):
        return info(ss.herd_lot)
    overview()


def weather_card():
    from .lots_weather import card
    card()


def overview():
    T.header("Risk overview", "Which lots are most likely to have a BRD problem, and which cattle need a look today.", f"{D.AS_OF:%b %d, %Y}")
    A, s = analysis()
    if A.empty:
        st.info("No cattle yet. Import or add them under Lot management.")
        return
    M = Mo.get()
    L = ss.lots.set_index("lot_id")
    a = D.animal_status()
    att = a[a.status.isin(["In treatment", "Alert"])]
    calls = pd.Series({l: A.loc[l, "cls"]["chip"] for l in A.index})
    k = st.columns(4)
    for i, (lab, tone, ic) in enumerate((("High risk", "rust", "alert"), ("Not sure yet", "amber", "signal"), ("Low risk", "pine", "check"))):
        ids = calls[calls == lab].index
        with k[i]:
            T.kpi(lab, f"{len(ids)} lot{'s' if len(ids) != 1 else ''}", ic, tone, f"{int(L.loc[ids, 'active_head'].sum()):,} cattle" if len(ids) else "none", None, key=f"tile_r{i}")
    with k[3]:
        T.kpi("Need attention", f"{len(att)} cattle", "heart", "sky", "sick or flagged", None, key="tile_r3")

    order = {"High risk": 0, "Not sure yet": 1, "Low risk": 2}
    ids = sorted(A.index, key=lambda l: (order[A.loc[l, "cls"]["chip"]], -A.loc[l, "cls"]["p"]))
    rows = []
    for l in ids:
        r, c = L.loc[l], A.loc[l, "cls"]
        rows.append(dict(lot=l, pen=r.pen, cattle=int(r.active_head),
                         stage=(f"Day {int(r.days_on_feed)} on feed" if r.status == "in_progress" else f"Arrives {pd.Timestamp(r.arrival_date):%b %d}"),
                         risk=c["chip"], score=c["score"],
                         sofar=(f'{A.loc[l, "proj"]["so_far"]:.0%}' if r.status == "in_progress" else "Not arrived"),
                         attention=int((att.lot_id == l).sum())))
    with st.container(key="card_risklots"):
        T.h("Lots, highest risk first", "Select a lot to see why it got its rating.")
        ev_ = st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch", on_select="rerun", selection_mode="single-row", key="risk_tbl",
                           column_config={
                               "lot": "Lot", "pen": "Pen", "cattle": "Cattle", "stage": "Stage", "risk": "Rating",
                               "score": st.column_config.ProgressColumn("Risk score", min_value=0, max_value=100, format="%d",
                                                                        help="Chance out of 100 that the lot ends up with 15% or more of its cattle treated for BRD."),
                               "sofar": "Treated for BRD so far",
                               "attention": st.column_config.NumberColumn("Need attention")})
        sel = ev_.selection.rows if ev_ and ev_.selection else []
        if sel:
            ss.herd_lot = rows[sel[0]]["lot"]
            st.rerun()
        st.caption(f"Risk score: the chance, out of 100, that a lot ends up with 15% or more of its cattle treated for BRD in the first 45 days. "
                   f"PenPoint rates a lot high risk from {100 * M['t_star']:.0f} out of 100. 'Not sure yet' means the records can't settle which side it falls on.")
    with st.container(key="card_attn"):
        T.h("Cattle needing attention", "Treated in the last 4 days, or flagged by SenseHub and not yet treated.")
        if att.empty:
            st.html('<p class="pp-note">None today.</p>')
        else:
            sh = D.sensehub_status()
            t = att.assign(pen=att.lot_id.map(ss.lots_all.set_index("lot_id").pen),
                           why=[("SenseHub alert" + (f" ({sh['label']})" if sh and sh["stale"] else "")) if x == "Alert" else
                                f"In treatment (treatment #{n})" for x, n in zip(att.status, att.n_tx)],
                           rating=att.lot_id.map(calls))
            t = t.sort_values(["status", "lot_id"])
            st.dataframe(t[["animal_id", "lot_id", "pen", "why", "rating"]], hide_index=True, width="stretch",
                         column_config={"animal_id": "Animal", "lot_id": "Lot", "pen": "Pen", "why": "Reason", "rating": "Lot rating"})
    weather_card()


def info(lot_id):
    A, s = analysis()
    M = Mo.get()
    r = ss.lots_all.set_index("lot_id").loc[lot_id]
    c = A.loc[lot_id, "cls"]
    def back():
        ss.herd_lot = None
        ss.pop("risk_tbl", None)
    st.button("All lots", icon=":material/arrow_back:", type="tertiary", on_click=back)
    T.header(f"Lot {lot_id}", f"{r.pen}, {int(r.active_head)} cattle, " + (f"day {int(r.days_on_feed)} on feed." if r.status == "in_progress"
                                                                           else f"arrives {pd.Timestamp(r.arrival_date):%b %d}."))
    k = st.columns(3)
    tone = {"High risk": "rust", "Not sure yet": "amber", "Low risk": "pine"}[c["chip"]]
    with k[0]:
        T.kpi("Risk call", c["chip"], "pulse", tone, key="tile_i1")
    with k[1]:
        T.kpi("Risk score", f"{c['score']} of 100", "signal", "sky", f"yard average {100 * M['prevalence']:.0f}", None, key="tile_i2")
    with k[2]:
        if r.status == "in_progress":
            pj = A.loc[lot_id, "proj"]
            T.kpi("Treated for BRD so far", f"{pj['so_far']:.0%}", "heart", "rust", f"{pj['sick']} of {pj['CS']} cattle", None, key="tile_i3")
        else:
            T.kpi("Cattle", f"{int(r.active_head)}", "cow", "hay", "not arrived yet", None, key="tile_i3")
    c1, c2 = st.columns([1.35, 1])
    with c1:
        with st.container(key="card_why"):
            T.h(f"Why this lot is {c['chip'].lower()}", "The decision tree's questions, in order, and this lot's answers.")
            st.html(why_html(c, M))
            if c["unsure"]:
                st.html(f'<p class="pp-note" style="margin:.4rem 0 0 0">Not sure yet: the likely share for this group runs from {c["lo"]:.0%} to {c["hi"]:.0%}, '
                        f'which crosses the high-risk line. More history or more details about the lot would settle it.</p>')
            risk_work(c, M)
    with c2:
        with st.container(key="card_known"):
            T.h("What PenPoint knows")
            items = [("Average arrival weight", f"{r.arrival_weight_lb:,.0f} lb"), ("Head count", f"{int(r.head_count)}"),
                     ("Sex", "Conflict" if "sex" in (r.conflicts or {}) else D.SEXES.get(r.sex, "Not known")),
                     ("Preconditioning", "Conflict" if "preconditioning" in (r.conflicts or {}) else D.PRECOND.get(r.preconditioning, "Not known")),
                     ("Vaccinated before arrival", "Conflict" if "pre_arrival_vaccinated" in (r.conflicts or {}) else
                      ("Not known" if r.pre_arrival_vaccinated is None or pd.isna(r.pre_arrival_vaccinated) else ("Yes" if r.pre_arrival_vaccinated else "No"))),
                     ("Average haul time", "Not known" if pd.isna(r.haul_hours) else f"{r.haul_hours:.1f} h"),
                     ("Arrival quarter", f"Q{int(r.arrival_quarter)}" if pd.notna(r.arrival_quarter) else "Not known"),
                     ("Pen area, bunk length", f"{r.pen_area_m2:,.0f} m², {r.bunk_m:,.0f} m")]
            st.html("".join(f'<div class="action" style="padding:6px 0"><div style="flex:1;color:var(--muted)">{esc(a)}</div>'
                            f'<div style="font-weight:600;{"color:#9A3B27" if b in ("Conflict", "Not known") else ""}">{esc(b)}</div></div>' for a, b in items))
            if r.conflicts:
                st.caption("Conflicts are left out of the risk call until fixed under Lot management.")
        if r.status == "in_progress":
            with st.container(key="card_sofar"):
                pj = A.loc[lot_id, "proj"]
                T.h("So far", f"Day {pj['d']} on feed.")
                st.html(f'<p style="margin:0">{pj["sick"]} of {pj["CS"]} cattle treated for BRD ({pj["so_far"]:.0%}). The 15% high-risk line would be '
                        f'{0.15 * pj["CS"]:.0f} cattle.</p>')
                T.work([("5", "BRD rate so far = (cattle treated for BRD at least once) ÷ head count",
                         f"= {pj['sick']} ÷ {pj['CS']} = {pj['so_far']:.1%}")])
        sh = D.sensehub_status()
        a = D.animal_status()
        n_al = int(((a.lot_id == lot_id) & (a.status == "Alert")).sum())
        if sh and n_al:
            st.html(f'<p class="pp-note">{n_al} cattle flagged by SenseHub {sensehub_chip()}</p>')
    with st.container(key="feature_link"):
        e = A.loc[lot_id, "econ"]
        st.html('<p class="pp-h" style="color:#fff">Treatment options and costs</p>'
                '<p style="color:#DCE8E0;margin:.2rem 0 .6rem 0">Compare metaphylaxis with pull-and-treat for this lot, with every cost worked out.</p>')
        st.button("See treatment options and costs", key="to_costs",
                  on_click=lambda: ss.update(section="options", sub="costs", focus_lot=lot_id, herd_lot=None))
