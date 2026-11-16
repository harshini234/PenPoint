from __future__ import annotations

import io
from datetime import date

import numpy as np
import pandas as pd
import streamlit as st

from .. import data as D
from .. import db
from .. import theme as T
from ..theme import esc
from .common import analysis, lot_chip, sensehub_chip

ss = st.session_state
BADGE = {"Healthy": "green", "Recovered": "blue", "Retreated": "violet", "Alert": "orange", "In treatment": "red",
         "Died": "gray", "Sold": "gray", "Culled": "gray"}
PAGE = 25
PC = [None, "VAC45", "VAC34", "VAC24", "none"]
YN = {None: "Not known", True: "Yes", False: "No"}


def render(sub, yard=None):
    {"cards": lots_page, "add": add_page, "operation": constraints}[sub]()


def _gone(g):
    k = g.removed_reason.value_counts()
    parts = [f"{int(k[r])} {w}" for r, w in (("Died", "died"), ("Sold", "sold"), ("Culled or railed", "culled")) if k.get(r, 0)]
    return ", ".join(parts) or "none"


def _f(v, kind=None):
    v = D._none(v)
    if v is None or v == "":
        return "Not known"
    if kind == "lb":
        return f"{v:,.0f} lb"
    if kind == "h":
        return f"{v:.1f} h"
    if kind == "yn":
        return "Yes" if bool(v) else "No"
    if kind == "pc":
        return D.PRECOND.get(v, v)
    if kind == "sex":
        return D.SEXES.get(v, str(v).capitalize())
    if kind == "chan":
        return D.CHANNEL.get(v, v)
    return str(v)


def herd_values(r, cows):
    g = cows[cows.lot_id == r.lot_id]
    conf = r.conflicts or {}
    nh, nw = int(r.n_haul or 0), int(r.n_weight or 0)
    haul_note = (f"average of {nh} animals" + (f", {len(g) - nh} not recorded" if len(g) - nh else "") if nh else
                 "from the lot record (no animal has a haul time)" if r.haul_source == "lot record" else "")
    rows = [("Head count", f"{int(r.head_count)}", f"{int(r.active_head)} in the lot now"),
            ("Average arrival weight", _f(r.arrival_weight_lb, "lb"), f"average of {nw} animals" if nw else ""),
            ("Average haul time", _f(r.haul_hours, "h"), haul_note),
            ("Arrival date", _f(r.arrival_date), f"quarter {int(r.arrival_quarter)}" if pd.notna(r.arrival_quarter) else ""),
            ("Sex", "Conflict: needs resolving" if "sex" in conf else _f(r.sex, "sex"), ""),
            ("Preconditioning", "Conflict: needs resolving" if "preconditioning" in conf else _f(r.preconditioning, "pc"), ""),
            ("Vaccinated before arrival", "Conflict: needs resolving" if "pre_arrival_vaccinated" in conf else _f(r.pre_arrival_vaccinated, "yn"), ""),
            ("Bought through", _f(r.market_channel, "chan"), ""),
            ("Buyer's risk call", _f(r.buyer_risk_call).capitalize(), ""),
            ("Pen area, bunk length", f"{r.pen_area_m2:,.0f} m², {r.bunk_m:,.0f} m", f"{r.pen_area_m2_per_head:.1f} m² and {r.bunk_cm_per_head / 100:.2f} m a head")]
    st.html("".join(f'<div class="action" style="padding:6px 0"><div style="flex:1;color:var(--muted)">{esc(a)}</div>'
                    f'<div style="font-weight:600;{"color:#9A3B27" if "Conflict" in b else ""}">{esc(b)}'
                    f'<span style="color:var(--muted);font-weight:400;font-size:.8rem">{"  " + esc(c) if c else ""}</span></div></div>'
                    for a, b, c in rows))
    for f, ids in conf.items():
        st.warning(f"**{D.FIELD_LABEL[f]} conflict.** The lot says {_f(_lot_value(r.lot_id, f), _kind(f))}, "
                   f"but {len(ids)} animal{'s' if len(ids) > 1 else ''} ({', '.join(ids[:6])}{'…' if len(ids) > 6 else ''}) "
                   f"{'say' if len(ids) > 1 else 'says'} otherwise. This category is left out of the risk calculation until you correct the lot or those animals.")
    if len(g):
        hv = pd.to_numeric(g.haul_hours, errors="coerce").dropna()
        T.work([("1", "Average arrival weight = (sum of the animals' arrival weights) ÷ (animals with a weight)",
                 f"= {g.weight_lb.sum():,.0f} lb ÷ {nw} = {r.arrival_weight_lb:,.1f} lb"),
                ("1b", "Average haul time = (sum of the animals' haul times) ÷ (animals with a haul time)",
                 f"= {hv.sum():,.1f} h ÷ {len(hv)} = {hv.mean():.2f} h" if len(hv) else "No animal has a haul time; the lot record is used if given.",
                 "Numbers that differ animal to animal (weight, haul time, pay weight) are averaged. They are never treated as conflicts."),
                ("2", "Head count = animals placed in the lot, including any that died, were sold or culled (not ones moved or entered by mistake)",
                 f"= {int(r.active_head)} in the lot + {int(r.head_count - r.active_head)} no longer in it ({_gone(g)}) = {int(r.head_count)}"),
                ("", "Pen area per head = pen area ÷ head count; bunk per head = bunk length ÷ head count",
                 f"= {r.pen_area_m2:,.0f} ÷ {int(r.head_count)} = {r.pen_area_m2_per_head:.1f} m²; {r.bunk_m:,.0f} ÷ {int(r.head_count)} = {r.bunk_cm_per_head / 100:.2f} m"),
                ("", "Sex, preconditioning and vaccination are categories set for the lot",
                 "An animal recorded differently is a conflict to resolve, because a lot can't be partly preconditioned in the model.")])


def _kind(f):
    return {"sex": "sex", "preconditioning": "pc", "pre_arrival_vaccinated": "yn"}.get(f)


