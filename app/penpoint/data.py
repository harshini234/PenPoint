from __future__ import annotations

import io
import json
import re
import sys
import urllib.parse
import urllib.request
import zlib
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import streamlit as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from brd import generator as G
from brd import params as P
from brd.econ import Settings

from . import db

DEMO = ROOT / "data" / "demo"
AS_OF = date.today()
YARD = "A"
VET_NOTE = "Medication decisions stay with your veterinarian. PenPoint is decision support only."
CHANNEL = {"sale_barn": "Sale barn", "backgrounder": "Backgrounder", "ranch_direct": "Ranch direct", "mexico_import": "Mexico import"}
PRECOND = {"VAC45": "VAC-45", "VAC34": "VAC-34", "VAC24": "VAC-24", "none": "None"}
SEXES = {"steer": "Steers", "heifer": "Heifers", "mixed": "Mixed"}
STATES = ("AL AR AZ CA CO FL GA IA ID IL IN KS KY LA MO MS MT NC ND NE NM NV OK OR SC SD TN TX UT VA WA WI WV WY MX").split()
REMOVAL = {"Died": "Death", "Sold": "Sold", "Culled or railed": "Culled", "Moved to another lot": "Moved", "Entered by mistake": None}
FIELD_LABEL = {"sex": "Sex", "preconditioning": "Preconditioning", "pre_arrival_vaccinated": "Vaccinated before arrival",
               "haul_hours": "Haul time", "origin_state": "Origin state", "pay_weight_lb": "Pay weight", "head_count": "Head count",
               "n_sources": "Sellers", "market_channel": "Bought through", "seller": "Seller", "weight_lb": "Arrival weight"}
CONFLICT_FIELDS = ["sex", "preconditioning", "pre_arrival_vaccinated"]
AVERAGED = ["weight_lb", "haul_hours", "pay_weight_lb"]
COW_COLS = ["animal_id", "eid", "lot_id", "sex", "weight_lb", "pay_weight_lb", "arrival_date", "origin_state", "seller",
            "market_channel", "haul_hours", "preconditioning", "pre_arrival_vaccinated", "notes", "removed_reason", "removed_date"]
EVENT_COLS = ["animal_id", "lot_id", "day", "date", "type", "detail", "temp_c", "source", "drug", "product", "drug_class", "dose", "route",
              "withdrawal_days", "given_by"]
TREAT = ("BRD treatment", "Retreatment")


def _seed(*parts) -> int:
    return zlib.crc32("|".join(map(str, parts)).encode())


def _eid(rng):
    e = str(rng.integers(10**11, 10**12 - 1))
    return f"840 {e[:4]} {e[4:8]} {e[8:]}"


def _none(v):
    if v is None:
        return None
    try:
        return None if pd.isna(v) else v
    except (TypeError, ValueError):
        return v


def _yn(v):
    v = _none(v)
    if v is None:
        return None
    if isinstance(v, str):
        return {"true": 1, "false": 0, "yes": 1, "no": 0, "1": 1, "0": 0}.get(v.strip().lower())
    return int(bool(v))


PROTOCOL_DEFAULT = {
    "metaphylaxis": dict(drug="tildipirosin", product="Zuprevo 18%", drug_class="Macrolide antibiotic", route="SC", withdrawal_days=21.0,
                         dose="Per label, by body weight"),
    "first": dict(drug="florfenicol", product="Nuflor", drug_class="Phenicol antibiotic", route="IM", withdrawal_days=28.0,
                  dose="Per label, by body weight"),
    "retreat": dict(drug="enrofloxacin", product="Baytril 100", drug_class="Fluoroquinolone antibiotic", route="SC", withdrawal_days=28.0,
                    dose="Per label, by body weight"),
}
PROTOCOL_ROLE = {"metaphylaxis": "Metaphylaxis on arrival (whole lot)", "first": "First BRD treatment (1st-line antibiotic)",
                 "retreat": "BRD retreatment (2nd-line antibiotic)"}
