# Demonstration case: arrival decision for the week of Nov 16, 2026

Synthetic, fictional data. One end-to-end decision: inputs, alternatives, recommendation and projected consequences.
To follow along, open https://penpoint-brd.streamlit.app/, upload the three files in `demo_data/`, then go to
**Herd status → Risk overview** and **Management options → Treatment options**.

## 1. The decision

Seven lots (878 cattle) are about to arrive. For each lot, the manager decides between **metaphylaxis on arrival**
and **pull and treat** (treating only cattle that get sick). The veterinarian reviews the plan before any treatment.

## 2. Inputs

- Each lot's cattle list from `demo_data/cattle.csv`: arrival weights, haul times, sex, preconditioning, vaccination
  before arrival and purchase channel. Lot values are averaged from the animals; missing details stay missing.
- The buyer's high or low risk call for each lot.
- 2026 default costs: metaphylaxis $30 per head, metaphylaxis prevents 50% of cases (ME 0.5), and one sick animal
  costs $514 at 550 lb (treatment, lost growth and the risk of death).
- The yard's current approach: metaphylaxis when the buyer calls a lot high risk.

## 3. Focus lot: C100009

Pen 14, 151 steers, Mexico import, arriving Nov 18. **The buyer called it low risk.**

- **Decision tree:** average weight 445 lb (at most 595 lb), haul 8.1 h (at most 16.3 h), not vaccinated before
  arrival. In the training history, 51 of 218 lots that answered these questions the same way (23%) became high risk.
- **Adjustment for its own details:** a haul over 6 hours raises its risk, not coming through a sale barn lowers it,
  and its lighter weight raises it.
- **Result:** risk score 25, rated **High risk** (90% range 20% to 30%), well above the 8.5% cutoff.

## 4. Alternatives (all 7 arriving lots, first 45 days)

| Option | Lots on metaphylaxis | Expected cost | BRD cases | BRD deaths | Antibiotic doses |
|---|---|---|---|---|---|
| Current approach (buyer's call) | 4 | $36,969 | 41.8 | 6.1 | 610 |
| **PenPoint plan** | 4 | **$34,975** | **39.2** | **5.7** | **569** |
| Metaphylaxis on every lot | 7 | $41,419 | 31.3 | 4.5 | 914 |
| Pull and treat on every lot | 0 | $30,158 | 62.6 | 9.1 | 73 |

## 5. Recommendation

Metaphylaxis on arrival for **C100002, C100016, C100009 and C100015**. Pull and treat for **C100013, C100003 and C100007**.

Compared with the buyer's call, metaphylaxis moves from C100013 (called high by the buyer, risk score 3) to C100009
(called low by the buyer, risk score 25). Pull and treat alone would be cheaper for each of these lots, but it would
raise expected deaths. PenPoint's rule that the plan must expect at least 5% fewer deaths than the current approach
keeps metaphylaxis on these four, and the dashboard labels them.

## 6. Projected consequences

Compared with the current approach, the PenPoint plan is expected to:

- cost **$1,994 less** in health costs,
- prevent **2.6 more BRD cases** and **0.4 more deaths**,
- use **41 fewer antibiotic doses**.

**Close call:** C100015 (149 steers, 25 hour haul) has a 90% risk range of 18% to 44%. Across that range, the cheaper
option changes, so PenPoint flags it for the veterinarian rather than presenting a confident answer.

The plan is exported from **Management options → Decision summary** as a one-page report with a line for the
veterinarian's approval.

These are model projections on simulated data, not observed results. Drug choice, dose and withdrawal remain with
the consulting veterinarian.
