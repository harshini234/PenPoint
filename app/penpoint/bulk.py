from __future__ import annotations

import io
import re
from datetime import date

import numpy as np
import pandas as pd

from . import data as D
from . import db

CATTLE_COLS = {
    "animal_id": ["animal_id", "animal id", "tag", "visual tag", "ear tag", "animal"],
    "eid": ["eid", "rfid", "electronic id"],
    "lot_id": ["lot_id", "lot id", "lot", "lot number"],
    "pen": ["pen", "home pen", "pen name"],
    "arrival_date": ["arrival_date", "arrival date", "arrived", "date in", "in date"],
    "sex": ["sex", "gender", "class"],
    "weight_lb": ["arrival_weight_lb", "weight_lb", "arrival weight", "weight", "in weight", "arrival weight (lb)"],
    "pay_weight_lb": ["pay_weight_lb", "pay weight", "pay weight (lb)"],
    "haul_hours": ["haul_hours", "haul hours", "haul time", "haul time (h)", "transit hours"],
    "preconditioning": ["preconditioning", "precondition", "precond", "preconditioning program"],
    "pre_arrival_vaccinated": ["vaccinated_before_arrival", "pre_arrival_vaccinated", "vaccinated before arrival", "pre-arrival vaccination"],
    "buyer_risk_call": ["buyer_risk_call", "buyer risk call", "buyer call", "risk call"],
    "market_channel": ["bought_through", "market_channel", "bought through", "source", "market"],
    "origin_state": ["origin_state", "origin state", "origin", "state"],
    "seller": ["seller", "consignor"],
    "metaphylaxis_given": ["metaphylaxis_on_arrival", "metaphylaxis_given", "metaphylaxis", "metaphylaxis on arrival"],
    "pen_area_m2": ["pen_area_m2", "pen area (m2)", "pen area"],
    "bunk_m": ["bunk_m", "bunk length (m)", "bunk length"],
}
EVENT_COLS = {
    "animal_id": ["animal_id", "animal id", "tag", "animal", "eid"],
    "date": ["date", "event date", "treatment date"],
    "event": ["event", "type", "event type", "treatment"],
    "drug": ["drug", "active ingredient", "drug name"],
    "product": ["product", "brand", "product name"],
    "drug_class": ["drug_class", "drug class", "class"],
    "dose": ["dose", "dose given"],
    "route": ["route"],
    "withdrawal_days": ["withdrawal_days", "withdrawal days", "withdrawal"],
    "temp_c": ["rectal_temp_c", "temp_c", "temperature", "rectal temp", "temp"],
    "detail": ["notes", "detail", "note", "reason", "comments"],
    "given_by": ["given_by", "given by", "treated by", "crew"],
}
REQUIRED = ["animal_id", "lot_id", "weight_lb"]


def read_table(f) -> pd.DataFrame:
    name = getattr(f, "name", "file")
    raw = f.getvalue() if hasattr(f, "getvalue") else f
    if str(name).lower().endswith((".xlsx", ".xls")):
        return pd.read_excel(io.BytesIO(raw))
    return pd.read_csv(io.BytesIO(raw), dtype=str, keep_default_na=False, na_values=["", "NA", "N/A", "na", "n/a", "-"])


def match_columns(df: pd.DataFrame, spec: dict) -> dict:
    low = {re.sub(r"\s+", " ", str(c).strip().lower()): c for c in df.columns}
    out = {}
    for key, names in spec.items():
        for n in names:
            if n in low:
                out[key] = low[n]
                break
    return out


def _sex(v):
    v = D._none(v)
    if v is None:
        return None
    v = str(v).strip().lower()
    return {"s": "steer", "steer": "steer", "steers": "steer", "h": "heifer", "heifer": "heifer", "heifers": "heifer", "bull": "steer",
            "mixed": "mixed"}.get(v)