PROTOCOL_NOTE = ("Example protocol for the demo. Your veterinarian sets the drugs, doses and withdrawal times; check every product label. "
                 "Fluoroquinolones may not be used extra-label in cattle.")
EVENT_TYPES = ["BRD treatment", "Retreatment", "Temperature check", "SenseHub alert", "Observation", "Death"]


def protocol() -> dict:
    p = db.get_meta("protocol") or {}
    return {k: {**v, **(p.get(k) or {})} for k, v in PROTOCOL_DEFAULT.items()}


def save_protocol(p):
    db.write(lambda c: db.set_meta("protocol", p, c))


def ensure_db():
    if db.get_meta("initialized") is None:
        def go(conn):
            for name in ("cows", "events", "feed", "lots", "documents", "uploads", "weather", "yard"):
                db.delete_rows(conn, name)
            y = P.load_yards()["yards"][YARD]
            db.insert_rows(conn, "yard", [dict(yard_id=YARD, name="Panhandle receiving yard", region=y["region"], lat=y["lat"], lon=y["lon"],
                                               riders=y["riders"], rider_hours_per_day=y["rider_hours_per_day"],
                                               spare_rider_hours_per_day=y["spare_rider_hours_per_day"], hospital_pen_head=y["hospital_pen_head"],
                                               chute_hours_per_day=y["chute_hours_per_day"], pen_area_m2_per_head=y["pen_area_m2_per_head"],
                                               bunk_cm_per_head=y["bunk_cm_per_head"])])
            db.set_meta("as_of", date.today().isoformat(), conn)
            db.set_meta("initialized", db.now(), conn)
        db.write(go)


def lot_conflicts(lot, g) -> dict:
    out = {}
    for f in CONFLICT_FIELDS:
        lv = _none(lot.get(f))
        if lv is None or f not in g:
            continue
        col = g[f].map(_none)
        if f == "pre_arrival_vaccinated":
            col, lv = col.map(_yn), _yn(lv)
        if f == "sex" and lv == "mixed":
            continue
        bad = g[col.notna() & (col != lv)]
        if len(bad):
            out[f] = bad["animal_id"].tolist()
    return out


def _mean(col):
    v = pd.to_numeric(col, errors="coerce").dropna()
    return (float(v.mean()), int(len(v))) if len(v) else (np.nan, 0)