def _lot_value(lot_id, f):
    t = db.read("lots").set_index("lot_id")
    return D._none(t.loc[lot_id, f]) if lot_id in t.index else None


def lots_page():
    if ss.get("open_lot") and ss.open_lot in set(ss.lots_all.lot_id):
        return lot_detail(ss.open_lot)
    T.header("Lots and cattle", "Every lot in your yard. Open a lot to see and manage its cattle.", f"{D.AS_OF:%b %d, %Y}")
    L = ss.lots_all
    if L.empty:
        st.info("No lots yet. Import your yard's cattle file (or the demo files) under Add or import data, or create a lot by hand there.")
        st.button("Go to Add or import data", type="primary", on_click=lambda: ss.update(sub="add"))
        return
    A, _ = analysis()
    a = D.animal_status()
    alerts = a[a.status == "Alert"].groupby("lot_id").size()
    order = {"High risk": 0, "Not sure yet": 1, "Low risk": 2}
    L = L.assign(_o=[order.get(A.loc[l, "cls"]["chip"], 3) if len(A) and l in A.index else 3 for l in L.lot_id],
                 _s=[-A.loc[l, "cls"]["p"] if len(A) and l in A.index else 0 for l in L.lot_id]).sort_values(["_o", "_s"])
    for r in L.itertuples():
        with st.container(key=f"card_row_{r.lot_id}"):
            c1, c2 = st.columns([5, 1.1], vertical_alignment="center")
            name = f"{r.lot_id}" + (f"  {r.name}" if isinstance(r.name, str) and r.name else "")
            extra = ""
            if r.conflicts:
                extra += " " + T.chip("Conflict to resolve", "watch")
            if alerts.get(r.lot_id, 0):
                extra += " " + T.chip(f"{alerts[r.lot_id]} SenseHub alerts", "info") + " " + sensehub_chip()
            c1.html(f'<div class="lotrow"><div><p class="nm">{esc(name)}</p><p class="sub">{esc(r.pen)}, {int(r.active_head)} cattle'
                    f'{", arrives " + pd.Timestamp(r.arrival_date).strftime("%b %d") if r.status == "arriving" and isinstance(r.arrival_date, str) else ""}</p></div>'
                    f'<div style="margin-left:auto">{lot_chip(r.lot_id, A)}{extra}</div></div>')
            c2.button("Open lot", key=f"open_{r.lot_id}", on_click=lambda lid=r.lot_id: ss.update(open_lot=lid, cow_page=0), width="stretch")
            with st.expander("Herd values"):
                herd_values(r, ss.cows)


@st.dialog("Remove from lot")
def remove_dialog(animal_id):
    cow = ss.cows.set_index("animal_id").loc[animal_id]
    st.write(f"Remove **{animal_id}** from lot {cow.lot_id}? The reason is kept in the health log.")
    reason = st.radio("Why is it leaving?", list(D.REMOVAL))
    when = st.date_input("Date", D.AS_OF)
    dest = None
    if reason == "Moved to another lot":
        others = [l for l in ss.lots_all.lot_id if l != cow.lot_id]
        if not others:
            st.info("There's no other lot to move it to. Create one first.")
            return
        dest = st.selectbox("Move to", others)
    note = st.text_input("Note (optional)")
    if reason == "Entered by mistake":
        st.warning("This deletes the animal and its health history completely.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, remove", type="primary", width="stretch"):
        D.remove_cow(animal_id, reason, when, note, dest)
        st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


@st.dialog("Edit animal")
def edit_dialog(animal_id):
    cow = ss.cows.set_index("animal_id").loc[animal_id].to_dict()
    with st.form("editcow", border=False):
        v = cow_fields(cow, "ed")
        notes = st.text_input("Notes", value=cow.get("notes") or "")
        if st.form_submit_button("Save", type="primary"):
            D.update_cow(animal_id, {**v, "notes": notes})
            st.rerun()


def drug_fields(d: dict, key: str) -> dict:
    a1, a2 = st.columns(2)
    out = dict(drug=a1.text_input("Drug (active ingredient)", d.get("drug") or "", key=f"dg_{key}"),
               product=a2.text_input("Product", d.get("product") or "", key=f"dp_{key}"))
    b1, b2, b3 = st.columns([1.4, .8, 1])
    out["drug_class"] = b1.text_input("Drug class", d.get("drug_class") or "", key=f"dc_{key}")
    routes = ["", "IM", "SC", "IV", "Oral", "Topical"]
    out["route"] = b2.selectbox("Route", routes, routes.index(d.get("route")) if d.get("route") in routes else 0, key=f"dr_{key}")
    out["withdrawal_days"] = b3.number_input("Withdrawal (days)", 0.0, 200.0, float(D._none(d.get("withdrawal_days")) or 0.0), 1.0, key=f"dw_{key}")
    out["dose"] = st.text_input("Dose given", d.get("dose") or "", key=f"dd_{key}", placeholder="e.g. 18 mL")
    return out


@st.dialog("Record a treatment", width="large")
def treat_dialog(animal_id):
    cow = ss.cows.set_index("animal_id").loc[animal_id]
    lot = ss.lots_all.set_index("lot_id").loc[cow.lot_id]
    if lot.status == "arriving":
        st.info("This lot hasn't arrived yet.")
        return
    prior = int(((ss.events.animal_id == animal_id) & ss.events.type.isin(D.TREAT)).sum())
    kind = "BRD treatment" if prior == 0 else "Retreatment"
    st.html(f'<p style="margin:0">This will be <b>{"the first BRD treatment" if prior == 0 else f"BRD retreatment, treatment #{prior + 1}"}</b> for {animal_id}. '
            f'The drug below comes from your vet\'s protocol ({"1st-line" if prior == 0 else "2nd-line"}); change it if something else was given.</p>')
    c1, c2, c3 = st.columns(3)
    when = c1.date_input("Date", D.AS_OF, min_value=pd.Timestamp(lot.arrival_date).date())
    temp = c2.number_input("Rectal temperature (°C)", 37.0, 42.5, 40.3, 0.1)
    by = c3.text_input("Given by")
    d = drug_fields(D.treatment_drug(kind), f"new_{animal_id}")
    note = st.text_input("Signs and notes", placeholder="e.g. depressed, nasal discharge")
    st.caption(D.PROTOCOL_NOTE)
    if st.button("Save treatment", type="primary"):
        D.add_event(animal_id, cow.lot_id, when, kind, note, temp, drug=d, given_by=by or None)
        st.rerun()