def _precond(v):
    v = D._none(v)
    if v is None:
        return None
    v = str(v).strip().upper().replace("-", "").replace(" ", "")
    if v in ("NONE", "NO", "N", "0", "FALSE"):
        return "none"
    for k in ("VAC45", "VAC34", "VAC24"):
        if k in v or v == k[3:]:
            return k
    return None


def _call(v):
    v = D._none(v)
    if v is None:
        return None
    v = str(v).strip().lower()
    return "high" if v.startswith("h") else "low" if v.startswith("l") else None


def _channel(v):
    v = D._none(v)
    if v is None:
        return None
    v = str(v).strip().lower().replace(" ", "_")
    for k in D.CHANNEL:
        if k.split("_")[0] in v:
            return k
    return None


def _num(v):
    try:
        x = float(str(v).replace(",", ""))
        return None if np.isnan(x) else x
    except (TypeError, ValueError):
        return None


def _date(v):
    v = D._none(v)
    if v is None:
        return None
    t = pd.to_datetime(v, errors="coerce")
    return None if pd.isna(t) else t.date().isoformat()


def _mode(vals):
    v = [x for x in vals if D._none(x) is not None]
    if not v:
        return None
    s = pd.Series(v).value_counts()
    x = s.index[0]
    return x.item() if hasattr(x, "item") else x


def _event_type(v):
    v = str(D._none(v) or "").lower()
    if "retreat" in v or "2nd" in v or "second" in v:
        return "Retreatment"
    if "treat" in v or "pull" in v:
        return "BRD treatment"
    if "die" in v or "dead" in v or "death" in v:
        return "Death"
    if "temp" in v:
        return "Temperature check"
    if "sensehub" in v or "alert" in v:
        return "SenseHub alert"
    return "Observation"


def prepare_cattle(df: pd.DataFrame):
    cols = match_columns(df, CATTLE_COLS)
    missing = [k for k in REQUIRED if k not in cols]
    if missing:
        return None, [f"Missing column: {', '.join(missing)}. Expected names like animal_id, lot_id, arrival_weight_lb."], cols
    rows, problems, seen = [], [], set()
    for i, r in df.iterrows():
        g = {k: r[c] for k, c in cols.items()}
        tag = str(D._none(g.get("animal_id")) or "").strip().upper()
        lot = str(D._none(g.get("lot_id")) or "").strip()
        w = _num(g.get("weight_lb"))
        if not tag or not lot or w is None:
            problems.append(f"Row {i + 2}: needs an animal ID, a lot and an arrival weight.")
            continue
        if tag in seen:
            problems.append(f"Row {i + 2}: animal {tag} appears twice; kept the first.")
            continue
        seen.add(tag)
        rows.append(dict(animal_id=tag, eid=D._none(g.get("eid")), lot_id=lot, pen=D._none(g.get("pen")), arrival_date=_date(g.get("arrival_date")),
                         sex=_sex(g.get("sex")), weight_lb=w, pay_weight_lb=_num(g.get("pay_weight_lb")), haul_hours=_num(g.get("haul_hours")),
                         preconditioning=_precond(g.get("preconditioning")), pre_arrival_vaccinated=D._yn(g.get("pre_arrival_vaccinated")),
                         buyer_risk_call=_call(g.get("buyer_risk_call")), market_channel=_channel(g.get("market_channel")),
                         origin_state=(str(D._none(g.get("origin_state"))).strip().upper()[:2] if D._none(g.get("origin_state")) else None),
                         seller=D._none(g.get("seller")), metaphylaxis_given=D._yn(g.get("metaphylaxis_given")),
                         pen_area_m2=_num(g.get("pen_area_m2")), bunk_m=_num(g.get("bunk_m"))))
    return pd.DataFrame(rows), problems, cols


