from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, linprog, milp

from . import params as P
from . import seirq
from .econ import Settings


def plan(option_tables: dict[str, pd.DataFrame], lots: pd.DataFrame, yards: pd.DataFrame, s: Settings,
         baseline: dict[str, str]) -> dict:
    recs = []
    for lid, tab in option_tables.items():
        y = lots.loc[lots["lot_id"] == lid, "yard_id"].iloc[0]
        w = float(lots.loc[lots["lot_id"] == lid, "arrival_weight_lb"].iloc[0])
        for _, r in tab.iterrows():
            if r["option"] == "A":
                continue
            recs.append({"lot_id": lid, "yard_id": y, "option": r["option"], "label": r["label"],
                         "objective": r["cost"] + s.stewardship_per_dose * r["doses"], "cost": r["cost"], "doses": r["doses"], "cases": r["cases"],
                         "deaths": r["deaths"], "sick_days": r["sick_days"], "hosp": r["hosp_peak"],
                         "rider": r["rider_h_day"], "chute": r["chute_min"], "case_cost": float(s.case_cost(w))})
    V = pd.DataFrame(recs)
    yard_ids = list(yards["yard_id"])
    nx, ny = len(V), len(yard_ids)
    over_pen = seirq.overflow_extra_cases_per_case()
    stay = 4.0
    over_cost = np.array([over_pen * 45 / stay * V.loc[V.yard_id == y, "case_cost"].mean() if (V.yard_id == y).any() else 0.0
                          for y in yard_ids])
    c = np.concatenate([V["objective"].to_numpy(), over_cost])

    A, lb, ub, names = [], [], [], []
    for lid in V["lot_id"].unique():
        row = np.zeros(nx + ny)
        row[(V["lot_id"] == lid).to_numpy().nonzero()[0]] = 1
        A.append(row); lb.append(1); ub.append(1); names.append(("pick", lid))
    yd = yards.set_index("yard_id")
    for j, y in enumerate(yard_ids):
        m = (V["yard_id"] == y).to_numpy()
        row = np.zeros(nx + ny); row[:nx] = V["rider"].to_numpy() * m
        A.append(row); lb.append(-np.inf); ub.append(float(yd.loc[y, "spare_rider_hours_per_day"])); names.append(("rider", y))
        row = np.zeros(nx + ny); row[:nx] = V["hosp"].to_numpy() * m; row[nx + j] = -1
        A.append(row); lb.append(-np.inf); ub.append(float(yd.loc[y, "hospital_pen_head"])); names.append(("hospital", y))
        row = np.zeros(nx + ny); row[:nx] = V["chute"].to_numpy() * m
        A.append(row); lb.append(-np.inf); ub.append(float(yd.loc[y, "chute_hours_per_day"]) * 60 * 5); names.append(("chute", y))
    base_sick = 0.0
    for lid, code in baseline.items():
        t = option_tables[lid]
        base_sick += float(t.loc[t.option == code, "sick_days"].iloc[0])
    row = np.zeros(nx + ny); row[:nx] = V["sick_days"].to_numpy()
    A.append(row); lb.append(-np.inf); ub.append(base_sick * (1 + s.welfare_slack)); names.append(("welfare", "all"))
    base_deaths = sum(float(option_tables[lid].loc[option_tables[lid].option == code, "deaths"].iloc[0]) for lid, code in baseline.items())
    row = np.zeros(nx + ny); row[:nx] = V["deaths"].to_numpy()
    A.append(row); lb.append(-np.inf); ub.append(base_deaths * (1 - P.get("mortality_cap_margin"))); names.append(("mortality", "all"))
    A = np.array(A)

    integrality = np.concatenate([np.ones(nx), np.zeros(ny)])
    bounds = Bounds(np.zeros(nx + ny), np.concatenate([np.ones(nx), np.full(ny, np.inf)]))
    res = milp(c, constraints=LinearConstraint(A, lb, ub), integrality=integrality, bounds=bounds,
               options={"time_limit": 20})
    if res.x is None:
        return {"status": "infeasible", "message": res.message}
    x = np.round(res.x[:nx]).astype(bool)
    chosen = V[x].copy()
    overflow = dict(zip(yard_ids, res.x[nx:]))

    A_ub, b_ub, A_eq, b_eq, ub_names = [], [], [], [], []
    for row, l, u, nm in zip(A, lb, ub, names):
        if l == u:
            A_eq.append(row); b_eq.append(u)
        else:
            A_ub.append(row); b_ub.append(u); ub_names.append(nm)
    lp = linprog(c, A_ub=np.array(A_ub), b_ub=b_ub, A_eq=np.array(A_eq), b_eq=b_eq,
                 bounds=list(zip(np.zeros(nx + ny), np.concatenate([np.ones(nx), np.full(ny, None)]))), method="highs")
    shadow = []
    if lp.status == 0:
        for nm, mu, row, u in zip(ub_names, lp.ineqlin.marginals, A_ub, b_ub):
            used = float(row[:nx] @ x.astype(float) + (row[nx:] @ res.x[nx:]))
            shadow.append({"constraint": nm[0], "yard_id": nm[1], "limit": u, "used": used,
                           "value_of_one_more_unit": float(-mu)})
    util = []
    for j, y in enumerate(yard_ids):
        m = chosen["yard_id"] == y
        util.append({"yard_id": y, "lots": int(m.sum()),
                     "rider_hours_day": float(chosen.loc[m, "rider"].sum()), "rider_cap": float(yd.loc[y, "spare_rider_hours_per_day"]),
                     "hospital_peak": float(chosen.loc[m, "hosp"].sum()), "hospital_cap": float(yd.loc[y, "hospital_pen_head"]),
                     "overflow": float(overflow[y]), "chute_min": float(chosen.loc[m, "chute"].sum()),
                     "chute_cap_min_week": float(yd.loc[y, "chute_hours_per_day"]) * 300})
    free = V.loc[V.groupby("lot_id")["objective"].idxmin()]
    base_rows = []
    for lid, code in baseline.items():
        t = option_tables[lid]
        b = t.loc[t.option == code].iloc[0].copy()
        b["yard_id"] = lots.loc[lots["lot_id"] == lid, "yard_id"].iloc[0]
        b["hosp"] = b["hosp_peak"]
        base_rows.append(b)
    base = pd.DataFrame(base_rows)
    oc = dict(zip(yard_ids, over_cost))

    def totals(d):
        out = {k: float(d[k].sum()) for k in ("cost", "doses", "cases", "deaths", "sick_days")}
        ovf = sum(max(0.0, d.loc[d["yard_id"] == y, "hosp"].sum() - float(yd.loc[y, "hospital_pen_head"])) * oc[y] for y in yard_ids)
        out["overflow_cost"] = float(ovf)
        out["total_cost"] = out["cost"] + out["overflow_cost"]
        return out

    return {"status": "optimal", "chosen": chosen, "utilisation": pd.DataFrame(util), "shadow": pd.DataFrame(shadow),
            "totals_plan": totals(chosen), "totals_unconstrained": totals(free), "totals_current": totals(base),
            "overflow_cost": float(res.x[nx:] @ over_cost)}


def frontier(option_tables, lots, yards, s: Settings, baseline, weights=(0, 25, 50, 100, 200, 400, 800)) -> pd.DataFrame:
    rows = []
    for w in weights:
        out = plan(option_tables, lots, yards, s.with_(stewardship_per_dose=float(w)), baseline)
        if out["status"] == "optimal":
            rows.append({"stewardship_per_dose": w, **out["totals_plan"]})
    return pd.DataFrame(rows)
