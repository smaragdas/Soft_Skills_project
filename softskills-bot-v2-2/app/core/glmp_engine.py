# app/core/glmp_engine.py
from __future__ import annotations
from typing import Dict, Any, Optional
import json, os, math, pathlib

CONFIG_PATH = os.getenv("GLMP_CONFIG", str(pathlib.Path(__file__).resolve().parents[1] / "config" / "glmp_weights.json"))

def _load_config(path: Optional[str] = None) -> Dict[str, float]:
    p = path or CONFIG_PATH
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Expect: { "communication": 0.2, "teamwork": 0.15, ... }
            return {str(k).lower(): float(v) for k,v in data.items()}
    # default equal weights
    return {}

def compute_glmp(dimensions: Dict[str, float], config_path: Optional[str] = None) -> Dict[str, Any]:
    """Compute a GLM-style weighted sum on normalized [0,1] dimension scores.
    Returns dict with per-dimension contribution and final score in [0,1].
    """
    dims = {str(k).lower(): float(v) for k, v in (dimensions or {}).items() if v is not None}
    weights = _load_config(config_path)

    if not dims:
        return {"dimensions": {}, "final_score": 0.0}

    if not weights:
        # Equal weights if no config provided
        w = 1.0 / len(dims)
        weights = {k: w for k in dims.keys()}

    # Normalize weights to sum 1
    s = sum(abs(v) for v in weights.values()) or 1.0
    weights = {k: abs(v)/s for k,v in weights.items()}

    contributions = {k: dims.get(k, 0.0) * weights.get(k, 0.0) for k in set(dims) | set(weights)}
    final_score = sum(contributions.values())
    return {"weights": weights, "dimensions": dims, "contributions": contributions, "final_score": final_score}