@st.dialog("Edit health record", width="large")
def edit_event_dialog(event_id):
    e = ss.events.set_index("id").loc[event_id].to_dict()
    c1, c2, c3 = st.columns(3)
    types = D.EVENT_TYPES
    kind = c1.selectbox("Record", types, types.index(e["type"]) if e["type"] in types else 0)
    when = c2.date_input("Date", e["date"])
    temp = c3.number_input("Rectal temperature (°C, 0 = none)", 0.0, 42.5, float(D._none(e.get("temp_c")) or 0.0), 0.1)
    d = drug_fields(e, f"ev_{event_id}") if kind in D.TREAT else {}
    note = st.text_input("Notes", e.get("detail") or "")
    by = st.text_input("Given or recorded by", e.get("given_by") or "")
    b1, b2, b3 = st.columns(3)
    if b1.button("Save changes", type="primary", width="stretch"):
        D.update_event(event_id, dict(type=kind, date=when, temp_c=temp or None, detail=note or None, given_by=by or None, **d))
        st.rerun()
    if b2.button("Delete record", width="stretch"):
        D.delete_event(event_id)
        st.rerun()
    if b3.button("Cancel", width="stretch"):
        st.rerun()


def cow_fields(c: dict, key: str, lot=None):
    a1, a2 = st.columns(2)
    out = {"weight_lb": a1.number_input("Arrival weight (lb)", 150.0, 1500.0, float(D._none(c.get("weight_lb")) or 550.0), 5.0, key=f"cf_{key}_w")}
    sx = [None, "steer", "heifer", "bull"]
    out["sex"] = a2.selectbox("Sex", sx, sx.index(D._none(c.get("sex"))) if D._none(c.get("sex")) in sx else 0,
                              format_func=lambda x: "Same as the lot" if x is None else x.capitalize(), key=f"cf_{key}_s")
    b1, b2, b3 = st.columns(3)
    out["preconditioning"] = b1.selectbox("Preconditioning", PC, PC.index(D._none(c.get("preconditioning"))) if D._none(c.get("preconditioning")) in PC else 0,
                                          format_func=lambda x: "Same as the lot" if x is None else D.PRECOND[x], key=f"cf_{key}_p")
    cur = D._yn(c.get("pre_arrival_vaccinated"))
    cur = None if cur is None else bool(cur)
    out["pre_arrival_vaccinated"] = b2.selectbox("Vaccinated before arrival", list(YN), list(YN).index(cur),
                                                 format_func=lambda x: "Same as the lot" if x is None else YN[x], key=f"cf_{key}_v")
    hh = b3.number_input("Haul time (h, 0 = not recorded)", 0.0, 60.0, float(D._none(c.get("haul_hours")) or 0.0), 0.5, key=f"cf_{key}_h")
    out["haul_hours"] = hh or None
    return out


