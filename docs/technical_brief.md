# PenPoint: BRD decisions under uncertainty in the first 45 days on feed

**Technical brief - AISFS × Merck Animal Health Hackathon 2026, Problem 1** · Team: [names] · Dashboard: [URL] · Repo: [URL]

## 1. Decision problem
**User:** a receiving-yard manager, with the consulting veterinarian, who owns every medication decision.
**Decision unit:** the arrival **lot**. Arrival metaphylaxis is decided per lot, and the best outcome data (Rojas et al. 2022) are lot-level. Animals enter through their weights, treatments, removals and SenseHub alerts.
**Decisions supported and when:**
- *Arrival (day 0):* metaphylaxis or pull-and-treat for each arriving lot.
- *On feed (days 1-45):* whether to ask the vet about late metaphylaxis, given the lot's own treatment record so far.
- *Daily:* which cattle to check (SenseHub alerts, recent treatments), which data conflicts to fix, and whether the hospital pen will hold the expected cases.

**Information available at decision time:** per-animal records (arrival weight, haul time, sex, preconditioning, pre-arrival vaccination), lot details (buyer's high/low call, purchase channel, pen area and bunk length), health records (treatments with drug, class and withdrawal; retreatments; deaths) and a daily SenseHub alert export. Numbers that vary animal to animal (weight, haul time) are averaged for the lot. Categories (sex, preconditioning, vaccination) are lot-level; an animal recorded differently is flagged as a conflict and that category is left out until resolved. Missing details are shown as missing, never guessed.

The core question: *which arriving lots are high-risk for BRD, why, and is metaphylaxis worth its cost for each one at 2026 prices, without letting expected deaths rise?*

## 2. Data and provenance
No dataset was provided. The original data that best fit the problem (Rojas 2022: 1,733 lots, 10 feedlots) are proprietary, so we built a **synthetic but calibrated world**: one fictional receiving yard in the Texas Panhandle, with 1,500 history lots for training and 18 current lots (1,972 head) for the demo.
- **90 parameters** sit in one ledger (`params/parameters.yaml`), each with value, range, source link, page or table, and an evidence tag: **34 observed** in a source, **8 estimated** from sources, **5 calibrated**, **43 assumed** (mostly effect magnitudes where the literature gives direction only). The dashboard shows every tag.
- **Calibration:** 5 values were fitted so that, under current practice, the simulated history reproduces published figures:

  | Figure | Published | Ours | Source |
  |---|---|---|---|
  | Lots ≥15% morbidity | 10.8% | 10.2% | Rojas 2022 |
  | Mean 45-day morbidity | 6.3% | 5.6% | Rojas 2022 |
  | Buyer-call sensitivity / specificity | 84% / 60% | 85% / 60% | Rojas 2022 |
  | Fall 45-day incidence | 8.6% | 7.5% | Cernicchiaro et al. 2011 (288,388 head) |
  | Untargeted check: morbidity in high / low lots | 27.1% / 3.8% | 24.2% / 3.5% | Rojas 2022 |

  Our high-risk tail is somewhat thinner than research herds of high-risk calves (48-52% morbidity; Wottlin 2021, Pillen 2016), so the simulation is, if anything, conservative.
- **Real public sources** for prices and context: CME feeder index (≈$348/cwt, Oct 2026), USDA NASS Cattle on Feed, K-State Focus on Feedlots, USDA AMS Market News API, Kansas and West Texas Mesonet weather (manual download only; the Kansas Mesonet prohibits automated ingest without consent), FDA 2024 antimicrobial sales report, NAHMS 2017.
- **Data a yard can bring in:** lot and per-animal records (typed in or edited in the app); health certificates, invoices and preconditioning certificates, read for missing lot details and confirmed by the user before use; a daily SenseHub alert export (CSV, matched by tag or EID); local weather (Open-Meteo forecast), shown for context.
- **Privacy and licensing:** no real animal, owner or premises data are used. The yard, lots and documents are fictional.

## 3. Approach
**Risk (Herd status): a decision tree, as in Rojas et al. (2022).** We chose their method for their reasons: a tree's questions can be read and checked by a manager, it handles mixed numeric and categorical inputs and missing values, and it gives a lot-level call that can be priced with their economic equations.
- **Predictors:** the paper's Table 2 set (head count, average arrival weight, arrival quarter, sex, pen area, bunk length, and both per head) plus preconditioning, vaccination and haul time, each with an "unknown" level.
- **Outcome:** high-risk lot = 15% or more treated for BRD at least once in 45 days.
- **Fitting:** 75/25 split stratified by outcome; 10-fold stratified cross-validation over depth (2-4), minimum lots per branch (20-50) and pruning, scored by AUC. Chosen: depth 3, 30 lots per branch.
- **Cutoff:** Youden's J on out-of-fold training predictions (t* = 8.5%), as in the paper.
- **Adjustment for the lot's own details.** A depth-3 tree can only ask three questions, so preconditioning or vaccination may never be asked. PenPoint therefore starts from the branch share p₀ and adjusts it with published effect sizes for how this lot differs from the average of the branch's own past lots: logit(p) = logit(p₀) + Σ ln(ORₖ)(xₖ − x̄ₖ). Factors: preconditioned (OR 0.54, Mijar 2023, observed), pre-arrival vaccination (0.80), haul ≥ 6 h (1.4), sale-barn purchase (1.6) and weight (log-odds 0.45 per 100 lb lighter), the last four labelled assumptions and all editable. Because only the difference from similar past lots counts, a factor the tree already used is not counted twice; unknown factors add nothing.
- **Output per lot:** a risk score (100 × p), the call, the tree's questions in plain words, the starting estimate with its lot count, the adjustment table, and **Not sure yet** when the 90% range (the branch's Wilson interval, shifted by the adjustment) crosses t* or the branch holds fewer than 20 lots.

