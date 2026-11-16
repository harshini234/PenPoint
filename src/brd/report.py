from __future__ import annotations

from datetime import date

import pandas as pd

from . import params as P
from .econ import Settings

VET = ("**Veterinary review required.** Medication-related options are decision support only. Drug choice, dose, "
       "withdrawal times and any metaphylaxis decision remain with the consulting veterinarian.")


def _money(x):
    return f"${x:,.0f}"


def lot_summary(row: pd.Series, risk: pd.Series, res, s: Settings, voi: pd.DataFrame, checklist: pd.DataFrame,
                drivers: pd.DataFrame) -> str:
    H = int(row["head_count"])
    tab = res.table
    rec = tab.loc[tab.option == res.recommended].iloc[0]
    L = [f"# BRD decision summary - lot {row['lot_id']} (Yard {row['yard_id']})",
         f"*Prepared {date.today().isoformat()} with the BRD Decision Aid. Synthetic demonstration data.*", "",
         "## The lot",
         f"- {H} head, {row['sex']}, {row['arrival_weight_lb']:.0f} lb, bought via **{row['market_channel'].replace('_', ' ')}**, "
         f"arrived {row['arrival_date']} ({row.get('status', 'arriving').replace('_', ' ')}"
         + (f", day {int(row['days_on_feed'])} on feed" if row.get("status") == "in_progress" else "") + ")",
         f"- Buyer's call: **{row.get('buyer_risk_call', 'n/a')}**. Information known: {risk['completeness']:.0%} of risk inputs.",
         "", "## Risk (first 45 days, without arrival metaphylaxis)",
         f"- Expected BRD morbidity **{risk['exp_morbidity']:.1%}** (likely range {risk['lo']:.1%} - {risk['hi']:.1%}); "
         f"chance of a high-morbidity lot (>=15%): **{risk['p_high']:.0%}**. Basis: {risk['basis']}.",
         "- Main drivers: " + "; ".join(f"{r.factor} ({r.domain}, {'raises' if r.log_odds > 0 else 'lowers'} risk)"
                                         for r in drivers.head(4).itertuples()) + ".",
         "- High-risk states met (Adekunle et al. 2026, Table A1): "
         + (", ".join(checklist.loc[checklist["met"] == True, "risk_factor"]) or "none")
         + ("; unknown: " + ", ".join(checklist.loc[checklist["met"].isna(), "risk_factor"]) if checklist["met"].isna().any() else ""),
         "", "## Options compared with current practice", "",
         "| Option | Cases | Deaths | Antimicrobial doses | Expected cost | Cost vs current ($/head) | Doses vs current (/head) |",
         "|---|---|---|---|---|---|---|"]
    for r in tab.itertuples():
        L.append(f"| {r.label} | {r.cases:.1f} ({r.cases_lo:.1f}-{r.cases_hi:.1f}) | {r.deaths:.1f} | {r.doses:.0f} | "
                 f"{_money(r.cost)} | {r.vs_current_cost_per_head:+.2f} | {r.vs_current_doses_per_head:+.2f} |")
    L += ["", "## Recommendation",
          f"**{rec['label']}.** {res.note}",
          f"- Compared with current practice: {rec['vs_current_cost_per_head']:+.2f} $/head, "
          f"{rec['vs_current_doses_per_head']:+.2f} antimicrobial doses/head.",
          "- Confidence: " + ("the information supports this call." if res.confident else
                              "**low - the available information cannot support a confident decision.**")]
    if len(voi) and voi["value_per_head"].max() > 0.05:
        top = voi.iloc[0]
        L.append(f"- Information worth getting first: **{top['field']}** (worth about ${top['value_per_head']:.2f}/head to this decision).")
    L += ["", "## Assumptions behind these numbers",
          f"- Feeder price ${s.feeder_price_cwt:.0f}/cwt; metaphylaxis ${s.meta_cost:.0f}/head; treatment ${s.tx_cost:.0f}/case; "
          f"lost performance ${s.perf_loss:.0f}/treated survivor; BRD case fatality {s.cfr:.1%}.",
          f"- Metaphylaxis cuts BRD cases to {s.meta_rr:.0%} (range {s.meta_rr_low:.0%}-{s.meta_rr_high:.0%}) of untreated "
          "(Rojas 2022; Horton 2023; Baptiste 2017). Stewardship weight: "
          f"${s.stewardship_per_dose:.0f} per dose.",
          "- Every input is listed with its source and evidence type on the dashboard's Sources page.", "", VET]
    return "\n".join(L)