def lot_detail(lot_id):
    L = ss.lots_all.set_index("lot_id")
    r = L.loc[lot_id]
    st.button("All lots", icon=":material/arrow_back:", type="tertiary", on_click=lambda: ss.update(open_lot=None))
    when = (f", day {int(r.days_on_feed)} on feed" if r.status == "in_progress" else
            f", arrives {pd.Timestamp(r.arrival_date):%b %d}" if isinstance(r.arrival_date, str) else "")
    T.header(f"Lot {lot_id}" + (f"  {r['name']}" if isinstance(r["name"], str) and r["name"] else ""),
             f"{r.pen}, {int(r.active_head)} cattle{when}.")
    a = D.animal_status()
    a = a[a.lot_id == lot_id]
    t1, t2, t3, t4 = st.tabs(["Cattle", "Add cattle", "Lot details", "Health log"])
    with t1:
        if a.empty:
            st.info("No cattle in this lot yet. Use the Add cattle tab.")
        else:
            show_removed = st.toggle("Also show cattle that died, were sold or culled", value=False)
            v = a if show_removed else a[a.removed_reason.isna()]
            pri = {"Alert": 0, "In treatment": 1, "Retreated": 2, "Recovered": 3, "Healthy": 4}
            v = v.assign(_p=v.status.map(pri).fillna(5)).sort_values(["_p", "animal_id"])
            pages = max(1, int(np.ceil(len(v) / PAGE)))
            pg = min(ss.get("cow_page", 0), pages - 1)
            if pages > 1:
                pg = st.segmented_control("Page", list(range(pages)), default=pg, key=f"pg_{lot_id}", label_visibility="collapsed",
                                          format_func=lambda i: f"{i * PAGE + 1}-{min((i + 1) * PAGE, len(v))}") or 0
                ss.cow_page = pg
            sh = D.sensehub_status()
            ev = ss.events
            conf_ids = {i for ids in (r.conflicts or {}).values() for i in ids}
            for c in v.iloc[pg * PAGE:(pg + 1) * PAGE].itertuples():
                status = c.status + (f" ({sh['label']})" if c.status == "Alert" and sh else "")
                label = f"**{c.animal_id}** &nbsp; :{BADGE.get(c.status, 'gray')}-badge[{status}]" + (" &nbsp; :orange-badge[Conflict]" if c.animal_id in conf_ids else "")
                with st.expander(label):
                    k1, k2, k3 = st.columns(3)
                    k1.html(f'<p class="pp-note" style="margin:0">Weight</p><p style="margin:0 0 .5rem 0;font-weight:600">{_f(c.weight_lb, "lb")}</p>'
                            f'<p class="pp-note" style="margin:0">EID</p><p style="margin:0">{esc(c.eid)}</p>')
                    k2.html(f'<p class="pp-note" style="margin:0">Sex</p><p style="margin:0 0 .5rem 0">{esc(_f(D._none(c.sex) or r.sex, "sex"))}'
                            f'{"" if D._none(c.sex) else " (lot)"}</p><p class="pp-note" style="margin:0">Preconditioning, vaccinated</p>'
                            f'<p style="margin:0">{esc(_f(D._none(c.preconditioning) or _lot_value(lot_id, "preconditioning"), "pc"))}, '
                            f'{esc(_f(D._none(c.pre_arrival_vaccinated) if D._none(c.pre_arrival_vaccinated) is not None else _lot_value(lot_id, "pre_arrival_vaccinated"), "yn"))}</p>')
                    wd = c.withdrawal_until if isinstance(c.withdrawal_until, date) else None
                    k3.html(f'<p class="pp-note" style="margin:0">Haul time</p><p style="margin:0 0 .5rem 0">{esc(_f(D._none(c.haul_hours), "h"))}</p>'
                            f'<p class="pp-note" style="margin:0">Slaughter withdrawal</p><p style="margin:0">'
                            f'{("until " + wd.strftime("%b %d, %Y")) if wd and wd >= D.AS_OF else ("cleared " + wd.strftime("%b %d")) if wd else "No antibiotic recorded"}</p>')
                    h = D.treatment_history(c.animal_id)
                    if len(h):
                        st.html('<p class="pp-note" style="margin:.4rem 0 .2rem 0">Health history</p>')
                        for x in h.itertuples():
                            e1, e2 = st.columns([6, 1], vertical_alignment="center")
                            extra = []
                            if pd.notna(x.temp_c):
                                extra.append(f"{x.temp_c:.1f} °C")
                            if x.type in D.TREAT and D._none(x.withdrawal_days):
                                extra.append(f"{x.withdrawal_days:.0f}-day withdrawal")
                            if x.type in D.TREAT and D._none(x.detail):
                                extra.append(x.detail)
                            if D._none(x.given_by):
                                extra.append(f"by {x.given_by}")
                            e1.html(f'<p style="margin:0;font-size:.88rem">{x.date:%b %d} (day {x.day}): <b>{esc(x.label)}</b>'
                                    f'<span style="color:var(--muted)">{"; " + esc("; ".join(extra)) if extra else ""}</span></p>')
                            e2.button("Edit", key=f"eev_{x.id}", type="tertiary", on_click=edit_event_dialog, args=(int(x.id),))
                    if isinstance(c.notes, str) and c.notes:
                        st.caption(f"Notes: {c.notes}")
                    b1, b2, b3, _ = st.columns([1.2, .8, 1.3, 2])
                    if pd.isna(c.removed_reason):
                        b1.button("Record treatment", key=f"tx_{c.animal_id}", on_click=treat_dialog, args=(c.animal_id,))
                        b2.button("Edit", key=f"ed_{c.animal_id}", on_click=edit_dialog, args=(c.animal_id,))
                        b3.button("Remove from lot", key=f"rm_{c.animal_id}", icon=":material/close:", on_click=remove_dialog, args=(c.animal_id,))
                    else:
                        st.caption({"Died": f"Died on {c.removed_date}.", "Sold": f"Sold on {c.removed_date}."}.get(c.removed_reason, f"Culled on {c.removed_date}."))
                        b1.button("Undo", key=f"un_{c.animal_id}", on_click=D.restore_cow, args=(c.animal_id,))
    with t2:
        add_cattle(lot_id, "d")
    with t3:
        c1, c2 = st.columns([1.1, 1])
        with c1:
            with st.container(key="card_hv"):
                T.h("Herd values")
                herd_values(ss.lots_all[ss.lots_all.lot_id == lot_id].iloc[0], ss.cows)
        with c2:
            with st.container(key="card_lotset"):
                T.h("Lot settings", "Entered once for the whole lot.")
                lot_form(_lot_raw(lot_id), f"edit_{lot_id}", "Save lot settings", lot_id)
            with st.container(key="soft_dellot"):
                if st.button("Delete this lot", icon=":material/delete:"):
                    delete_lot_dialog(lot_id)
    with t4:
        ev = ss.events[ss.events.lot_id == lot_id].sort_values(["date", "id"])
        if ev.empty:
            st.info("No health records yet.")
        else:
            n = ev.groupby("animal_id").cumcount()
            tn = ev[ev.type.isin(D.TREAT)].groupby("animal_id").cumcount() + 1
            ev = ev.assign(record=[D.event_label(r, int(tn.get(i, 0)) or None) for i, r in zip(ev.index, ev.to_dict("records"))])
            ev = ev.sort_values(["date", "id"], ascending=False)
            st.dataframe(ev[["date", "day", "animal_id", "record", "drug_class", "withdrawal_days", "temp_c", "detail", "given_by", "source"]],
                         hide_index=True, width="stretch",
                         column_config={"date": "Date", "day": "Day", "animal_id": "Animal", "record": "Record", "drug_class": "Drug class",
                                        "withdrawal_days": st.column_config.NumberColumn("Withdrawal (d)", format="%.0f"),
                                        "temp_c": st.column_config.NumberColumn("Temp °C", format="%.1f"), "detail": "Notes", "given_by": "By",
                                        "source": "Source"})
            st.caption("To change a record, open the animal under Cattle and press Edit next to it.")


def _lot_raw(lot_id):
    t = db.read("lots").set_index("lot_id")
    return t.loc[lot_id].to_dict()


