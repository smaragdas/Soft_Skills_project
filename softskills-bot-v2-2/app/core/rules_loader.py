# app/core/rules_loader.py
from __future__ import annotations
import json, os
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException

RULES_PATH = Path("app/rules/rules_v2.json")

def _load_from_env() -> Tuple[dict | None, str]:
    raw = os.getenv("RULES_OVERRIDE_JSON")
    if not raw:
        return None, "none"
    try:
        data = json.loads(raw)
        return data, "env"
    except Exception as e:
        print(f"[rules] RULES_OVERRIDE_JSON invalid JSON: {e}")
        return None, "env_invalid"

def _load_from_file() -> Tuple[dict, str]:
    if not RULES_PATH.exists():
        raise HTTPException(status_code=404, detail="rules file not found")
    try:
        data = json.loads(RULES_PATH.read_text(encoding="utf-8"))
        return data, f"file:{RULES_PATH}"
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"failed to read rules file: {e}")

def load_rules() -> Tuple[dict, str]:
    data, src = _load_from_env()
    if data is not None:
        print("[rules] loaded from ENV RULES_OVERRIDE_JSON")
        return data, src
    data, src = _load_from_file()
    print(f"[rules] loaded from {src}")
    return data, src