def plan_summary(out: dict, s: Settings, lots: pd.DataFrame) -> str:
    cur, pl = out["totals_current"], out["totals_plan"]
    head = int(lots["head_count"].sum())
    L = [f"# BRD plan for this week - all yards ({len(lots)} lots, {head:,} head)",
         f"*Prepared {date.today().isoformat()} with the BRD Decision Aid. Synthetic demonstration data.*", "",
         "## Plan vs current practice", "",
         "| | Current practice | Recommended plan | Change |", "|---|---|---|---|"]
    for k, lab in [("total_cost", "Expected cost (incl. hospital overflow)"), ("doses", "Antimicrobial doses"),
                   ("cases", "BRD cases"), ("deaths", "BRD deaths"), ("sick_days", "Untreated sick-days")]:
        L.append(f"| {lab} | {cur[k]:,.0f} | {pl[k]:,.0f} | {pl[k] - cur[k]:+,.0f} |")
    L += ["", "## Capacity check", "", "| Yard | Extra rider h/day (cap) | Peak hospital head (cap) | Overflow |", "|---|---|---|---|"]
    for r in out["utilisation"].itertuples():
        L.append(f"| {r.yard_id} | {r.rider_hours_day:.2f} ({r.rider_cap:.2f}) | {r.hospital_peak:.0f} ({r.hospital_cap:.0f}) | {r.overflow:.0f} |")
    sh = out["shadow"]
    sh = sh[sh["value_of_one_more_unit"].abs() > 1]
    if len(sh):
        L += ["", "## Binding constraints (what more capacity would be worth over these lots' 45 days)"]
        names = {"rider": "one more rider hour per day", "hospital": "one more hospital-pen space", "chute": "one more chute minute",
                 "welfare": "one more allowed untreated sick-day",
                 "mortality": "the no-more-deaths rule (savings given up per death it prevents; the rule stays on)"}
        for r in sh.itertuples():
            L.append(f"- Yard {r.yard_id}: {names.get(r.constraint, r.constraint)} - about {_money(r.value_of_one_more_unit)}")
    L += ["", "## Lot-by-lot actions", "", "| Lot | Yard | Action |", "|---|---|---|"]
    for r in out["chosen"].sort_values(["yard_id", "lot_id"]).itertuples():
        L.append(f"| {r.lot_id} | {r.yard_id} | {r.label} |")
    L += ["", f"Stewardship weight used: ${s.stewardship_per_dose:.0f} per antimicrobial dose. Welfare floor: untreated "
          f"sick-days may not exceed current practice{'' if s.welfare_slack == 0 else f' + {s.welfare_slack:.0%}'}. "
          f"Fixed rule: expected BRD deaths at least {P.get('mortality_cap_margin'):.0%} below current practice.", "", VET]
    return "\n".join(L)


def to_html(md_text: str, title: str) -> str:
    import markdown
    body = markdown.markdown(md_text, extensions=["tables"])
    return f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>{title}</title>
<style>body{{font-family:system-ui,Arial,sans-serif;max-width:900px;margin:32px auto;padding:0 16px;color:#222;line-height:1.45}}
table{{border-collapse:collapse;margin:8px 0;font-size:14px}}th,td{{border:1px solid #ccc;padding:4px 8px;text-align:left}}
th{{background:#f3f3f3}}h1{{font-size:22px}}h2{{font-size:17px;margin-top:22px}}@media print{{body{{margin:0}}}}</style>
</head><body>{body}</body></html>"""