def lot_form(v: dict, key: str, submit: str, lot_id=None):
    with st.form(key, border=False):
        name = st.text_input("Name (optional)", value=v.get("name") or "")
        a1, a2 = st.columns(2)
        ad = D._none(v.get("arrival_date"))
        arr = a1.date_input("Arrival date", date.fromisoformat(ad) if isinstance(ad, str) else D.AS_OF)
        sx = ["steer", "heifer", "mixed"]
        sex = a2.selectbox("Sex", sx, sx.index(v.get("sex")) if v.get("sex") in sx else 0, format_func=D.SEXES.get)
        b1, b2 = st.columns(2)
        calls = [None, "high", "low"]
        call = b1.selectbox("Buyer's risk call", calls, calls.index(v.get("buyer_risk_call")) if v.get("buyer_risk_call") in calls else 0,
                            format_func=lambda x: "Not given" if x is None else x.capitalize())
        pc = b2.selectbox("Preconditioning", PC, PC.index(D._none(v.get("preconditioning"))) if D._none(v.get("preconditioning")) in PC else 0,
                          format_func=lambda x: "Not known" if x is None else D.PRECOND[x])
        c1, c2 = st.columns(2)
        cur = D._yn(v.get("pre_arrival_vaccinated"))
        vx = c1.selectbox("Vaccinated before arrival", list(YN), list(YN).index(None if cur is None else bool(cur)), format_func=YN.get)
        haul = c2.number_input("Haul time for the load (h, 0 = not known)", 0.0, 60.0, float(D._none(v.get("haul_hours")) or 0.0), 0.5,
                               help="Used only when no animal in the lot has its own haul time; otherwise PenPoint averages the animals.")
        d1, d2 = st.columns(2)
        ch = [None] + list(D.CHANNEL)
        chan = d1.selectbox("Bought through", ch, ch.index(v.get("market_channel")) if v.get("market_channel") in ch else 0,
                            format_func=lambda x: "Not known" if x is None else D.CHANNEL[x])
        sts = [None] + D.STATES
        org = d2.selectbox("Origin state", sts, sts.index(D._none(v.get("origin_state"))) if D._none(v.get("origin_state")) in sts else 0,
                           format_func=lambda x: "Not known" if x is None else x)
        e1, e2 = st.columns(2)
        pen = e1.number_input("Pen area (m², 0 = yard default)", 0.0, 50000.0, float(D._none(v.get("pen_area_m2")) or 0.0), 10.0)
        bunk = e2.number_input("Bunk length (m, 0 = yard default)", 0.0, 2000.0, float(D._none(v.get("bunk_m")) or 0.0), 1.0)
        meta = None
        if lot_id is not None:
            meta = st.toggle("Whole lot got metaphylaxis on arrival", value=bool(D._yn(v.get("metaphylaxis_given"))))
        if st.form_submit_button(submit, type="primary"):
            vals = dict(name=name or None, arrival_date=arr.isoformat(), sex=sex, buyer_risk_call=call, preconditioning=pc,
                        pre_arrival_vaccinated=vx, haul_hours=haul or None, market_channel=chan, origin_state=org,
                        pen_area_m2=pen or None, bunk_m=bunk or None)
            if lot_id is None:
                lid = D.create_lot(vals)
                ss.add_lot_sel = lid
                ss.add_msg = f"Created lot {lid}. Add its cattle below."
            else:
                vals["metaphylaxis_given"] = meta
                D.update_lot(lot_id, vals)
            ss.pop("prefill", None)
            st.rerun()


@st.dialog("Delete lot")
def delete_lot_dialog(lot_id):
    n = int((ss.cows.lot_id == lot_id).sum())
    st.write(f"Delete lot **{lot_id}** and its {n} animals? This can't be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, delete", type="primary", width="stretch"):
        D.delete_lot(lot_id)
        ss.open_lot = None
        st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


TEMPLATE = pd.DataFrame([dict(tag="A5001", weight_lb=545, sex="", preconditioning="", pre_arrival_vaccinated="", haul_hours=""),
                         dict(tag="A5002", weight_lb=560, sex="", preconditioning="", pre_arrival_vaccinated="", haul_hours="")])


def add_cattle(lot_id, key):
    t1, t2, t3 = st.tabs(["One animal", "A group", "From a file"])
    lot = ss.lots_all.set_index("lot_id").loc[lot_id]
    w0 = float(lot.arrival_weight_lb) if pd.notna(lot.arrival_weight_lb) else 550.0
    with t1:
        with st.form(f"one_{key}", clear_on_submit=True, border=False):
            tag = st.text_input("Visual tag", value=D.next_tags(1)[0])
            st.caption("Weight and haul time are this animal's own; the lot uses their average. Sex, preconditioning and vaccination come from the lot, "
                       "so only fill them in if this animal differs (a difference is flagged as a conflict).")
            v = cow_fields({"weight_lb": w0}, f"o{key}")
            notes = st.text_input("Notes", key=f"on{key}")
            if st.form_submit_button("Add animal", type="primary"):
                n, bad = D.add_cows(lot_id, [{**v, "animal_id": tag, "notes": notes}])
                if bad:
                    st.error(f"Tag {bad[0]} is blank or already used. Each animal needs its own tag.")
                else:
                    st.rerun()
    with t2:
        n = st.number_input("How many cattle", 1, 500, 5, key=f"gn{key}")
        w = st.number_input("Typical weight (lb)", 150.0, 1500.0, w0, 5.0, key=f"gw{key}")
        grid = pd.DataFrame({"tag": D.next_tags(int(n)), "weight_lb": [w] * int(n)})
        st.caption("Change any tag or weight in the table. Everything else comes from the lot.")
        ed = st.data_editor(grid, hide_index=True, width="stretch", key=f"ged{key}_{n}",
                            column_config={"tag": "Visual tag", "weight_lb": st.column_config.NumberColumn("Weight (lb)", min_value=150, max_value=1500)})
        if st.button(f"Add {int(n)} cattle", type="primary", key=f"gadd{key}"):
            k, bad = D.add_cows(lot_id, [{"animal_id": x.tag, "weight_lb": float(x.weight_lb)} for x in ed.itertuples()])
            if bad:
                st.warning(f"Added {k}. Skipped {len(bad)} with blank or duplicate tags: {', '.join(bad[:6])}.")
            else:
                st.rerun()
    with t3:
        st.caption("A CSV with one row per animal. Tag and weight are required. Other columns are optional and are checked against the lot.")
        st.download_button("Download the template", TEMPLATE.to_csv(index=False), "penpoint_cattle_template.csv", "text/csv", key=f"tpl{key}")
        f = st.file_uploader("Cattle CSV", type=["csv"], key=f"cf{key}", label_visibility="collapsed")
        if f is not None:
            df = pd.read_csv(f)
            low = {c.lower().strip(): c for c in df.columns}
            pick = lambda *ks: next((low[k] for k in ks if k in low), None)
            m = dict(animal_id=pick("tag", "animal id", "animal_id", "id"), weight_lb=pick("weight_lb", "weight"), sex=pick("sex"),
                     preconditioning=pick("preconditioning"), pre_arrival_vaccinated=pick("pre_arrival_vaccinated", "vaccinated"),
                     haul_hours=pick("haul_hours", "haul"))
            st.dataframe(df.head(6), hide_index=True, width="stretch")
            if not m["animal_id"] or not m["weight_lb"]:
                st.error("The file needs a tag column and a weight column.")
            elif st.button(f"Add {len(df)} cattle from the file", type="primary", key=f"cfi{key}"):
                rows = [{k: (x[c] if c and pd.notna(x[c]) and str(x[c]).strip() != "" else None) for k, c in m.items()} for _, x in df.iterrows()]
                for r in rows:
                    if r.get("sex"):
                        r["sex"] = str(r["sex"]).lower()
                k, bad = D.add_cows(lot_id, rows)
                db.write(lambda c: db.insert_rows(c, "uploads", [dict(file=f.name, kind="Cattle records", rows=len(df), matched=k, uploaded_at=db.now())]))
                st.success(f"Added {k} cattle." + (f" Skipped {len(bad)} with blank or duplicate tags." if bad else ""))