def derive_lots(lots_t, cows, yard, swing, as_of) -> pd.DataFrame:
    rows = []
    for lt in lots_t.to_dict("records"):
        g = cows[cows.lot_id == lt["lot_id"]]
        g_act = g[g.removed_reason.isna()] if len(g) else g
        conf = lot_conflicts(lt, g_act)
        w, nw = _mean(g.weight_lb) if len(g) else (np.nan, 0)
        hh, nh = _mean(g.haul_hours) if len(g) else (np.nan, 0)
        pw, npw = _mean(g.pay_weight_lb) if len(g) else (np.nan, 0)
        lot_haul = _none(lt.get("haul_hours"))
        rec = {**lt, "yard_id": YARD, "head_count": len(g), "active_head": len(g_act), "conflicts": conf,
               "metaphylaxis_given": None if _none(lt.get("metaphylaxis_given")) is None else bool(lt["metaphylaxis_given"]),
               "pre_arrival_vaccinated": None if _yn(lt.get("pre_arrival_vaccinated")) is None else bool(_yn(lt["pre_arrival_vaccinated"])),
               "temp_range_wk1_f": swing, "arrival_weight_lb": w, "n_weight": nw, "weight_sum": float(g.weight_lb.sum()) if len(g) else 0.0,
               "haul_hours": hh if nh else (float(lot_haul) if lot_haul is not None else np.nan), "n_haul": nh,
               "haul_source": "animals" if nh else ("lot record" if lot_haul is not None else None),
               "pay_weight_lb": pw, "n_pay": npw}
        for f in conf:
            rec[f] = None
        arr = pd.Timestamp(lt["arrival_date"]) if _none(lt.get("arrival_date")) else None
        if arr is not None:
            dof = (pd.Timestamp(as_of) - arr).days
            rec.update(status="arriving" if dof < 0 else "in_progress", days_on_feed=dof if dof >= 0 else -1,
                       arrival_quarter=(arr.month - 1) // 3 + 1)
        else:
            rec.update(status="arriving", days_on_feed=-1, arrival_quarter=np.nan)
        hc = max(len(g), 1)
        rec["pen_area_m2"] = _none(lt.get("pen_area_m2")) or yard["pen_area_m2_per_head"] * hc
        rec["bunk_m"] = _none(lt.get("bunk_m")) or yard["bunk_cm_per_head"] * hc / 100
        rec["pen_area_m2_per_head"] = rec["pen_area_m2"] / hc
        rec["bunk_cm_per_head"] = rec["bunk_m"] * 100 / hc
        rows.append(rec)
    out = pd.DataFrame(rows)
    if out.empty:
        out = pd.DataFrame(columns=["lot_id", "pen", "name", "head_count", "active_head", "status", "days_on_feed", "conflicts", "arrival_date",
                                    "arrival_weight_lb", "haul_hours", "sex", "preconditioning", "pre_arrival_vaccinated", "buyer_risk_call",
                                    "market_channel", "metaphylaxis_given", "pen_area_m2", "bunk_m"])
    return out


def yard_swing(w, as_of):
    if w is None or w.empty:
        return np.nan
    w = w.copy()
    w["date"] = pd.to_datetime(w["date"]).dt.date
    nxt = w[w["date"] >= as_of].head(7)
    nxt = nxt if len(nxt) >= 3 else w.tail(7)
    return float((nxt.tmax - nxt.tmin).mean())


@st.cache_data
def load_history():
    return pd.read_csv(DEMO / "lots_history.csv")


def sync(force=False):
    global AS_OF
    ensure_db()
    ss = st.session_state
    v = db.version()
    if not force and ss.get("_db_v") == v and "lots" in ss:
        AS_OF = ss._as_of
        return
    AS_OF = date.fromisoformat(db.get_meta("as_of", date.today().isoformat()))
    yard = db.read("yard").iloc[0].to_dict()
    w = db.read("weather")
    if len(w):
        w["date"] = pd.to_datetime(w["date"]).dt.date
    cows = db.read("cows")
    for c in ("weight_lb", "pay_weight_lb", "haul_hours", "pre_arrival_vaccinated"):
        cows[c] = pd.to_numeric(cows[c], errors="coerce")
    events = db.read("events")
    events["day"] = pd.to_numeric(events["day"], errors="coerce").fillna(0).astype(int)
    events["date"] = pd.to_datetime(events["date"]).dt.date
    events["withdrawal_days"] = pd.to_numeric(events["withdrawal_days"], errors="coerce")
    swing = yard_swing(w, AS_OF)
    lots_all = derive_lots(db.read("lots"), cows, yard, swing, AS_OF)
    sh = events[events.type == "SenseHub alert"]
    ss.update(_db_v=v, _as_of=AS_OF, history=load_history(), lots_all=lots_all,
              lots=lots_all[lots_all.head_count > 0].reset_index(drop=True), cows=cows, events=events, yard=yard,
              ops=db.get_meta("ops", {}) or {}, weather=(w, db.get_meta("weather_source")) if len(w) else (None, None), swing=swing,
              docs=db.read("documents").to_dict("records"), uploads=db.read("uploads").to_dict("records"),
              sensehub_last=max(sh.date) if len(sh) else None, sensehub_uploaded=db.get_meta("sensehub_uploaded"),
              protocol=protocol(), data_source=db.get_meta("data_source"))


def sensehub_status():
    ss = st.session_state
    last = ss.get("sensehub_last")
    if last is None:
        return None
    stale = last < AS_OF
    return dict(last=last, stale=stale, label=f"alerts from {last:%m/%d/%y}")


def save_ops(ops):
    db.write(lambda c: db.set_meta("ops", ops, c))


def set_as_of(d):
    db.write(lambda c: db.set_meta("as_of", d.isoformat(), c))


def update_yard(values):
    db.write(lambda c: db.update_rows(c, "yard", "yard_id", YARD, values))


def clear_lots():
    def go(c):
        for name in ("cows", "events", "feed", "lots", "documents", "uploads"):
            db.delete_rows(c, name)
        db.set_meta("data_source", None, c)
    db.write(go)


def new_lot_id():
    L = st.session_state.lots_all
    nums = L["lot_id"].astype(str).str.extract(r"(\d+)")[0].dropna().astype(int) if len(L) else pd.Series(dtype=int)
    return f"L{(nums.max() + 1) if len(nums) else 1:04d}"


def create_lot(values: dict) -> str:
    L = st.session_state.lots_all
    lid = new_lot_id()
    pens = L["pen"].astype(str).str.extract(r"(\d+)")[0].dropna().astype(int) if len(L) else pd.Series(dtype=int)
    rec = dict(lot_id=lid, pen=f"Pen {(pens.max() + 1) if len(pens) else 1:02d}", created_at=db.now(), notes="", **values)
    rec["pre_arrival_vaccinated"] = _yn(rec.get("pre_arrival_vaccinated"))
    db.write(lambda c: db.insert_rows(c, "lots", [rec]))
    return lid


def update_lot(lot_id, values: dict):
    if "pre_arrival_vaccinated" in values:
        values["pre_arrival_vaccinated"] = _yn(values["pre_arrival_vaccinated"])
    if "metaphylaxis_given" in values:
        values["metaphylaxis_given"] = _yn(values["metaphylaxis_given"])
    db.write(lambda c: db.update_rows(c, "lots", "lot_id", lot_id, values))


def delete_lot(lot_id):
    def go(c):
        for name in ("events", "cows", "feed", "documents"):
            db.delete_rows(c, name, "lot_id", lot_id)
        db.delete_rows(c, "lots", "lot_id", lot_id)
    db.write(go)


def next_tags(n, prefix=YARD):
    cows = st.session_state.cows
    used = set(cows.animal_id.astype(str).str.upper())
    nums = pd.to_numeric(cows.animal_id.astype(str).str.extract(rf"^{re.escape(prefix)}(\d+)$")[0], errors="coerce").dropna()
    k = int(nums.max()) + 1 if len(nums) else 1001
    out = []
    while len(out) < n:
        if f"{prefix}{k}".upper() not in used:
            out.append(f"{prefix}{k}")
        k += 1
    return out


def add_cows(lot_id, rows):
    used = set(st.session_state.cows.animal_id.astype(str).str.upper())
    lot = st.session_state.lots_all.set_index("lot_id").loc[lot_id]
    ok, bad = [], []
    for r in rows:
        tag = str(r.get("animal_id") or "").strip().upper()
        if not tag or tag in used:
            bad.append(tag or "(blank)")
            continue
        used.add(tag)
        rng = np.random.default_rng(_seed("eid", tag))
        rec = {**{c: None for c in COW_COLS}, **{k: _none(v) for k, v in r.items()}}
        rec.update(animal_id=tag, lot_id=lot_id, eid=_none(r.get("eid")) or _eid(rng), notes=r.get("notes") or "",
                   arrival_date=_none(r.get("arrival_date")) or (lot.arrival_date if isinstance(lot.arrival_date, str) else AS_OF.isoformat()),
                   pre_arrival_vaccinated=_yn(r.get("pre_arrival_vaccinated")))
        ok.append(rec)
    if ok:
        db.write(lambda c: db.insert_rows(c, "cows", ok))
    return len(ok), bad


def update_cow(animal_id, values):
    if "pre_arrival_vaccinated" in values:
        values["pre_arrival_vaccinated"] = _yn(values["pre_arrival_vaccinated"])
    db.write(lambda c: db.update_rows(c, "cows", "animal_id", animal_id, {k: _none(v) for k, v in values.items()}))


def remove_cow(animal_id, reason, when, note="", dest_lot=None):
    cow = st.session_state.cows.set_index("animal_id").loc[animal_id]
    lots = st.session_state.lots_all.set_index("lot_id")
    arr = lots.loc[cow.lot_id, "arrival_date"] if cow.lot_id in lots.index else None
    day = (pd.Timestamp(when) - pd.Timestamp(arr)).days if isinstance(arr, str) else 0

    def go(c):
        if reason == "Entered by mistake":
            db.delete_rows(c, "events", "animal_id", animal_id)
            db.delete_rows(c, "cows", "animal_id", animal_id)
            return
        detail = note or reason
        if reason == "Moved to another lot":
            detail = f"Moved from {cow.lot_id} to {dest_lot}" + (f": {note}" if note else "")
            db.update_rows(c, "cows", "animal_id", animal_id, {"lot_id": dest_lot})
            db.update_rows(c, "events", "animal_id", animal_id, {"lot_id": dest_lot})
        else:
            db.update_rows(c, "cows", "animal_id", animal_id, {"removed_reason": reason, "removed_date": when.isoformat()})
        db.insert_rows(c, "events", [dict(animal_id=animal_id, lot_id=dest_lot or cow.lot_id, date=when.isoformat(), day=int(max(day, 0)),
                                          type=REMOVAL[reason], detail=detail, temp_c=None, source="Entered by user")])
    db.write(go)


def restore_cow(animal_id):
    from sqlalchemy import delete as _del

    def go(c):
        db.update_rows(c, "cows", "animal_id", animal_id, {"removed_reason": None, "removed_date": None})
        t = db.TABLES["events"]
        c.execute(_del(t).where((t.c.animal_id == animal_id) & t.c.type.in_(["Death", "Sold", "Culled"])))
    db.write(go)


def treatment_drug(kind):
    p = st.session_state.get("protocol") or protocol()
    role = {"BRD treatment": "first", "Retreatment": "retreat"}.get(kind)
    return p[role] if role else {}


def add_event(animal_id, lot_id, when: date, kind, detail="", temp_c=None, source="Entered by user", drug: dict | None = None, given_by=None):
    lot = st.session_state.lots_all.set_index("lot_id").loc[lot_id]
    day = (pd.Timestamp(when) - pd.Timestamp(lot["arrival_date"])).days
    d = drug if drug is not None else treatment_drug(kind)
    rec = dict(animal_id=animal_id, lot_id=lot_id, day=int(day), date=when.isoformat(), type=kind, detail=detail, temp_c=_none(temp_c),
               source=source, given_by=given_by, **{k: d.get(k) for k in ("drug", "product", "drug_class", "dose", "route", "withdrawal_days")})
    db.write(lambda c: db.insert_rows(c, "events", [rec]))


def update_event(event_id, values):
    ev = st.session_state.events.set_index("id").loc[event_id]
    if "date" in values:
        arr = st.session_state.lots_all.set_index("lot_id").loc[ev.lot_id, "arrival_date"]
        values["day"] = int((pd.Timestamp(values["date"]) - pd.Timestamp(arr)).days)
        values["date"] = pd.Timestamp(values["date"]).date().isoformat()
    db.write(lambda c: db.update_rows(c, "events", "id", int(event_id), {k: _none(v) for k, v in values.items()}))


def delete_event(event_id):
    db.write(lambda c: db.delete_rows(c, "events", "id", int(event_id)))


def event_label(r, nth=None) -> str:
    if r["type"] == "BRD treatment":
        head = "BRD treatment #1"
    elif r["type"] == "Retreatment":
        head = f"BRD retreatment (treatment #{nth})" if nth else "BRD retreatment"
    elif r["type"] == "Death":
        return "Died" + (f": {r['detail']}" if _none(r.get("detail")) else "")
    else:
        head = r["type"]
    if r["type"] in TREAT and _none(r.get("drug")):
        bits = [f"{r['drug']}" + (f" ({r['product']})" if _none(r.get("product")) else "")]
        if _none(r.get("drug_class")):
            bits.append(str(r["drug_class"]).lower())
        if _none(r.get("route")):
            bits.append(str(r["route"]))
        head += ": " + ", ".join(bits)
    elif _none(r.get("detail")):
        head += f": {r['detail']}"
    return head


def treatment_history(animal_id) -> pd.DataFrame:
    ev = st.session_state.events
    g = ev[ev.animal_id == animal_id].sort_values(["date", "id"]).copy()
    n = 0
    labels = []
    for r in g.to_dict("records"):
        if r["type"] in TREAT:
            n += 1
        labels.append(event_label(r, n))
    g["label"] = labels
    return g


def margin() -> float:
    return float((st.session_state.get("ops") or {}).get("mortality_cap_margin", P.get("mortality_cap_margin")))


def settings() -> Settings:
    base = Settings()
    return base.with_(**{k: v for k, v in st.session_state.ops.items() if k in asdict(base)})


def animal_status() -> pd.DataFrame:
    ss = st.session_state
    a = ss.cows.copy()
    ev = ss.events
    lots = ss.lots_all.set_index("lot_id") if len(ss.lots_all) else pd.DataFrame(columns=["days_on_feed"])
    tx = ev[ev.type.isin(TREAT)].groupby("animal_id").agg(n_tx=("day", "size"), last_tx=("day", "max"))
    al = ev[ev.type == "SenseHub alert"].groupby("animal_id").agg(n_alerts=("day", "size"), last_alert=("day", "max"),
                                                                  last_alert_date=("date", "max"))
    out = a.merge(tx, left_on="animal_id", right_index=True, how="left").merge(al, left_on="animal_id", right_index=True, how="left")
    out[["n_tx", "n_alerts"]] = out[["n_tx", "n_alerts"]].fillna(0).astype(int)
    out["today"] = out["lot_id"].map(lots["days_on_feed"]).fillna(-1) if len(out) else []

    def st_(r):
        if isinstance(r.removed_reason, str) and r.removed_reason:
            return {"Died": "Died", "Sold": "Sold", "Culled or railed": "Culled"}.get(r.removed_reason, r.removed_reason)
        if r.n_tx and r.today - r.last_tx <= 4:
            return "In treatment"
        if r.n_alerts and r.today - r.last_alert <= 2 and not (r.n_tx and r.last_tx >= r.last_alert):
            return "Alert"
        if r.n_tx >= 2:
            return "Retreated"
        if r.n_tx:
            return "Recovered"
        return "Healthy"
    out["status"] = out.apply(st_, axis=1) if len(out) else pd.Series(dtype=str)
    wd = ev[ev.type.isin(TREAT) & ev.withdrawal_days.notna()].copy()
    if len(wd):
        wd["until"] = [d + timedelta(days=int(k)) for d, k in zip(wd["date"], wd["withdrawal_days"])]
        out["withdrawal_until"] = out["animal_id"].map(wd.groupby("animal_id")["until"].max())
    else:
        out["withdrawal_until"] = None
    return out


def sample_sensehub_csv() -> bytes:
    ss = st.session_state
    a = animal_status()
    lots = ss.lots.set_index("lot_id") if len(ss.lots) else None
    rows = []
    if lots is not None:
        a = a[(a.status.isin(["Healthy", "Recovered"])) & a.lot_id.isin(lots.index[lots.status == "in_progress"])]
        rng = np.random.default_rng(7)
        for lid, g in a.groupby("lot_id"):
            for aid in g.sample(min(len(g), int(rng.integers(0, 4))), random_state=int(rng.integers(1e6)))["animal_id"]:
                rows.append({"Animal ID": aid, "Group": lots.loc[lid, "pen"], "Alert Date": AS_OF.strftime("%m/%d/%Y"),
                             "Alert Time": f"{int(rng.integers(4, 9)):02d}:{int(rng.integers(0, 60)):02d}",
                             "Reason": str(rng.choice(["Health", "Health", "Activity"])), "Health Index": int(rng.integers(55, 86))})
    if not rows:
        rows = [{"Animal ID": "A1001", "Group": "Pen 01", "Alert Date": AS_OF.strftime("%m/%d/%Y"), "Alert Time": "06:12",
                 "Reason": "Health", "Health Index": 68}]
    return pd.DataFrame(rows).to_csv(index=False).encode()


def guess_columns(cols):
    low = {c: c.lower() for c in cols}

    def pick(*keys):
        for k in keys:
            for c in cols:
                if k in low[c]:
                    return c
        return None
    return {"animal": pick("animal", "tag", "eid", "cow", "id"), "date": pick("date", "day", "time"),
            "reason": pick("reason", "type", "alert"), "index": pick("index", "score")}


def import_sensehub(df, mapping, fname):
    ss = st.session_state
    a = ss.cows
    by_tag = dict(zip(a["animal_id"].astype(str).str.upper(), a["animal_id"]))
    by_eid = dict(zip(a["eid"].astype(str).str.replace(" ", ""), a["animal_id"]))
    lots = ss.lots_all.set_index("lot_id")
    unmatched, rows = [], []
    for _, r in df.iterrows():
        key = str(r[mapping["animal"]]).strip().upper()
        aid = by_tag.get(key) or by_eid.get(key.replace(" ", ""))
        when = pd.to_datetime(r[mapping["date"]], errors="coerce")
        if not aid or pd.isna(when):
            unmatched.append(key)
            continue
        lid = a.loc[a.animal_id == aid, "lot_id"].iloc[0]
        day = (when.normalize() - pd.Timestamp(lots.loc[lid, "arrival_date"])).days
        detail = " ".join(str(r[mapping[k]]) for k in ("reason", "index") if mapping.get(k) and pd.notna(r[mapping[k]]))
        rows.append(dict(animal_id=aid, lot_id=lid, day=int(day), date=when.date().isoformat(), type="SenseHub alert",
                         detail=detail, temp_c=None, source=f"SenseHub upload ({fname})"))

    def go(c):
        db.insert_rows(c, "events", rows)
        db.insert_rows(c, "uploads", [dict(file=fname, kind="SenseHub alerts", rows=len(df), matched=len(rows), uploaded_at=db.now())])
        db.set_meta("sensehub_uploaded", db.now(), c)
    db.write(go)
    return len(rows), unmatched


def save_weather(w, source):
    def go(c):
        db.delete_rows(c, "weather")
        db.insert_rows(c, "weather", w.assign(date=w["date"].astype(str)))
        db.set_meta("weather_source", source, c)
        db.set_meta("weather_synced", db.now(), c)
    db.write(go)


def pdf_text(data: bytes) -> str:
    try:
        from pypdf import PdfReader
        return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(data)).pages)
    except Exception:
        return ""


