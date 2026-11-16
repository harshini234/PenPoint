from __future__ import annotations

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq

from . import params as P


def run(N: int, beta: float, eQ: float, eV: float = 0.0, dM: float = 0.0, I0: int = 2, days: int = 45,
        sigma: float | None = None, gamma: float | None = None, mu: float = 0.02, gammaQ: float = 0.25):
    sigma = 1 / P.get("seirq_latent_days") if sigma is None else sigma
    gamma = 1 / P.get("seirq_infectious_days") if gamma is None else gamma

    def f_full(t, y):
        S, E, I, R, Q, C = y
        inf = beta * max(1 - eV - eQ, 0.0) * S * I / N
        return [-inf, inf - sigma * E, sigma * E - (gamma + mu + dM) * I, gamma * I + dM * I, eQ * I - gammaQ * Q, sigma * E]

    y0 = [N - I0, 0, I0, 0, 0, I0]
    sol = solve_ivp(f_full, (0, days), y0, t_eval=np.arange(0, days + 1), rtol=1e-6, atol=1e-8)
    S, E, I, R, Q, C = sol.y
    return {"day": sol.t, "S": S, "E": E, "I": I, "R": R, "Q": Q, "cumulative_cases": C}


def beta_for_attack(target_share: float, N: int = 100, eQ: float | None = None, dM: float | None = None) -> float:
    eQ = P.get("seirq_isolation_effect") if eQ is None else eQ
    dM = P.get("seirq_treatment_rate") if dM is None else dM

    def gap(b):
        return run(N, b, eQ, dM=dM)["cumulative_cases"][-1] / N - target_share

    lo, hi = 0.01, 20.0
    if gap(hi) < 0:
        return hi
    if gap(lo) > 0:
        return lo
    return brentq(gap, lo, hi, xtol=1e-4)


def overflow_extra_cases_per_case() -> float:
    tau = P.get("transmission_share")
    return tau / (1 - tau) * P.get("seirq_isolation_effect")