SAMPLE_CVI = """CERTIFICATE OF VETERINARY INSPECTION (sample, fictional)
Consignor: Bluestem Cattle Co., Okmulgee, Origin state: OK
Consignee: Panhandle receiving yard, Hereford, TX
Number of head: 92   Class: steers   Average weight 548 lb
Commingled from 4 sources at Okmulgee sale.
Vaccination history: Pyramid 5 + Presponse (BRSV, IBR, BVD, PI3) given at branding.
Preconditioning: none recorded. Loaded 6:10 AM, estimated haul 9.5 hours.
"""


def read_certificate():
    f = st.file_uploader("Health certificate or other document (PDF or text)", type=["pdf", "txt"], key="cert")
    c1, c2 = st.columns(2)
    found = None
    if c1.button("Read it", disabled=f is None, width="stretch"):
        raw = f.getvalue()
        text = D.pdf_text(raw) if f.name.lower().endswith(".pdf") else raw.decode(errors="ignore")
        found = (D.extract_fields(text), f.name)
    if c2.button("Try a sample certificate", width="stretch"):
        found = (D.extract_fields(SAMPLE_CVI), "sample_cvi.txt")
    if found:
        vals = {}
        for it in found[0]:
            if it["field"] in ("origin_state", "preconditioning", "pre_arrival_vaccinated", "haul_hours"):
                vals[it["field"]] = it["value"]
        if "Class: steers" in (SAMPLE_CVI if found[1] == "sample_cvi.txt" else ""):
            vals["sex"] = "steer"
        ss.prefill = vals
        ss.prefill_src = found[1]
        ss.prefill_found = found[0]
    if ss.get("prefill_found"):
        st.success(f"Found in {ss.prefill_src}: " + "; ".join(f"{D.FIELD_LABEL.get(x['field'], x['field'])} {x['value']}" for x in ss.prefill_found)
                   + ". These are filled into the form below. Check them before creating the lot.")


def bulk_import():
    T.h("Import cattle records", "Upload your cattle list, with health records and today's SenseHub report if you have them. "
        "PenPoint builds each lot from its cattle.")
    u1, u2, u3 = st.columns(3)
    fc = u1.file_uploader("Cattle list (required)", type=["csv", "xlsx"], key="bk_cattle")
    fe = u2.file_uploader("Health records", type=["csv", "xlsx"], key="bk_events")
    fs = u3.file_uploader("SenseHub report", type=["csv"], key="bk_sh")
    with st.expander("File format"):
        st.markdown("**Cattle list:** one row per animal. Needs `animal_id`, `lot_id` and `arrival_weight_lb`. Also read if present: `eid`, `pen`, "
                    "`arrival_date`, `sex`, `haul_hours`, `preconditioning`, `vaccinated_before_arrival`, `buyer_risk_call`, `bought_through`, "
                    "`origin_state`, `metaphylaxis_on_arrival`, `pen_area_m2`, `bunk_m`.\n\n"
                    "**Health records:** `animal_id`, `date`, `event` (treatment, retreatment, death, temperature check, observation), and if known "
                    "`drug`, `product`, `drug_class`, `route`, `dose`, `withdrawal_days`, `rectal_temp_c`, `notes`, `given_by`.\n\n"
                    "**SenseHub report:** the daily alert export.")
    if fc is not None:
        from .. import bulk as B
        prev, probs, cols = B.prepare_cattle(B.read_table(fc))
        if prev is None:
            st.error(probs[0])
        else:
            c1, c2 = st.columns([2, 1], vertical_alignment="center")
            replace = True
            if not ss.lots_all.empty:
                replace = c1.radio("Existing records", ["Replace them", "Keep them and add these"], horizontal=True) == "Replace them"
            if c2.button(f"Import {len(prev):,} cattle in {prev.lot_id.nunique()} lots", type="primary", icon=":material/upload:", width="stretch"):
                ss.bulk_report = B.import_bundle(fc, fe, fs, replace=replace)
                ss.open_lot = None
                st.rerun()
    rep = ss.pop("bulk_report", None)
    if rep:
        if rep["ok"]:
            st.success(f"Imported {rep['lots']} lots and {rep['cattle']:,} cattle"
                       + (f", with {rep['events']} health records" if rep["events"] else "")
                       + (f" and {rep['alerts']} SenseHub alerts" if rep["alerts"] else "") + ".")
        for p_ in rep["problems"][:5]:
            st.warning(p_)


