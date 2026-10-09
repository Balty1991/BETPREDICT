"""LightGBM pe feature-urile pre-meci (+ Dixon-Coles/ELO ca intrări). Un model multiclasă pentru
1X2 și câte unul binar pentru Peste 1.5/2.5/3.5 și GG. Opțional: dacă lightgbm lipsește,
``available()`` e False și Robotul folosește doar Dixon-Coles + ELO."""

from __future__ import annotations

import base64
import gzip
from typing import Dict, Optional

import numpy as np

try:  # pragma: no cover - depinde de mediu
    import lightgbm as lgb
except Exception:  # noqa: BLE001
    lgb = None

TASKS = ("1x2", "O15", "O25", "O35", "BY")

DEFAULT_GBM = {"learning_rate": 0.04, "num_leaves": 24, "min_data_in_leaf": 300, "feature_fraction": 0.7,
               "bagging_fraction": 0.8, "bagging_freq": 1, "lambda_l2": 5.0, "num_rounds": 350, "verbose": -1,
               "num_threads": 0, "seed": 7}


def available() -> bool:
    return lgb is not None


def targets(gh: np.ndarray, ga: np.ndarray) -> Dict[str, np.ndarray]:
    tot = gh + ga
    return {"1x2": np.where(gh > ga, 0, np.where(gh == ga, 1, 2)), "O15": (tot > 1.5).astype(int),
            "O25": (tot > 2.5).astype(int), "O35": (tot > 3.5).astype(int), "BY": ((gh > 0) & (ga > 0)).astype(int)}


def train(X: np.ndarray, y: Dict[str, np.ndarray], params: Optional[Dict] = None, weight: Optional[np.ndarray] = None) -> Dict[str, object]:
    if lgb is None:
        return {}
    p = dict(DEFAULT_GBM)
    p.update(params or {})
    rounds = int(p.pop("num_rounds"))
    out: Dict[str, object] = {}
    for task in TASKS:
        pp = dict(p)
        if task == "1x2":
            pp.update({"objective": "multiclass", "num_class": 3})
        else:
            pp.update({"objective": "binary"})
        ds = lgb.Dataset(X, label=y[task], weight=weight, free_raw_data=True)
        out[task] = lgb.train(pp, ds, num_boost_round=rounds)
    return out


def predict(models: Dict[str, object], X: np.ndarray) -> Dict[str, np.ndarray]:
    if not models:
        return {}
    out: Dict[str, np.ndarray] = {}
    p = models["1x2"].predict(X)
    out["H"], out["D"], out["A"] = p[:, 0], p[:, 1], p[:, 2]
    for k in ("O15", "O25", "O35", "BY"):
        out[k] = models[k].predict(X)
    # coerență: P(peste 1.5) ≥ P(peste 2.5) ≥ P(peste 3.5)
    out["O25"] = np.minimum(out["O25"], out["O15"])
    out["O35"] = np.minimum(out["O35"], out["O25"])
    for k in ("15", "25", "35"):
        out["U" + k] = 1 - out["O" + k]
    out["BN"] = 1 - out["BY"]
    return out


def dumps(models: Dict[str, object]) -> str:
    raw = "\n#----TASK----\n".join(f"{k}\n{m.model_to_string()}" for k, m in models.items())
    return base64.b64encode(gzip.compress(raw.encode("utf-8"), 6)).decode("ascii")


def loads(blob: str) -> Dict[str, object]:
    if lgb is None or not blob:
        return {}
    raw = gzip.decompress(base64.b64decode(blob)).decode("utf-8")
    out = {}
    for part in raw.split("\n#----TASK----\n"):
        k, s = part.split("\n", 1)
        out[k] = lgb.Booster(model_str=s)
    return out