def lots_from_cattle(c: pd.DataFrame, existing_pens=0) -> list[dict]:
    lots = []
    for k, (lid, g) in enumerate(c.groupby("lot_id", sort=False)):
        sexes = set(x for x in g.sex if x)
        sex = None if not sexes else (sexes.pop() if len(sexes) == 1 else "mixed")
        dates = [x for x in g.arrival_date if x]
        lots.append(dict(lot_id=lid, pen=_mode(g.pen) or f"Pen {existing_pens + k + 1:02d}", name=None,
                         arrival_date=min(dates) if dates else date.today().isoformat(), sex=sex,
                         buyer_risk_call=_mode(g.buyer_risk_call), preconditioning=_mode(g.preconditioning),
                         pre_arrival_vaccinated=_mode(g.pre_arrival_vaccinated), haul_hours=None,
                         market_channel=_mode(g.market_channel), origin_state=_mode(g.origin_state),
                         pen_area_m2=_mode(g.pen_area_m2), bunk_m=_mode(g.bunk_m), metaphylaxis_given=_mode(g.metaphylaxis_given),
                         created_at=db.now(), notes="Imported"))
    return lots


def prepare_events(df: pd.DataFrame, tags: dict, arrivals: dict):
    cols = match_columns(df, EVENT_COLS)
    if "animal_id" not in cols or "date" not in cols:
        return [], ["Health records need at least an animal ID and a date column."]
    proto = D.protocol()
    out, problems = [], []
    for i, r in df.iterrows():
        g = {k: r[c] for k, c in cols.items()}
        key = str(D._none(g.get("animal_id")) or "").strip().upper()
        aid = tags.get(key) or tags.get(key.replace(" ", ""))
        when = _date(g.get("date"))
        if not aid or not when:
            problems.append(f"Health record row {i + 2}: animal {key or '(blank)'} not found or date unreadable.")
            continue
        lid, arr = arrivals[aid]
        typ = _event_type(g.get("event"))
        rec = dict(animal_id=aid, lot_id=lid, date=when, day=int((pd.Timestamp(when) - pd.Timestamp(arr)).days), type=typ,
                   detail=D._none(g.get("detail")), temp_c=_num(g.get("temp_c")), source="Bulk upload", given_by=D._none(g.get("given_by")))
        for k in ("drug", "product", "drug_class", "dose", "route"):
            rec[k] = D._none(g.get(k))
        rec["withdrawal_days"] = _num(g.get("withdrawal_days"))
        out.append(rec)
    ev = pd.DataFrame(out)
    if len(ev):
        ev = ev.sort_values(["animal_id", "date"]).reset_index(drop=True)
        n = ev[ev.type.isin(D.TREAT)].groupby("animal_id").cumcount()
        ev.loc[n.index, "type"] = np.where(n == 0, "BRD treatment", "Retreatment")
        for role, typ in (("first", "BRD treatment"), ("retreat", "Retreatment")):
            m = (ev.type == typ) & ev.drug.isna()
            for k in ("drug", "product", "drug_class", "dose", "route", "withdrawal_days"):
                ev.loc[m, k] = proto[role][k]
    return ev, problems


def prepare_sensehub(df: pd.DataFrame, tags: dict, arrivals: dict):
    m = D.guess_columns(list(df.columns))
    out, bad = [], 0
    for _, r in df.iterrows():
        key = str(r[m["animal"]]).strip().upper() if m.get("animal") else ""
        aid = tags.get(key) or tags.get(key.replace(" ", ""))
        when = pd.to_datetime(r[m["date"]], errors="coerce") if m.get("date") else pd.NaT
        if not aid or pd.isna(when):
            bad += 1
            continue
        lid, arr = arrivals[aid]
        detail = " ".join(str(r[m[k]]) for k in ("reason", "index") if m.get(k) and pd.notna(r[m[k]]))
        out.append(dict(animal_id=aid, lot_id=lid, day=int((when.normalize() - pd.Timestamp(arr)).days), date=when.date().isoformat(),
                        type="SenseHub alert", detail=detail, temp_c=None, source="SenseHub (bulk upload)"))
    return out, bad