def add_page():
    T.header("Add or import data", "Import your records, or add a lot and its cattle by hand.")
    with st.container(key="card_bulk"):
        bulk_import()
    c1, c2 = st.columns([1, 1.25])
    with c1:
        with st.container(key="card_newlot"):
            T.h("New lot by hand", "Fill it in, or read a health certificate first to fill it for you.")
            with st.expander("Read a health certificate", icon=":material/description:"):
                read_certificate()
            lot_form(ss.get("prefill", {}), "newlot", "Create lot")
    with c2:
        with st.container(key="card_addcattle"):
            T.h("Add cattle to a lot")
            if ss.get("add_msg"):
                st.success(ss.pop("add_msg"))
            L = ss.lots_all
            if L.empty:
                st.html('<p class="pp-note">Create a lot first.</p>')
            else:
                ids = L.lot_id.tolist()
                default = ids.index(ss.add_lot_sel) if ss.get("add_lot_sel") in ids else len(ids) - 1
                meta = L.set_index("lot_id")
                lid = st.selectbox("Lot", ids, default, format_func=lambda x: f"{x}, {meta.loc[x, 'pen']}, {int(meta.loc[x, 'active_head'])} cattle")
                ss.add_lot_sel = lid
                add_cattle(lid, "p")
    with st.container(key="card_sh"):
        sensehub_upload()
    if not ss.lots_all.empty:
        if st.button("Delete all lots and cattle", icon=":material/delete:", type="tertiary"):
            confirm_dialog("clear")


@st.dialog("Are you sure?")
def confirm_dialog(what):
    st.write("Delete every lot, animal and health record? Your costs, protocol and yard settings stay. This can't be undone.")
    c1, c2 = st.columns(2)
    if c1.button("Yes, delete", type="primary", width="stretch"):
        D.clear_lots()
        ss.open_lot = None
        st.rerun()
    if c2.button("Cancel", width="stretch"):
        st.rerun()


def sensehub_upload():
    s = D.sensehub_status()
    head = "SenseHub alerts (optional, upload daily)"
    T.h(head, "If your yard uses SenseHub ear tags, save the alert report as CSV each morning and upload it here. Alerts show on cattle only after "
        "an upload. If no report comes in for a day, every alert in PenPoint is marked with the date of the last report.")
    if s:
        st.html(f'<p style="margin:0 0 .6rem 0">Last report: {sensehub_chip()}</p>')
    c1, c2 = st.columns([1.1, 1])
    with c1:
        ex = pd.read_csv(io.BytesIO(D.sample_sensehub_csv()))
        st.caption("What a SenseHub alert report looks like (one row per alert):")
        st.dataframe(ex.head(4), hide_index=True, width="stretch")
        st.download_button("Download this example", D.sample_sensehub_csv(), "sensehub_example.csv", "text/csv")
    with c2:
        f = st.file_uploader("SenseHub CSV", type=["csv"], label_visibility="collapsed", key="shfile")
        if st.button("Use the example file"):
            ss.sh_df = (pd.read_csv(io.BytesIO(D.sample_sensehub_csv())), "sensehub_example.csv")
        if f is not None:
            ss.sh_df = (pd.read_csv(f), f.name)
        if ss.get("sh_df"):
            df, name = ss.sh_df
            g = D.guess_columns(df.columns.tolist())
            cols = [None] + df.columns.tolist()
            m1, m2 = st.columns(2)
            mp = dict(animal=m1.selectbox("Animal ID or EID", cols, cols.index(g["animal"]) if g["animal"] in cols else 0),
                      date=m2.selectbox("Alert date", cols, cols.index(g["date"]) if g["date"] in cols else 0),
                      reason=m1.selectbox("Reason (optional)", cols, cols.index(g["reason"]) if g["reason"] in cols else 0),
                      index=m2.selectbox("Health index (optional)", cols, cols.index(g["index"]) if g["index"] in cols else 0))
            if st.button(f"Import {len(df)} alerts from {name}", type="primary", disabled=not (mp["animal"] and mp["date"])):
                n, bad = D.import_sensehub(df, mp, name)
                ss.sh_df = None
                ss.sh_msg = f"Imported {n} alerts." + (f" {len(bad)} rows didn't match an animal in your yard." if bad else "")
                st.rerun()
        if ss.get("sh_msg"):
            st.success(ss.pop("sh_msg"))