def extract_fields(text: str) -> list[dict]:
    t = " ".join(text.split())
    found = []

    def add(field, value, evidence):
        found.append(dict(field=field, value=value, evidence=evidence[:110]))
    st_re = r"\b(" + "|".join(STATES) + r")\b"
    m = re.search(r"(?i:origin(?: state)?)\s*[:\-]\s*" + st_re, t) or re.search(r"(?i:shipped from|premises|origin)[^.]{0,60}?" + st_re, t)
    if m:
        add("origin_state", m.group(1), m.group(0))
    m = re.search(r"(?:number of (?:head|animals)|head count|no\.? of head|total head)\D{0,12}(\d{1,4})", t, re.I)
    if m:
        add("head_count", int(m.group(1)), m.group(0))
    m = re.search(r"(?:pay weight|net weight|average weight|avg\.? weight)\D{0,14}([\d,]{3,6})", t, re.I)
    if m:
        add("pay_weight_lb", float(m.group(1).replace(",", "")), m.group(0))
    m = re.search(r"(VAC[- ]?45|VAC[- ]?34|VAC[- ]?24|precondition\w*[^.]{0,30}|weaned\s+\d+\s+days)", t, re.I)
    if m:
        s_ = m.group(1).upper().replace(" ", "").replace("-", "")
        if re.search(r"NONE|NOT|NO(?:T)?RECORD", s_):
            val = "none"
        elif "VAC45" in s_ or "45" in s_:
            val = "VAC45"
        elif "VAC34" in s_ or "34" in s_:
            val = "VAC34"
        elif "VAC24" in s_ or "24" in s_:
            val = "VAC24"
        else:
            val = None
        if val:
            add("preconditioning", val, m.group(0))
    m = re.search(r"(?:vaccinat\w*|BRSV|IBR|BVD|PI3|Pyramid|Bovi-?Shield|Vista|Express ?5)[^.]{0,60}", t, re.I)
    if m:
        add("pre_arrival_vaccinated", True, m.group(0))
    m = re.search(r"(\d{1,2})\s+(?:sources|farms|origins|consignors|ranches)", t, re.I) or re.search(r"(?:sources?|consignors?)\s*[:\-]?\s*(\d{1,2})\b", t, re.I)
    if m and int(m.group(1)) < 40:
        add("n_sources", float(m.group(1)), m.group(0))
    m = re.search(r"(?:haul|transit|travel|loaded)[^.]{0,40}?(\d{1,2}(?:\.\d)?)\s*(?:h|hr|hrs|hours)\b", t, re.I)
    if m:
        add("haul_hours", float(m.group(1)), m.group(0))
    return found


