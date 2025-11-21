# app/core/fuzzy_engine.py
from __future__ import annotations
from typing import Dict, Any, Optional
import json, os, pathlib

DEFAULT_WEIGHTS = {"mcq": 0.5, "text": 0.3,}
CONFIG_PATH = os.getenv("FUZZY_CONFIG", str(pathlib.Path(__file__).resolve().parents[1] / "config" / "fuzzy_rules.json"))

def _load_fuzzy_config(path: Optional[str] = None) -> Dict[str, Any]:
    p = path or CONFIG_PATH
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def _weighted_average(sources: Dict[str, Dict[str, float]], weights: Dict[str, float]) -> Dict[str, Any]:
    # sources: { modality -> {dim -> score[0..1]} }
    dims = {}
    expl = {}
    for modality, dmap in (sources or {}).items():
        for dim, val in (dmap or {}).items():
            dims.setdefault(dim, []).append((modality, float(val), float(weights.get(modality, 0.0))))
    result = {}
    for dim, triples in dims.items():
        num = sum(v*w for _, v, w in triples)
        den = sum(w for _, _, w in triples) or 1.0
        val = num / den
        result[dim] = {"value": val, "sources": {m: v for m, v, _ in triples}}
    return result

def compute_fuzzy(mcq: Optional[Dict[str, float]] = None,
                  text: Optional[Dict[str, float]] = None,
                  audio: Optional[Dict[str, float]] = None,
                  config_path: Optional[str] = None) -> Dict[str, Any]:
    cfg = _load_fuzzy_config(config_path)
    weights = cfg.get("weights", DEFAULT_WEIGHTS)
    sources = {k: v for k, v in {"mcq": mcq, "text": text, "audio": audio}.items() if v}

    # If no rule base, use weighted average fallback
    if not cfg.get("rules"):
        dims = _weighted_average(sources, weights)
        skill_nodes = {k: {"score": v["value"], "explain": "weighted average of modalities"} for k, v in dims.items()}
        final = sum(v["score"] for v in skill_nodes.values()) / (len(skill_nodes) or 1)
        return {"dimensions": dims, "skill_nodes": skill_nodes, "final_score": final}

    # Placeholder simple rule application (min-max across modalities per dim)
    dims = {}
    for dim in set().union(*(d.keys() for d in sources.values())):
        vals = [sources[m].get(dim, 0.0) for m in sources.keys()]
        if cfg.get("mode") == "max":
            agg = max(vals) if vals else 0.0
        elif cfg.get("mode") == "min":
            agg = min(vals) if vals else 0.0
        else:
            agg = sum(vals)/len(vals) if vals else 0.0
        dims[dim] = {"value": agg, "sources": {m: sources[m].get(dim) for m in sources}}
    skill_nodes = {k: {"score": v["value"], "explain": "fuzzy rulebase (placeholder)"} for k, v in dims.items()}
    final = sum(v["score"] for v in skill_nodes.values()) / (len(skill_nodes) or 1)
    return {"dimensions": dims, "skill_nodes": skill_nodes, "final_score": final}