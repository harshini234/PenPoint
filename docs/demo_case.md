Demonstration case: lot C100007, Yard A
Synthetic, fictional data. One end-to-end decision: inputs, alternatives, recommendation, projected consequences.

1. Arrival (Nov 2026): what the manager knows
74 head, heifers, 524 lb, bought through a backgrounder, arriving at Yard A (Texas Panhandle receiving yard: light calves, tight hospital pens).
Haul: unknown; sources commingled: 4; preconditioning: VAC45; pre-arrival vaccination: True.
Buyer's call: low. Under Yard A's current practice that means no metaphylaxis.
2. Risk at arrival (tool, page 3)
Expected 45-day BRD morbidity without metaphylaxis: 6.4% (80% range 1.4%-13.6%); chance of a high-morbidity lot (>=15%): 8%.
Drivers: Arrival season (environmental); Arrival weight (biological); Preconditioning / weaning (operational); Long haul (>=6 h) (operational, unknown - typical value used); Stacked stressors (risk threshold) (operational, unknown - typical value used).
High-risk states met (Adekunle et al. 2026, Table A1): Commingling, Stocking density, Weight, Season; unknown: Transportation.
3. Options at arrival (tool, page 4)
Option	Cases (80% range)	Deaths	Doses	Expected cost	$/head vs current	Best in
Current practice (pull-and-treat)	5.2 (1.0-11.2)	0.8	6	$2,617	+0.00	
Metaphylaxis on arrival	2.6 (0.5-5.5)	0.4	77	$3,537	+12.43	16%
Pull-and-treat only	5.2 (1.0-11.2)	0.8	6	$2,617	+0.00	75%
Pull-and-treat + extra rider pass	5.2 (1.0-11.2)	0.7	6	$2,694	+1.04	8%
Pull-and-treat, re-decide on day 5	4.9 (1.0-10.4)	0.7	9	$2,579	-0.51	0%
Recommendation: Pull-and-treat, re-decide on day 5. No metaphylaxis on arrival; review the day-5 pull and feed records. They would trigger metaphylaxis in 4% of plausible scenarios. Metaphylaxis on arrival pays off in only 16%.

Information that would change the decision: haul_hours ($0.16/head).

4. Day 5 checkpoint: the yard's own records update the risk (page 3)
By day 5: 2 BRD pulls of 74 head, and feed delivered on days 2-5 ran 6.9% below the receiving-diet plan (Heinen 2022: early feed-delivery change is the strongest early signal of a high-morbidity lot).
Updated risk: 28.8% (80% range 18.2%-40.1%); chance of >=15% morbidity 96% (was 8% at arrival).
Options now:

Option	Cases (80% range)	Deaths	Doses	Expected cost	$/head vs current	Best in
Keep current course	22.0 (13.0-31.1)	3.2	26	$11,105	+0.00	0%
Metaphylaxis now (late)	14.3 (8.5-20.1)	2.1	91	$9,413	-22.87	78%
Extra rider pass from today	22.0 (13.0-31.1)	2.8	26	$10,489	-8.33	21%
Recommendation on day 5: Metaphylaxis now (late). Metaphylaxis now (late) is best in 78% of plausible scenarios. Drug choice and administration remain with the consulting veterinarian.

5. Feasibility (page 5)
Yard A is the yard where capacity binds this week: the plan uses all its spare rider time and its expected peak hospital load exceeds its free hospital-pen spaces. Catching this lot early keeps sick cattle out of an already full hospital pen; un-isolated sick cattle keep transmitting (SEIR-Q, Adekunle & Kaniyamattam 2026).
6. What the simulation's hidden truth shows
The generator gave this lot a true untreated BRD risk of 47.5% - a high-morbidity lot the buyer called low.

Path	Expected cases	Expected deaths	Antimicrobial doses	Expected cost
Current practice (buyer said low: pull-and-treat only)	35.1	5.1	41	$17,717
Metaphylaxis on arrival	17.6	2.5	94	$11,079
Tool's path: pull-and-treat, then metaphylaxis on day 5	22.7	3.3	100	$13,660
Following the tool instead of the buyer's call avoids about 1.8 deaths and $4,057 ($55/head) on this lot. Treating on arrival would have done better still on this lot, but the arrival information did not support it with confidence - and across a season, mass-treating every uncertain lot costs more (docs/evaluation.md). The day-5 checkpoint is how the tool turns 'we don't know yet' into a timely, accountable decision.

Projected consequences use the parameter ledger's assumptions (metaphylaxis halves cases; 2026 prices) and remain subject to veterinary review.