def fetch_weather(lat, lon) -> pd.DataFrame:
    q = urllib.parse.urlencode(dict(latitude=lat, longitude=lon, daily="temperature_2m_max,temperature_2m_min,precipitation_sum,wind_speed_10m_max",
                                    temperature_unit="fahrenheit", wind_speed_unit="mph", precipitation_unit="inch",
                                    timezone="America/Chicago", past_days=7, forecast_days=16))
    with urllib.request.urlopen(f"https://api.open-meteo.com/v1/forecast?{q}", timeout=8) as r:
        d = json.loads(r.read())["daily"]
    return pd.DataFrame({"date": pd.to_datetime(d["time"]).date, "tmax": d["temperature_2m_max"], "tmin": d["temperature_2m_min"],
                         "precip": d["precipitation_sum"], "wind": d["wind_speed_10m_max"]})


def weather_flags(w: pd.DataFrame) -> pd.DataFrame:
    w = w.copy()
    w["swing"] = w["tmax"] - w["tmin"]
    w["big_swing"] = w["swing"] > P.get("weather_swing_threshold_f")
    w["cold_wind"] = (w["tmin"] < 25) & (w["wind"] > 20)
    w["cold_wet"] = (w["precip"] > 0.25) & (w["tmax"] < 45)
    w["stress"] = w[["big_swing", "cold_wind", "cold_wet"]].any(axis=1)
    return w


def normals_weather(yard_id) -> pd.DataFrame:
    rng = np.random.default_rng(_seed("wx", yard_id))
    days = [AS_OF - timedelta(days=7) + timedelta(days=k) for k in range(23)]
    tmax = 58 + 6 * np.sin(np.arange(23) / 3) + rng.normal(0, 5, 23)
    tmin = tmax - rng.normal(29, 6, 23)
    return pd.DataFrame({"date": days, "tmax": tmax.round(1), "tmin": tmin.round(1), "precip": np.clip(rng.gamma(.3, .2, 23), 0, None).round(2),
                         "wind": rng.normal(14, 5, 23).clip(3).round(1)})
