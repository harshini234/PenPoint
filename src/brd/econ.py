from __future__ import annotations

from dataclasses import dataclass, field, replace

import numpy as np

from . import params as P


@dataclass
class Settings:
    feeder_price_cwt: float = field(default_factory=lambda: P.get("feeder_price_cwt_700_899"))
    light_premium: float = field(default_factory=lambda: P.get("light_calf_premium"))
    meta_cost: float = field(default_factory=lambda: P.get("cost_metaphylaxis_2026"))
    tx_cost: float = field(default_factory=lambda: P.get("cost_treatment_case_2026"))
    perf_loss: float = field(default_factory=lambda: P.get("performance_loss_per_case"))
    feed_cost_day: float = field(default_factory=lambda: P.get("feed_yardage_cost_per_day"))
    rider_wage: float = field(default_factory=lambda: P.get("rider_wage"))
    cfr: float = field(default_factory=lambda: P.get("case_fatality"))
    doses_per_case: float = field(default_factory=lambda: P.get("doses_per_case"))
    meta_rr: float = field(default_factory=lambda: P.get("meta_rr_morbidity"))
    meta_rr_low: float = field(default_factory=lambda: P.entry("meta_rr_morbidity")["low"])
    meta_rr_high: float = field(default_factory=lambda: P.entry("meta_rr_morbidity")["high"])
    arrival_vax_credit: float = 0.0
    stewardship_per_dose: float = 0.0
    decision_day: int = field(default_factory=lambda: int(P.get("decision_day")))
    late_meta_fraction: float = field(default_factory=lambda: P.get("late_meta_effect_fraction"))
    policy: str = "buyer_high"
    welfare_slack: float = 0.0

    def with_(self, **kw) -> "Settings":
        return replace(self, **kw)

    def price_per_lb(self, weight_lb) -> np.ndarray:
        w = np.asarray(weight_lb, float)
        prem = self.light_premium * np.clip((700 - w) / 150, 0, 1)
        return self.feeder_price_cwt / 100 * (1 + prem)

    def death_cost(self, weight_lb) -> np.ndarray:
        return np.asarray(weight_lb, float) * self.price_per_lb(weight_lb) + self.feed_cost_day * P.get("mean_death_day") + self.tx_cost

    def survivor_case_cost(self) -> float:
        return self.tx_cost + self.perf_loss

    def case_cost(self, weight_lb, cfr=None) -> np.ndarray:
        c = self.cfr if cfr is None else cfr
        return (1 - c) * self.survivor_case_cost() + c * self.death_cost(weight_lb)
