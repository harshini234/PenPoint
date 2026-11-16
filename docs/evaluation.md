# Does the tool make better decisions?

Policy backtest on fresh simulated seasons (3 seeds x 600 test lots per scenario, model learns from 800 history lots of the same world). Outcomes are expected values under each lot's TRUE risk. Cost = metaphylaxis + treatment + lost performance + death loss at 2026 prices (parameter ledger). Regret = extra cost vs a perfect-hindsight oracle that knows each lot's true risk and true metaphylaxis effect.

We report decisions, not classifier accuracy: the risk model shares its equations with the generator, so accuracy on synthetic data would be circular. The three stress tests make the simulated world differ from what the model assumes.

## base: World matches the model's assumptions

| Policy | Lots treated | Cases /100 hd | Deaths /100 hd | Doses /head | Cost $/head | Saving vs current $/head | Doses vs current | Regret $/head |
|---|---|---|---|---|---|---|---|---|
| Current practice (buyer's call) | 49% | 5.65 | 0.82 | 0.55 | 43.77 | +0.00 | +0% | 5.41 |
| Metaphylaxis on every lot | 100% | 4.72 | 0.68 | 1.05 | 54.33 | -10.57 | +93% | 15.98 |
| Pull-and-treat only | 0% | 9.30 | 1.35 | 0.11 | 47.93 | -4.16 | -80% | 9.57 |
| Tool: arrival decision | 46% | 5.40 | 0.78 | 0.51 | 41.58 | +2.18 | -6% | 3.23 |
| Tool: arrival + day-5 re-decision | 46% | 5.38 | 0.78 | 0.51 | 41.41 | +2.35 | -7% | 3.06 |
| Perfect hindsight (oracle) | 31% | 5.65 | 0.82 | 0.36 | 38.36 | +5.41 | -33% | 0.00 |

## weaker_meta: Metaphylaxis works worse than assumed (true RR 0.75 vs assumed 0.50)

| Policy | Lots treated | Cases /100 hd | Deaths /100 hd | Doses /head | Cost $/head | Saving vs current $/head | Doses vs current | Regret $/head |
|---|---|---|---|---|---|---|---|---|
| Current practice (buyer's call) | 49% | 7.45 | 1.08 | 0.57 | 52.89 | +0.00 | +0% | 5.17 |
| Metaphylaxis on every lot | 100% | 6.97 | 1.01 | 1.08 | 65.95 | -13.06 | +91% | 18.23 |
| Pull-and-treat only | 0% | 9.30 | 1.35 | 0.11 | 47.93 | +4.96 | -81% | 0.21 |
| Tool: arrival decision | 46% | 7.32 | 1.06 | 0.53 | 51.32 | +1.57 | -6% | 3.60 |
| Tool: arrival + day-5 re-decision | 46% | 7.31 | 1.06 | 0.54 | 51.40 | +1.49 | -5% | 3.68 |
| Perfect hindsight (oracle) | 32% | 7.45 | 1.08 | 0.39 | 47.72 | +5.17 | -31% | 0.00 |

## misspecified: Every assumed risk-effect size off by 0.4-1.6x, 20% more lot-to-lot variation

| Policy | Lots treated | Cases /100 hd | Deaths /100 hd | Doses /head | Cost $/head | Saving vs current $/head | Doses vs current | Regret $/head |
|---|---|---|---|---|---|---|---|---|
| Current practice (buyer's call) | 47% | 5.47 | 0.79 | 0.53 | 42.34 | +0.00 | +0% | 5.48 |
| Metaphylaxis on every lot | 100% | 4.58 | 0.66 | 1.05 | 53.67 | -11.33 | +101% | 16.81 |
| Pull-and-treat only | 0% | 9.03 | 1.31 | 0.10 | 46.57 | -4.23 | -80% | 9.72 |
| Tool: arrival decision | 44% | 5.35 | 0.78 | 0.49 | 40.75 | +1.59 | -7% | 3.90 |
| Tool: arrival + day-5 re-decision | 46% | 5.25 | 0.76 | 0.51 | 40.75 | +1.58 | -4% | 3.90 |
| Perfect hindsight (oracle) | 29% | 5.47 | 0.79 | 0.34 | 36.85 | +5.48 | -35% | 0.00 |

## more_missing: Missing-data rates x1.5

| Policy | Lots treated | Cases /100 hd | Deaths /100 hd | Doses /head | Cost $/head | Saving vs current $/head | Doses vs current | Regret $/head |
|---|---|---|---|---|---|---|---|---|
| Current practice (buyer's call) | 49% | 5.65 | 0.82 | 0.55 | 43.77 | +0.00 | +0% | 5.41 |
| Metaphylaxis on every lot | 100% | 4.72 | 0.68 | 1.05 | 54.33 | -10.57 | +93% | 15.98 |
| Pull-and-treat only | 0% | 9.30 | 1.35 | 0.11 | 47.93 | -4.16 | -80% | 9.57 |
| Tool: arrival decision | 46% | 5.39 | 0.78 | 0.51 | 41.65 | +2.11 | -6% | 3.29 |
| Tool: arrival + day-5 re-decision | 46% | 5.38 | 0.78 | 0.51 | 41.48 | +2.29 | -6% | 3.12 |
| Perfect hindsight (oracle) | 31% | 5.65 | 0.82 | 0.36 | 38.36 | +5.41 | -33% | 0.00 |

## Reading the results

- **Rule: no more deaths than current practice.** The tool is not allowed to trade cattle deaths for money. Every tool policy must plan for at least 5% fewer expected deaths than the buyer's call (the safety margin absorbs model error). Among plans that meet that, it picks the cheapest. The perfect-hindsight row is held to current-practice deaths too (it knows the truth, so it needs no margin).
- Under that rule the tool's arrival decision still closes 40% of the gap between current practice and perfect hindsight, mainly by not mass-treating lots the buyer over-calls as high-risk and treating under-called ones instead.
- In every scenario and every seed, the tool's deaths per 100 head are at or below current practice. The 'welfare_price_per_death' column in results.csv is the price per avoided death the rule implies.
- Without the rule the tool would save more (about $3/head and 20% fewer doses in the base world) but deaths would edge above current practice when assumptions are wrong. We chose not to make that trade.
- Stress tests show how much of the advantage survives when our assumptions are wrong. Where a policy loses to current practice, that is reported, not hidden.
- All worlds are synthetic, calibrated to Rojas 2022 and Cernicchiaro 2011. Real-world validation needs a yard's own records.