**Costs (Management options): Rojas' net health cost benefit (NHCB, Eqs 1-5).** Per lot, with CS head, treatment cost TC, metaphylaxis effect ME, cost of a sick animal MC, and m_H, m_L the BRD rates of high- and low-risk lots in history:
- TP = CS(MC·m_H·ME − TC), FP = −CS·TC, FN = −CS·MC·m_H·ME, TN = 0. Eq 3 as printed multiplies by TC and uses BRD45 (the share of lots that are high-risk); the units only work with CS and m_H (their Table 3 gives 27%), so we use that and say so in the app.
- q = the lot's adjusted chance of being high-risk (p above); expected BRD rate E[m] = q·m_H + (1−q)·m_L.
- Expected cost: metaphylaxis CS·TC + CS·MC·E[m]·(1−ME); pull-and-treat CS·MC·E[m]. Metaphylaxis pays when E[m] > TC/(MC·ME) (11.7% at the 2026 defaults: MC $514 at 550 lb, TC $30, ME 0.5).
- MC = (1 − case fatality)(treatment + lost performance) + case fatality × cost of a death (animal value + feed and yardage + treatment). Every input has a 2026 default and is editable on the Constraints page.
- **No more deaths (always on):** the plan's expected BRD deaths must be at least 5% below current practice (the margin is editable, never below 0%) (the buyer's call by default). If the cheapest plan breaks the rule, lots are switched to metaphylaxis in order of lowest cost per death avoided until it holds.
- **Lots on feed:** projected 45-day rate = F(d)·(rate so far ÷ F(d)) + (1−F(d))·E[m], where F is the onset curve; late metaphylaxis is priced on the cases still to come, at a reduced effect.

**When information can't support a decision.** Each lot's two option costs are recomputed at both ends of its 90% risk range. If the cheaper option flips, the lot is marked "Not confident: vet review" on Treatment options, in the decision summary and on the lot's cost page, with the cost ranges and the missing details that would narrow them.

**Comparing approaches.** Management options opens on four approaches for the arriving lots: current practice (chosen by the user: buyer's call, all sale-barn lots, or none), PenPoint's plan, metaphylaxis on every lot and pull-and-treat on every lot, by expected cost, cases, deaths and antimicrobial doses, with a cost-against-doses chart. Scenario analysis changes TC, ME, feeder price, case fatality, current practice and the deaths margin without saving, and shows which lots' recommendations change. The decision summary downloads as a one-page HTML report with a veterinarian approval line.

**Transparency.** Every number in the app has a "Show the work" note: the numbered equation, the variables, and today's values plugged in. A separate page lists every equation in plain words.

**Data handling.** Lots, cattle, health records, uploads, settings and the treatment protocol live in PostgreSQL (`DATABASE_URL`; a local SQLite file is the fallback), not the browser. The app starts empty; a yard's data (or the demo files) come in through a bulk import of one cattle file plus optional health records and SenseHub report. Treatments are numbered per animal by date and carry drug, product, class, route and withdrawal days from the vet's protocol, editable. SenseHub alerts need a daily upload; when the latest report is older than today, every alert is marked "alerts from mm/dd/yy".

## 4. Evaluation
**Tree vs the buyer's call, on 375 held-back history lots** (simulated history calibrated to Rojas' published figures; see Section 2):

| | Se | Sp | PPV | NPV | AUC |
|---|---|---|---|---|---|
| Decision tree | 78.9% | 58.5% | 17.6% | 96.1% | 0.748 (CV 0.770) |
| Buyer's call | 76.3% | 53.1% | 15.5% | 95.2% | – |
| Rojas 2022 tree / buyer (real data) | 44.7% / 83.8% | 83.7% / 59.8% | | | 0.682 |

The buyer scores lower here than in the calibration table (85% / 60%) because this table scores against observed outcomes, which metaphylaxis on buyer-called lots has already lowered (the confounding Rojas note), while calibration scores against the simulation's untreated truth.

