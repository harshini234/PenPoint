from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]
PARAMS_PATH = ROOT / "params" / "parameters.yaml"
YARDS_PATH = ROOT / "params" / "yards.yaml"


CALIBRATED_PATH = ROOT / "params" / "calibrated.yaml"


@lru_cache(maxsize=1)
def load_ledger(path: str | None = None) -> dict:
    with open(path or PARAMS_PATH, encoding="utf-8") as f:
        led = yaml.safe_load(f)
    if CALIBRATED_PATH.exists():
        with open(CALIBRATED_PATH, encoding="utf-8") as f:
            cal = (yaml.safe_load(f) or {}).get("values", {})
        for p in led["parameters"]:
            if p.get("tag") == "Calibrated" and p["id"] in cal:
                p["value"] = cal[p["id"]]
    return led


def reload() -> None:
    load_ledger.cache_clear()
    load_yards.cache_clear()


def _index() -> dict:
    return {p["id"]: p for p in load_ledger()["parameters"]}


_OVERRIDES: dict = {}


def set_override(pid: str, value) -> None:
    _OVERRIDES[pid] = value


def clear_overrides() -> None:
    _OVERRIDES.clear()


def get(pid: str):
    if pid in _OVERRIDES:
        return _OVERRIDES[pid]
    idx = _index()
    if pid not in idx:
        raise KeyError(f"Unknown parameter id: {pid}")
    v = idx[pid]["value"]
    if v is None:
        raise ValueError(f"Parameter {pid} has no value yet (tag={idx[pid]['tag']}). Run scripts/calibrate.py.")
    return v


def entry(pid: str) -> dict:
    return _index()[pid]


def ledger_frame() -> pd.DataFrame:
    led = load_ledger()
    src = led["sources"]
    rows = []
    for p in led["parameters"]:
        s = src.get(p.get("source", ""), {})
        rows.append(
            {
                "id": p["id"],
                "group": p.get("group"),
                "description": p.get("description"),
                "value": p.get("value") if not isinstance(p.get("value"), dict) else "see YAML",
                "low": p.get("low"),
                "high": p.get("high"),
                "unit": p.get("unit"),
                "tag": p.get("tag"),
                "source_id": p.get("source"),
                "source": s.get("cite", ""),
                "link": s.get("link", ""),
                "location": p.get("location"),
                "used_in": ", ".join(p.get("used_in", [])),
                "verified": p.get("verified", False),
                "verified_by": p.get("verified_by", ""),
                "notes": p.get("notes", ""),
            }
        )
    return pd.DataFrame(rows)


@lru_cache(maxsize=1)
def load_yards() -> dict:
    with open(YARDS_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f)
