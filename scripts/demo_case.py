from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from brd import effects as E
from brd import evaluate as V
from brd import generator as G
from brd import params as P
from brd import risk as R
from brd import simulate as S
from brd.econ import Settings

LOT, DAY = "C100007", None
D = ROOT / "data" / "demo"


def fmt_tab(tab):
    L = ["| Option | Cases (80% range) | Deaths | Doses | Expected cost | $/head vs current | Best in |", "|---|---|---|---|---|---|---|"]
    for r in tab.itertuples():
        best = "" if np.isnan(r.p_best) else f"{r.p_best:.0%}"
        L.append(f"| {r.label} | {r.cases:.1f} ({r.cases_lo:.1f}-{r.cases_hi:.1f}) | {r.deaths:.1f} | {r.doses:.0f} | "
                 f"${r.cost:,.0f} | {r.vs_current_cost_per_head:+.2f} | {best} |")
    return L


def main() -> None:
    h = pd.read_csv(D / "lots_history.csv")
    cur = pd.read_csv(D / "lots_current.csv")
    truth = pd.read_csv(D / "truth_current.csv").set_index("lot_id").loc[LOT]
    s = Settings()
    day = s.decision_day
    m = R.RiskModel(h)
    lot = cur[cur.lot_id == LOT].reset_index(drop=True)
    row = lot.iloc[0]
    summ, prior_w, post_w = m.assess(lot, None)
    a = summ.iloc[0]
    res0 = S.evaluate_lot(row, prior_w[0], s)
    draws, lp, _ = m.prior(lot)
    voi = S.value_of_information(row, draws, lp[0], s, m.sd)
    ex = R.explain(row, h)
    cl = E.table_a1_checklist(row)

    rng = np.random.default_rng(2026)
    H = int(row.head_count)
    lam, p_true = float(truth.true_logodds), float(truth.p_case_no_meta)
    pulls5 = int(rng.binomial(H, p_true * float(G.onset_cdf(day))))
    dip = float(R.feed_dip_mean(np.array([lam]))[0] + rng.normal(0, P.get("feed_signal_noise_sd")))
    lik = R.likelihood(H, pulls5, day, 1.0, dip)
    w5 = prior_w[0] * lik
    w5 /= w5.sum()
    s5 = R.summarize(w5)
    row5 = row.copy()
    row5["status"], row5["days_on_feed"], row5["metaphylaxis_given"] = "in_progress", day, False
    res5 = S.evaluate_lot(row5, w5, s)

    w_lb = float(row.arrival_weight_lb)
    late = (1 - float(G.onset_cdf(day))) * s.late_meta_fraction
    paths = {
        "Current practice (buyer said low: pull-and-treat only)": V.outcomes(H, p_true, s.meta_rr, 1.0, s.cfr, s, w_lb, False),
        "Metaphylaxis on arrival": V.outcomes(H, p_true, s.meta_rr, 1.0, s.cfr, s, w_lb, True),
        f"Tool's path: pull-and-treat, then metaphylaxis on day {day}": V.outcomes(H, p_true, s.meta_rr, late, s.cfr, s, w_lb, True),
    }

    L = [f"# Demonstration case: lot {LOT}, Yard A", "",
         "*Synthetic, fictional data. One end-to-end decision: inputs, alternatives, recommendation, projected consequences.*", "",
         "## 1. Arrival (Nov 2026): what the manager knows",
         f"- **{H} head, {row.sex}s, {row.arrival_weight_lb:.0f} lb**, bought through a **backgrounder**, arriving at Yard A "
         "(Texas Panhandle receiving yard: light calves, tight hospital pens).",
         f"- Haul: {'unknown' if pd.isna(row.haul_hours) else f'{row.haul_hours:.1f} h'}; sources commingled: "
         f"{'unknown' if pd.isna(row.n_sources) else int(row.n_sources)}; preconditioning: "
         f"{'unknown' if pd.isna(row.preconditioning) else row.preconditioning}; pre-arrival vaccination: "
         f"{'unknown' if pd.isna(row.pre_arrival_vaccinated) else row.pre_arrival_vaccinated}.",
         f"- **Buyer's call: {row.buyer_risk_call}.** Under Yard A's current practice that means no metaphylaxis.", "",
         "## 2. Risk at arrival (tool, page 3)",
         f"- Expected 45-day BRD morbidity without metaphylaxis: **{a.exp_morbidity:.1%}** (80% range {a.lo:.1%}-{a.hi:.1%}); "
         f"chance of a high-morbidity lot (>=15%): **{a.p_high:.0%}**.",
         "- Drivers: " + "; ".join(f"{r.factor} ({r.domain}{', unknown - typical value used' if r.unknown else ''})" for r in ex.head(5).itertuples()) + ".",
         "- High-risk states met (Adekunle et al. 2026, Table A1): " + ", ".join(cl.loc[cl.met == True, "risk_factor"])
         + "; unknown: " + (", ".join(cl.loc[cl.met.isna(), "risk_factor"]) or "none") + ".", "",
         "## 3. Options at arrival (tool, page 4)", ""] + fmt_tab(res0.table) + [
         "", f"**Recommendation: {res0.table.loc[res0.table.option == res0.recommended, 'label'].iloc[0]}.** {res0.note}", ""]
    if len(voi):
        L.append("Information that would change the decision: " + "; ".join(f"{r.field} (${r.value_per_head:.2f}/head)" for r in voi.itertuples()) + ".")
    L += ["", f"## 4. Day {day} checkpoint: the yard's own records update the risk (page 3)",
          f"- By day {day}: **{pulls5} BRD pulls** of {H} head, and feed delivered on days 2-5 ran **{dip:.1%} below** the "
          "receiving-diet plan (Heinen 2022: early feed-delivery change is the strongest early signal of a high-morbidity lot).",
          f"- Updated risk: **{s5['exp_morbidity']:.1%}** (80% range {s5['lo']:.1%}-{s5['hi']:.1%}); chance of >=15% morbidity "
          f"**{s5['p_high']:.0%}** (was {a.p_high:.0%} at arrival).", "", "Options now:", ""] + fmt_tab(res5.table) + [
          "", f"**Recommendation on day {day}: {res5.table.loc[res5.table.option == res5.recommended, 'label'].iloc[0]}.** {res5.note}",
          "*Drug choice and administration remain with the consulting veterinarian.*", "",
          "## 5. Feasibility (page 5)",
          "- Yard A is the yard where capacity binds this week: the plan uses all its spare rider time and its expected peak "
          "hospital load exceeds its free hospital-pen spaces. Catching this lot early keeps sick cattle out of an already full "
          "hospital pen; un-isolated sick cattle keep transmitting (SEIR-Q, Adekunle & Kaniyamattam 2026).", "",
          "## 6. What the simulation's hidden truth shows",
          f"The generator gave this lot a true untreated BRD risk of **{p_true:.1%}** - a high-morbidity lot the buyer called low.", "",
          "| Path | Expected cases | Expected deaths | Antimicrobial doses | Expected cost |", "|---|---|---|---|---|"]
    for k, (cases, deaths, doses, cost) in paths.items():
        L.append(f"| {k} | {float(cases):.1f} | {float(deaths):.1f} | {float(doses):.0f} | ${float(cost):,.0f} |")
    c0 = float(list(paths.values())[0][3]); c2 = float(list(paths.values())[2][3])
    d0 = float(list(paths.values())[0][1]); d2 = float(list(paths.values())[2][1])
    L += ["", f"Following the tool instead of the buyer's call avoids about **{d0 - d2:.1f} deaths** and **${c0 - c2:,.0f}** "
          f"(${(c0 - c2) / H:.0f}/head) on this lot. Treating on arrival would have done better still on this lot, but the arrival "
          "information did not support it with confidence - and across a season, mass-treating every uncertain lot costs more "
          "(docs/evaluation.md). The day-5 checkpoint is how the tool turns 'we don't know yet' into a timely, accountable decision.",
          "", "*Projected consequences use the parameter ledger's assumptions (metaphylaxis halves cases; 2026 prices) and remain "
          "subject to veterinary review.*"]
    (ROOT / "docs" / "demo_case.md").write_text("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
