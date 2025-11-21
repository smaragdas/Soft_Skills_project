# app/routers/rater_calibrate.py
from fastapi import APIRouter, HTTPException
from pathlib import Path
import json, datetime

router = APIRouter(prefix="/rater", tags=["rater-calibration"])
RULES_PATH = Path("app/rules/rules_v1.json")
VERSIONS_DIR = Path("app/rules/versions")
VERSIONS_DIR.mkdir(parents=True, exist_ok=True)

@router.post("/calibrate")
def calibrate_rules(payload: dict):
    if not RULES_PATH.exists():
        raise HTTPException(status_code=404, detail="rules file not found")
    current = json.loads(RULES_PATH.read_text(encoding="utf-8"))

    # merge only known top-level keys
    for k in ("memberships","rules","weights","label_thresholds"):
        if k in payload:
            if isinstance(current.get(k), dict) and isinstance(payload[k], dict):
                current[k].update(payload[k])
            else:
                current[k] = payload[k]

    # version bump: κρατάμε αντίγραφο με timestamp
    ts = datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    (VERSIONS_DIR / f"rules_{ts}.json").write_text(json.dumps(current, indent=2), encoding="utf-8")
    RULES_PATH.write_text(json.dumps(current, indent=2), encoding="utf-8")
    return {"ok": True, "version": ts}
