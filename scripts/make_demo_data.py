from __future__ import annotations

import sys
import zlib
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"
OUT = ROOT / "demo_data"
DATA_DATE = pd.Timestamp("2026-11-14")
PEN_AREA, BUNK_CM = 14.0, 30.0
FIRST = dict(drug="florfenicol", product="Nuflor", drug_class="Phenicol antibiotic", route="IM", withdrawal_days=28)
RETREAT = dict(drug="enrofloxacin", product="Baytril 100", drug_class="Fluoroquinolone antibiotic", route="SC", withdrawal_days=28)
CREW = ["J. Ortiz", "M. Reyes", "T. Banks"]


def seed(*p):
    return zlib.crc32("|".join(map(str, p)).encode())


def eid(rng):
    e = str(rng.integers(10**11, 10**12 - 1))
    return f"840{e}"


def main():
    lots = pd.read_csv(DEMO / "lots_current.csv")
    daily = pd.read_csv(DEMO / "daily_current.csv")
    lots = lots[lots.yard_id == "A"].sort_values(["arrival_date", "lot_id"]).reset_index(drop=True)
    pc_lots = lots[(lots.status == "in_progress") & lots.preconditioning.isin(["VAC45", "VAC34"])]
    conflict_lot = pc_lots.lot_id.iloc[0] if len(pc_lots) else None
    cattle, events, alerts = [], [], []
    no = 1001
    for i, lot in lots.iterrows():
        rng = np.random.default_rng(seed("animals", lot.lot_id))
        n, w = int(lot.head_count), float(lot.arrival_weight_lb)
        sexes = rng.choice(["steer", "heifer"], n, p=[0.55, 0.45]) if lot.sex == "mixed" else [lot.sex] * n
        weights = np.round(rng.normal(w, 0.07 * w, n) / 5) * 5
        haul = lot.haul_hours
        hauls = [None] * n if pd.isna(haul) else list(np.round(np.clip(haul + rng.normal(0, 0.6, n), 0.5, None) * 2) / 2)
        if not pd.isna(haul):
            for j in rng.choice(n, max(1, n // 12), replace=False):
                hauls[j] = None
        pc = None if pd.isna(lot.preconditioning) else lot.preconditioning
        vx = None if pd.isna(lot.pre_arrival_vaccinated) else ("yes" if str(lot.pre_arrival_vaccinated).lower() in ("true", "1", "yes") else "no")
        ids = [f"A{no + k}" for k in range(n)]
        for k, aid in enumerate(ids):
            cattle.append({
                "animal_id": aid, "eid": eid(rng), "lot_id": lot.lot_id, "pen": f"Pen {i + 1:02d}", "arrival_date": lot.arrival_date,
                "sex": sexes[k], "arrival_weight_lb": weights[k], "haul_hours": hauls[k],
                "preconditioning": ("none" if (lot.lot_id == conflict_lot and k in (3, 4)) else pc),
                "vaccinated_before_arrival": vx, "buyer_risk_call": lot.buyer_risk_call, "bought_through": lot.market_channel,
                "origin_state": None if pd.isna(lot.origin_state) else lot.origin_state,
                "metaphylaxis_on_arrival": ("yes" if str(lot.metaphylaxis_given).lower() in ("true", "1") else "no") if lot.status == "in_progress" else None,
                "pen_area_m2": round(PEN_AREA * n), "bunk_m": round(BUNK_CM * n / 100)})
        no += n + 9
        if lot.status != "in_progress":
            continue
        arr = pd.Timestamp(lot.arrival_date)
        er = np.random.default_rng(seed("events", lot.lot_id))
        tx, dead = {a: 0 for a in ids}, set()
        for r in daily[daily.lot_id == lot.lot_id].sort_values("day").itertuples():
            day = arr + pd.Timedelta(days=int(r.day))
            if day > DATA_DATE:
                break
            for _ in range(int(r.pulls)):
                pool = [a for a in ids if tx[a] == 0 and a not in dead]
                if not pool:
                    break
                a = pool[er.integers(len(pool))]
                tx[a] = 1
                t = round(float(er.normal(40.4, 0.35)), 1)
                events.append(dict(animal_id=a, date=day.date().isoformat(), event="BRD treatment", **FIRST, dose="Per label",
                                   rectal_temp_c=t, notes="Pulled for BRD: depressed, nasal discharge", given_by=CREW[er.integers(3)]))
                d2 = int(r.day) + int(er.integers(3, 6))
                if er.random() < 0.18 and arr + pd.Timedelta(days=d2) <= DATA_DATE:
                    tx[a] = 2
                    events.append(dict(animal_id=a, date=(arr + pd.Timedelta(days=d2)).date().isoformat(), event="Retreatment", **RETREAT,
                                       dose="Per label", rectal_temp_c=round(float(er.normal(40.2, 0.3)), 1),
                                       notes="Not improving after first treatment", given_by=CREW[er.integers(3)]))
            for _ in range(int(r.deaths)):
                pool = [a for a in ids if tx[a] > 0 and a not in dead] or [a for a in ids if a not in dead]
                if not pool:
                    break
                a = pool[er.integers(len(pool))]
                dead.add(a)
                events.append(dict(animal_id=a, date=day.date().isoformat(), event="Death", notes="Died, BRD suspected (necropsy pending)",
                                   given_by=CREW[er.integers(3)]))
        healthy = [a for a in ids if tx[a] == 0 and a not in dead]
        for a in er.choice(healthy, min(len(healthy), int(er.integers(0, 4))), replace=False):
            alerts.append({"Animal ID": a, "Group": f"Pen {i + 1:02d}", "Alert Date": DATA_DATE.strftime("%m/%d/%Y"),
                           "Alert Time": f"{int(er.integers(4, 9)):02d}:{int(er.integers(0, 60)):02d}",
                           "Reason": str(er.choice(["Health", "Health", "Activity"])), "Health Index": int(er.integers(55, 86))})
    OUT.mkdir(exist_ok=True)
    pd.DataFrame(cattle).to_csv(OUT / "cattle.csv", index=False)
    ev = pd.DataFrame(events)
    ev = ev[["animal_id", "date", "event", "drug", "product", "drug_class", "dose", "route", "withdrawal_days", "rectal_temp_c", "notes", "given_by"]]
    ev.sort_values(["date", "animal_id"]).to_csv(OUT / "health_records.csv", index=False)
    pd.DataFrame(alerts).to_csv(OUT / "sensehub_alerts.csv", index=False)
    print(f"{len(cattle)} cattle in {lots.lot_id.nunique()} lots, {len(ev)} health records, {len(alerts)} SenseHub alerts -> {OUT}")


if __name__ == "__main__":
    sys.exit(main())
