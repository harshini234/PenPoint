# Data dictionary

All demo data are **synthetic and fictional** (scripts/generate_data.py). Field definitions live in `src/brd/schema.py`; this file is generated from it by `scripts/make_data_dictionary.py`.

## Data tiers

| Tier | Meaning |
|---|---|
| `always` | Recorded by every commercial yard at arrival |
| `usually` | Usually known from the purchase / buyer |
| `often_missing` | Frequently unknown, especially for sale-barn lots |
| `derived` | Computed by the tool from other fields |
| `daily` | Recorded daily after arrival (health log, feed calls) |
| `sensor` | Only if the yard runs monitoring technology |

## Lot fields (`lots_history.csv`, `lots_current.csv`) - one row per arrival lot

| Field | Type | Unit | Tier | Description | Allowed values | Paperwork it can come from |
|---|---|---|---|---|---|---|
| `lot_id` | str |  | always | Unique lot identifier |  |  |
| `yard_id` | str |  | always | Yard receiving the lot | A, B, C, D |  |
| `arrival_date` | date | YYYY-MM-DD | always | Date the lot arrived (day 0) |  | scale_ticket |
| `head_count` | int | head | always | Number of animals in the lot |  | invoice, cvi, scale_ticket |
| `sex` | category |  | always | Sex composition of the lot | steer, heifer, mixed | invoice, cvi |
| `arrival_weight_lb` | float | lb/head | always | Average arrival (scale) weight |  | scale_ticket |
| `pen_area_m2_per_head` | float | m2/head | always | Pen area divided by head count (Rojas predictor) |  |  |
| `bunk_cm_per_head` | float | cm/head | always | Linear bunk space per head (Rojas predictor) |  |  |
| `market_channel` | category |  | usually | How the lot was bought | sale_barn, ranch_direct, backgrounder, mexico_import | invoice |
| `buyer_risk_call` | category |  | usually | Buyer/manager risk classification at arrival (current practice) - Used as the current-practice baseline, not as a model input | high, low |  |
| `pay_weight_lb` | float | lb/head | often_missing | Purchase (pay) weight on the sale invoice |  | invoice |
| `origin_state` | str |  | often_missing | State (or country) of origin |  | cvi, invoice |
| `haul_hours` | float | hours | often_missing | Transport duration |  | trucking_manifest |
| `n_sources` | int | sources | often_missing | Number of consignors / origins commingled in the lot |  | invoice |
| `preconditioning` | category |  | often_missing | Preconditioning program completed | none, VAC24, VAC34, VAC45 | precon_certificate |
| `pre_arrival_vaccinated` | bool |  | often_missing | Respiratory vaccination before arrival |  | precon_certificate |
| `temp_range_wk1_f` | float | deg F | always | Mean daily max-min temperature in arrival week (weather station) - Synthetic climatology in v1; replace with Mesonet station data |  |  |
| `shrink_pct` | float | % | derived | (pay_weight - arrival_weight) / pay_weight x 100 |  |  |
| `long_haul` | bool |  | derived | haul_hours >= 6 (Table A1 threshold) |  |  |
| `arrival_quarter` | int | 1-4 | derived | Quarter of arrival date |  |  |

## Outcome / status fields

| Field | Type | Unit | Description |
|---|---|---|---|
| `metaphylaxis_given` | bool |  | Arrival metaphylaxis given under the yard's current practice (blank = decision pending) |
| `cases_45` | int | head | Animals treated for BRD at least once within 45 days (first treatments) - Rojas outcome definition |
| `morbidity_45` | float | proportion | cases_45 / head_count |
| `deaths_45` | int | head | BRD deaths within 45 days |
| `mortality_45` | float | proportion | deaths_45 / head_count |
| `status` | category |  | lots_current only: in_progress (arrived) or arriving (decision pending) |
| `days_on_feed` | int | days | lots_current only: days since arrival as of 2026-11-14 (negative = not yet arrived) |

## Daily fields (`daily_history.csv`, `daily_current.csv`) - one row per lot per day

| Field | Type | Unit | Description |
|---|---|---|---|
| `lot_id` | str |  | Lot identifier |
| `day` | int | days on feed | Days since arrival (0-45) |
| `pulls` | int | head | Animals pulled and treated for BRD that day (first treatments) |
| `deaths` | int | head | BRD deaths that day |
| `feed_pct_bw` | float | % of body weight (DM) | Feed delivered per head as % of arrival weight, dry-matter basis |

## Evaluation-only fields (`truth_*.csv`) - never shown in the dashboard

Complete inputs (no missing values) plus:

| Field | Description |
|---|---|
| `origin_region` | Origin region used to compute haul distance |
| `true_logodds` | Latent log-odds of an animal becoming a BRD case without metaphylaxis (incl. lot random effect) |
| `p_case_no_meta` | Probability an animal becomes a case without metaphylaxis |
| `meta_rr` | Relative risk applied if metaphylaxis was given (1 otherwise) |
| `p_case_observed` | Probability actually applied under current practice |
| `high_observed` | morbidity_45 >= 15% |
| `high_counterfactual` | Would have been >= 15% without metaphylaxis |

## Yards (`yards.csv`)

Fictional yards from `params/yards.yaml`: riders, rider hours/day, hospital-pen capacity (head), chute hours/day - the binding constraints used by the feasibility step.
