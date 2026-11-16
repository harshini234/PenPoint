from __future__ import annotations

from dataclasses import dataclass, field

TIERS = {
    "always": "Recorded by every commercial yard at arrival",
    "usually": "Usually known from the purchase / buyer",
    "often_missing": "Frequently unknown, especially for sale-barn lots",
    "derived": "Computed by the tool from other fields",
    "daily": "Recorded daily after arrival (health log, feed calls)",
    "sensor": "Only if the yard runs monitoring technology",
}


@dataclass(frozen=True)
class Field:
    name: str
    dtype: str
    unit: str
    tier: str
    description: str
    allowed: tuple = ()
    documents: tuple = ()
    risk_input: bool = True
    notes: str = ""


LOT_FIELDS: list[Field] = [
    Field("lot_id", "str", "", "always", "Unique lot identifier", risk_input=False),
    Field("yard_id", "str", "", "always", "Yard receiving the lot", allowed=("A", "B", "C", "D"), risk_input=False),
    Field("arrival_date", "date", "YYYY-MM-DD", "always", "Date the lot arrived (day 0)", documents=("scale_ticket",)),
    Field("head_count", "int", "head", "always", "Number of animals in the lot", documents=("invoice", "cvi", "scale_ticket")),
    Field("sex", "category", "", "always", "Sex composition of the lot", allowed=("steer", "heifer", "mixed"), documents=("invoice", "cvi")),
    Field("arrival_weight_lb", "float", "lb/head", "always", "Average arrival (scale) weight", documents=("scale_ticket",)),
    Field("pen_area_m2_per_head", "float", "m2/head", "always", "Pen area divided by head count (Rojas predictor)"),
    Field("bunk_cm_per_head", "float", "cm/head", "always", "Linear bunk space per head (Rojas predictor)"),
    Field("market_channel", "category", "", "usually", "How the lot was bought",
          allowed=("sale_barn", "ranch_direct", "backgrounder", "mexico_import"), documents=("invoice",)),
    Field("buyer_risk_call", "category", "", "usually", "Buyer/manager risk classification at arrival (current practice)",
          allowed=("high", "low"), risk_input=False, notes="Used as the current-practice baseline, not as a model input"),
    Field("pay_weight_lb", "float", "lb/head", "often_missing", "Purchase (pay) weight on the sale invoice", documents=("invoice",)),
    Field("origin_state", "str", "", "often_missing", "State (or country) of origin", documents=("cvi", "invoice")),
    Field("haul_hours", "float", "hours", "often_missing", "Transport duration", documents=("trucking_manifest",)),
    Field("n_sources", "int", "sources", "often_missing", "Number of consignors / origins commingled in the lot", documents=("invoice",)),
    Field("preconditioning", "category", "", "often_missing", "Preconditioning program completed",
          allowed=("none", "VAC24", "VAC34", "VAC45"), documents=("precon_certificate",)),
    Field("pre_arrival_vaccinated", "bool", "", "often_missing", "Respiratory vaccination before arrival", documents=("precon_certificate",)),
    Field("temp_range_wk1_f", "float", "deg F", "always", "Mean daily max-min temperature in arrival week (weather station)",
          notes="Synthetic climatology in v1; replace with Mesonet station data"),
    Field("shrink_pct", "float", "%", "derived", "(pay_weight - arrival_weight) / pay_weight x 100"),
    Field("long_haul", "bool", "", "derived", "haul_hours >= 6 (Table A1 threshold)"),
    Field("arrival_quarter", "int", "1-4", "derived", "Quarter of arrival date"),
]

DAILY_FIELDS: list[Field] = [
    Field("lot_id", "str", "", "daily", "Lot identifier", risk_input=False),
    Field("day", "int", "days on feed", "daily", "Days since arrival (0-45)", risk_input=False),
    Field("pulls", "int", "head", "daily", "Animals pulled and treated for BRD that day (first treatments)"),
    Field("deaths", "int", "head", "daily", "BRD deaths that day"),
    Field("feed_pct_bw", "float", "% of body weight (DM)", "daily", "Feed delivered per head as % of arrival weight, dry-matter basis"),
]

YARD_FIELDS = [
    "yard_id", "name", "region", "riders", "rider_hours_per_day", "hospital_pen_head", "chute_hours_per_day",
]


def lot_columns() -> list[str]:
    return [f.name for f in LOT_FIELDS]


def risk_input_fields() -> list[Field]:
    return [f for f in LOT_FIELDS if f.risk_input]