def import_bundle(cattle_file, events_file=None, sensehub_file=None, replace=True):
    report = dict(ok=False, problems=[], lots=0, cattle=0, events=0, alerts=0, as_of=None)
    c, probs, cols = prepare_cattle(read_table(cattle_file))
    report["problems"] += probs
    report["columns"] = cols
    if c is None or c.empty:
        return report
    old = D.st.session_state.cows if not replace else pd.DataFrame(columns=["animal_id", "lot_id"])
    if len(old):
        dup = c.animal_id.isin(set(old.animal_id.astype(str).str.upper()))
        if dup.any():
            report["problems"].append(f"{int(dup.sum())} animals already in PenPoint were skipped.")
            c = c[~dup]
    rng = np.random.default_rng(11)
    c["eid"] = [e or D._eid(rng) for e in c.eid]
    existing_lots = set() if replace else set(D.st.session_state.lots_all.lot_id)
    lots = [l for l in lots_from_cattle(c, 0 if replace else len(existing_lots)) if l["lot_id"] not in existing_lots]
    arr_by_lot = {l["lot_id"]: l["arrival_date"] for l in lots}
    if not replace:
        arr_by_lot.update(dict(zip(D.st.session_state.lots_all.lot_id, D.st.session_state.lots_all.arrival_date)))
    c["arrival_date"] = [a or arr_by_lot[l] for a, l in zip(c.arrival_date, c.lot_id)]
    cows = c[["animal_id", "eid", "lot_id", "sex", "weight_lb", "pay_weight_lb", "arrival_date", "origin_state", "seller", "market_channel",
              "haul_hours", "preconditioning", "pre_arrival_vaccinated"]].assign(notes="", removed_reason=None, removed_date=None)
    allc = pd.concat([old[["animal_id", "eid", "lot_id"]], cows[["animal_id", "eid", "lot_id"]]]) if len(old) else cows
    tags = {**dict(zip(allc.animal_id.astype(str).str.upper(), allc.animal_id)),
            **{str(e).replace(" ", ""): a for e, a in zip(allc.eid, allc.animal_id) if e}}
    arrivals = {a: (l, arr_by_lot.get(l, date.today().isoformat())) for a, l in zip(allc.animal_id, allc.lot_id)}
    ev = pd.DataFrame()
    if events_file is not None:
        ev, p2 = prepare_events(read_table(events_file), tags, arrivals)
        report["problems"] += p2
    alerts = []
    if sensehub_file is not None:
        alerts, bad = prepare_sensehub(read_table(sensehub_file), tags, arrivals)
        if bad:
            report["problems"].append(f"{bad} SenseHub rows didn't match an animal.")
    dates = ([*ev["date"]] if len(ev) else []) + [a["date"] for a in alerts]

    def go(conn):
        if replace:
            for name in ("cows", "events", "feed", "lots", "documents", "uploads"):
                db.delete_rows(conn, name)
        db.insert_rows(conn, "lots", lots)
        db.insert_rows(conn, "cows", cows)
        if len(ev):
            db.insert_rows(conn, "events", ev)
            for r in ev[ev.type == "Death"].itertuples():
                db.update_rows(conn, "cows", "animal_id", r.animal_id, {"removed_reason": "Died", "removed_date": r.date})
        db.insert_rows(conn, "events", alerts)
        for f, kind, n in ((cattle_file, "Cattle and lots", len(cows)), (events_file, "Health records", len(ev)),
                           (sensehub_file, "SenseHub alerts", len(alerts))):
            if f is not None:
                db.insert_rows(conn, "uploads", [dict(file=getattr(f, "name", "file"), kind=kind, rows=n, matched=n, uploaded_at=db.now())])
        if dates:
            db.set_meta("as_of", max(dates), conn)
        if alerts:
            db.set_meta("sensehub_uploaded", db.now(), conn)
        db.set_meta("data_source", dict(file=getattr(cattle_file, "name", "file"), at=db.now(), lots=len(lots), cattle=len(cows)), conn)
    db.write(go)
    report.update(ok=True, lots=len(lots), cattle=len(cows), events=len(ev), alerts=len(alerts), as_of=max(dates) if dates else None)
    return report