def constraints():
    from brd.econ import Settings
    from .. import model as Mo
    T.header("Constraints and assumptions", "Costs, risk-factor effects, treatment protocol, current practice and yard limits. Every risk call, "
             "cost and plan in PenPoint uses these; change any and every page updates. Defaults are 2026 values.")
    o = dict(ss.ops)
    d = Settings()
    y = ss.yard
    c1, c2 = st.columns([1.2, 1])
    with c1:
        with st.container(key="card_costs"):
            T.h("Cost inputs", "The variables in the net health cost benefit (Rojas et al. 2022). Change any to match your yard.")
            a1, a2 = st.columns(2)
            o["meta_cost"] = a1.number_input("TC: metaphylaxis cost ($ per head)", 1.0, 150.0, float(o.get("meta_cost", d.meta_cost)), 0.5,
                                             help="Drug and labour to treat the whole lot on arrival. 2026 default; get a current quote.")
            me = a2.number_input("ME: share of BRD cases metaphylaxis prevents", 0.05, 0.9, float(round(1 - o.get("meta_rr", d.meta_rr), 3)), 0.05,
                                 help="Rojas et al. use 0.5. A 2023 randomized trial found about 0.58.")
            o["meta_rr"] = round(1 - me, 3)
            st.html('<p class="pp-note" style="margin:.5rem 0 .3rem 0"><b style="color:var(--ink)">MC, the cost of one sick animal</b>, is built from:</p>')
            b1, b2 = st.columns(2)
            o["tx_cost"] = b1.number_input("Treating one case ($)", 0.0, 300.0, float(o.get("tx_cost", d.tx_cost)), 1.0)
            o["perf_loss"] = b2.number_input("Lost gain and sale value if it recovers ($)", 0.0, 800.0, float(o.get("perf_loss", d.perf_loss)), 5.0)
            o["cfr"] = b1.number_input("Chance a sick animal dies", 0.0, 0.5, float(o.get("cfr", d.cfr)), 0.005, format="%.3f")
            o["feeder_price_cwt"] = b2.number_input("Feeder price ($ per cwt)", 100.0, 600.0, float(o.get("feeder_price_cwt", d.feeder_price_cwt)), 1.0)
            o["feed_cost_day"] = b1.number_input("Feed and yardage ($ per head per day)", 0.0, 20.0, float(o.get("feed_cost_day", d.feed_cost_day)), 0.1)
            s = d.with_(**{k: v for k, v in o.items() if k in d.__dataclass_fields__})
            w = float(ss.lots.arrival_weight_lb.mean()) if len(ss.lots) else 550.0
            p = Mo.mc_parts(s, w)
            T.work([
                ("10a", "Cost of a death = weight × feeder price + feed and yardage until death + treatment",
                 f"= {w:,.0f} lb × ${s.price_per_lb(w):.3f}/lb + ${s.feed_cost_day:.2f} × {D.P.get('mean_death_day'):.0f} days + ${s.tx_cost:,.0f} = ${p['death']:,.0f}",
                 f"Feeder price per lb includes a light-calf premium below 700 lb. Shown for the yard's average weight, {w:,.0f} lb."),
                ("10", "MC = (1 − chance of death) × (treatment + lost gain) + chance of death × cost of a death",
                 f"= (1 − {s.cfr:.3f}) × (${s.tx_cost:,.0f} + ${s.perf_loss:,.0f}) + {s.cfr:.3f} × ${p['death']:,.0f} = ${p['mc']:,.0f}"),
                ("11b", "Break-even BRD rate = TC ÷ (MC × ME)",
                 f"= ${s.meta_cost:,.2f} ÷ (${p['mc']:,.0f} × {me:.2f}) = {s.meta_cost / (p['mc'] * me):.1%}",
                 "Metaphylaxis pays for a lot whose expected BRD rate is above this.")], label="Show the work for MC", expanded=True)
    with c2:
        with st.container(key="card_limits"):
            T.h("Current approach", "What the yard does now. Every option is compared against this.")
            yv = {"hospital_pen_head": y["hospital_pen_head"]}
            pol = {"Metaphylaxis when the buyer calls a lot high-risk": "buyer_high", "Metaphylaxis on every sale-barn lot": "all_sale_barn",
                   "No metaphylaxis (pull-and-treat only)": "none"}
            cur = [k for k, v in pol.items() if v == o.get("policy", "buyer_high")][0]
            o["policy"] = pol[st.selectbox("The yard currently gives", list(pol), index=list(pol).index(cur))]
        with st.container(key="card_yardset"):
            T.h("Yard and date")
            yv["name"] = st.text_input("Yard name", y["name"])
            yv["region"] = st.text_input("Location", y["region"])
            g1, g2 = st.columns(2)
            yv["lat"] = g1.number_input("Latitude (for weather)", -90.0, 90.0, float(y["lat"]), 0.01, format="%.2f")
            yv["lon"] = g2.number_input("Longitude", -180.0, 180.0, float(y["lon"]), 0.01, format="%.2f")
            asof = st.date_input("Today's date in PenPoint", D.AS_OF, help="Days on feed count from this date. Importing files sets it to the latest record.")
    f1, f2 = st.columns([1, 1.2])
    with f1:
        with st.container(key="card_factors"):
            T.h("Risk factors", "How much each detail changes a lot's risk. Below 1 lowers risk, above 1 raises it.")
            from ..model import FACTORS
            for f_ in FACTORS:
                e = D.P.entry(f_["param"])
                lab = f_["name"] + (" (log-odds)" if f_["kind"] == "logodds" else " (odds ratio)")
                o[f_["param"]] = st.number_input(lab, 0.0 if f_["kind"] == "logodds" else 0.1, 3.0, float(o.get(f_["param"], e["value"])), 0.01,
                                                 key=f"fx_{f_['param']}", help=f"Ledger: {e['value']} ({e['tag']}). {e.get('location', '')}")
            st.caption("Preconditioning (0.54) is from Mijar et al. 2023; the others are estimates. See About the model, Parameter sources.")
            o["mortality_cap_margin"] = st.number_input("Safety margin on deaths (the plan must expect at least this much fewer deaths than now)", 0.0, 0.5,
                                                        float(o.get("mortality_cap_margin", D.P.get("mortality_cap_margin"))), 0.01)
    with f2:
        with st.container(key="card_protocol"):
            T.h("Treatment protocol", "Set by your veterinarian. Used as the default drug when a treatment is recorded.")
            pr = dict(ss.protocol)
            for role in ("metaphylaxis", "first", "retreat"):
                with st.expander(f"{D.PROTOCOL_ROLE[role]}: {pr[role]['drug']} ({pr[role]['product']})"):
                    with st.form(f"proto_{role}", border=False):
                        from_ = drug_fields(pr[role], f"pr_{role}")
                        if st.form_submit_button("Save", type="primary"):
                            pr[role] = {**pr[role], **from_}
                            D.save_protocol(pr)
                            st.rerun()
            st.caption(D.PROTOCOL_NOTE)
    with st.container(key="feature_rule"):
        st.html(f'<p class="pp-h" style="color:#fff">A rule PenPoint never breaks</p><p style="margin:.2rem 0 0 0;color:#DCE8E0;max-width:90ch">'
                f'The plan may not expect more BRD deaths than your current practice; it aims at least {o.get("mortality_cap_margin", D.P.get("mortality_cap_margin")):.0%} below. '
                f'If skipping metaphylaxis would cost cattle, PenPoint keeps it even when it costs more.</p>')
    if o != ss.ops:
        D.save_ops(o)
    if any(float(yv[k]) != float(y[k]) for k in ("hospital_pen_head", "lat", "lon")) or yv["name"] != y["name"] or yv["region"] != y["region"]:
        D.update_yard(yv)
    if asof != D.AS_OF:
        D.set_as_of(asof)
        st.rerun()