**NHCB per animal, tree minus buyer** (Eq 9, 2026 defaults): +$1.69 at this history's 10% high-risk share, +$1.78 at 20%, +$2.05 at 50%. The tree is worth slightly more than the buyer's call at every share of high-risk lots, as in the paper's Fig. 3. These numbers describe the simulation, not real cattle; a yard's own records would replace the history.

**Demo plan** (7 arriving lots, 878 head; current practice = metaphylaxis when the buyer calls a lot high):

| Approach | Lots on metaphylaxis | Expected cost | BRD cases | BRD deaths | Doses |
|---|---|---|---|---|---|
| Current practice | 4 | $36,969 | 41.8 | 6.07 | 610 |
| **PenPoint plan** | 4 | **$34,975** | **39.2** | **5.68** | **569** |
| Metaphylaxis on every lot | 7 | $41,419 | 31.3 | 4.54 | 914 |
| Pull-and-treat on every lot | 0 | $30,158 | 62.6 | 9.08 | 73 |

The plan is cheaper than current practice by $1,994 and lower on cases, deaths and doses, by moving metaphylaxis from a lot the buyer over-called (C100013, risk score 3) to one the buyer under-called (C100009, score 25). Pull-and-treat everywhere is cheapest but has 50% more deaths than current practice, which the no-more-deaths rule forbids; the rule is why four lots keep metaphylaxis though pull-and-treat is cheaper for each on its own. One lot (C100015) is flagged as not confident.

## 5. Limitations
- **The training history is simulated.** Rojas' data are proprietary, so the tree learns from a synthetic yard history calibrated to their published figures. Its accuracy numbers describe that simulation.
- **The Youden cutoff is low** (8.5%) because high-risk lots are rare, so 12 of 18 demo lots are called high risk (4 not sure yet); the risk score and per-lot costs show how strong each call is.
- **Risk-factor adjustment** rests on one observed odds ratio (preconditioning) and four assumptions; each is labelled and editable, and the adjustment assumes the effects combine multiplicatively on the odds.
- **The drug protocol is an example** (tildipirosin for metaphylaxis, florfenicol first-line, enrofloxacin retreatment); the veterinarian sets the real one and product labels govern dose and withdrawal.
- **Eq 3 correction:** we read Rojas' Eq 3 as CS·(MC·m_H·ME − TC); this is our interpretation and is labelled in the app.
- **43 parameters are assumptions,** each labelled in the ledger. Most important: ME (one value; drug class not modelled, O'Connor 2019), the late-metaphylaxis effect, the 2026 drug cost (needs a quote), and the 5% margin on deaths.
- **Rojas' outcome is confounded** by unrecorded metaphylaxis (their p6); ours is not, because the simulation records it.
- **Not decided by the tool:** drug, dose, withdrawal times. Decision support only, subject to veterinary review.

**AI disclosure:** Claude (Anthropic) was used for literature search, code drafting and drafting this brief; the team verified claims, citations and results ([what was checked, by whom]).

## References
Adekunle A, Kaniyamattam K (2026) *Agriculture* 16:311 · Adekunle A, et al. (2026) *Animals* 16:1726 · Rojas HA, et al. (2022) *Pathogens* 11:442 · Weber KMD, et al. (2024) AAEA poster · Cernicchiaro N, et al. (2012) *J Anim Sci* (doi 10.2527/jas.2011-4657) · Horton LM, et al. (2023) *Vet Sci* 10:67 · Baptiste KE, Kyvsgaard NC (2017) *Pathog Dis* · O'Connor AM, et al. (2019) *Anim Health Res Rev* 20:143-162 and 20:163-181 · Mijar S, et al. (2023) *Front Vet Sci* · Werid GM, et al. (2026) *Prev Vet Med* 255:106952 · Wisnieski L, et al. (2021) *AJVR* 82:644 · Heinen L, et al. (2022) *Transl Anim Sci* · Babcock AH, et al. (2010) AABP Proc · Wottlin LR, et al. (2021) *Livest Sci* 248:104488 · Pillen JL, et al. (2016) *Bovine Pract* 50(1) · Toaff-Rosenstein RL, et al. (2016) *J Anim Sci* · Wolfger B, et al. (2015) *Prev Vet Med* 118:285 · Theurer ME, et al. (2015) *J Anim Sci* · Blakebrough-Hall C, et al. (2020) *J Anim Sci* · Horton V, et al. (2025) *Transl Anim Sci* · USDA APHIS NAHMS (2019) Antimicrobial Use and Stewardship on U.S. Feedlots, 2017 · FDA CVM (2025) 2024 Summary Report on Antimicrobials Sold for Food-Producing Animals · Full links and page locations: About the model, Sources in the app and `params/parameters.yaml`.
