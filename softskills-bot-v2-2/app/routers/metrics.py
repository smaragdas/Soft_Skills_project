# app/routers/metrics.py
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlmodel import Session, select
from sqlalchemy import func
from typing import Dict, List
import numpy as np

from app.core.db import get_session
from app.models.db_models import HumanRating, Interaction, AutoRating

router = APIRouter(prefix="/metrics", tags=["metrics"])


def _nan_to_none(x):
    try:
        if x is None:
            return None
        if isinstance(x, (float, np.floating)):
            if np.isnan(x) or np.isinf(x):
                return None
            return float(x)
        return float(x)
    except Exception:
        return None


def cohen_kappa_weighted_quadratic(a: List[float], b: List[float]) -> float:
    """
    Quadratic-weighted Cohen's kappa σε διακριτές κατηγορίες.
    Χαρτογραφούμε βαθμό 0..10 σε κατηγορία 0..20 (βήμα 0.5 → *2).
    """
    if len(a) == 0 or len(b) == 0:
        return np.nan
    A = np.array([int(round(float(x) * 2)) for x in a], dtype=int)
    B = np.array([int(round(float(x) * 2)) for x in b], dtype=int)

    if A.size == 0 or B.size == 0:
        return np.nan

    a_max = int(A.max()) if A.size > 0 else 0
    b_max = int(B.max()) if B.size > 0 else 0
    n_cat = max(a_max, b_max) + 1
    if n_cat < 2:
        return np.nan

    O = np.zeros((n_cat, n_cat), dtype=float)
    for i, j in zip(A, B):
        # guard για τυχόν αρνητικά/εκτός εύρους λόγω input σφαλμάτων
        if 0 <= i < n_cat and 0 <= j < n_cat:
            O[i, j] += 1.0

    s = O.sum()
    if s == 0:
        return np.nan
    O /= s

    r = O.sum(axis=1, keepdims=True)
    c = O.sum(axis=0, keepdims=True)
    E = r @ c

    # Quadratic weights
    W = np.zeros_like(O)
    if n_cat > 1:
        denom = (n_cat - 1) ** 2
        for i in range(n_cat):
            for j in range(n_cat):
                W[i, j] = ((i - j) ** 2) / denom

    num = (W * O).sum()
    den = (W * E).sum()
    if den == 0:
        return np.nan
    return 1.0 - num / den


def icc2k(scores: np.ndarray) -> float:
    """
    ICC(2,k) — two-way random, consistency, average-measures.
    scores: shape (n_targets, n_raters)
    """
    X = np.array(scores, dtype=float)
    if X.ndim != 2:
        return np.nan
    n, k = X.shape
    if n < 2 or k < 2:
        return np.nan

    # Αντικατάσταση NaNs με mean της στήλης (rater)
    col_means = np.nanmean(X, axis=0)
    inds = np.where(np.isnan(X))
    X[inds] = np.take(col_means, inds[1])

    mean_per_target = X.mean(axis=1, keepdims=True)
    mean_per_rater = X.mean(axis=0, keepdims=True)
    grand_mean = X.mean()

    SST = ((X - grand_mean) ** 2).sum()
    SSR = (n * ((mean_per_rater - grand_mean) ** 2)).sum()
    SSC = (k * ((mean_per_target - grand_mean) ** 2)).sum()
    SSE = SST - SSR - SSC

    MSR = SSR / (k - 1) if k > 1 else np.nan
    MSC = SSC / (n - 1) if n > 1 else np.nan
    MSE = SSE / ((n - 1) * (k - 1)) if n > 1 and k > 1 else np.nan

    if any(np.isnan([MSR, MSC, MSE])):
        return np.nan

    return (MSC - MSE) / (MSC + (MSR - MSE) / n)


@router.get("/reliability")
def reliability(
    category: str = Query(...),
    qtype: str = Query(..., pattern="^(open|mc)$"),
    session: Session = Depends(get_session)
):
    # Human ratings per answer
    rows = session.exec(
        select(HumanRating.answer_id, HumanRating.rater_id, HumanRating.score)
        .join(Interaction, Interaction.answer_id == HumanRating.answer_id)
        .where((Interaction.category == category) & (Interaction.qtype == qtype))
    ).all()

    by_answer: Dict[str, Dict[str, float]] = {}
    for ans_id, rater_id, score in rows:
        try:
            by_answer.setdefault(ans_id, {})[rater_id] = float(score)
        except Exception:
            # skip κακογραμμένες εγγραφές
            continue

    raters = sorted({rid for d in by_answer.values() for rid in d.keys()})

    # Weighted kappa per rater-pair
    pairs_vals = []
    for i in range(len(raters)):
        for j in range(i + 1, len(raters)):
            ra, rb = raters[i], raters[j]
            a, b = [], []
            for _, d in by_answer.items():
                if ra in d and rb in d:
                    a.append(d[ra]); b.append(d[rb])
            if len(a) >= 2:
                kv = cohen_kappa_weighted_quadratic(a, b)
                if not np.isnan(kv):
                    pairs_vals.append(kv)
    kappa_mean = np.nan if len(pairs_vals) == 0 else float(np.nanmean(pairs_vals))

    # ICC(2,k)
    if raters:
        matrix = []
        for _, d in by_answer.items():
            row = [d.get(rid, np.nan) for rid in raters]
            matrix.append(row)
        if len(matrix) >= 2 and len(raters) >= 2:
            icc_val = icc2k(np.array(matrix))
        else:
            icc_val = np.nan
    else:
        icc_val = np.nan

    # Auto vs Human (bias & LoA)
    auto_rows = session.exec(
        select(AutoRating.answer_id, AutoRating.score)
        .join(Interaction, Interaction.answer_id == AutoRating.answer_id)
        .where((Interaction.category == category) & (Interaction.qtype == qtype))
    ).all()
    auto_by_ans = {}
    for aid, s in auto_rows:
        try:
            auto_by_ans[aid] = float(s)
        except Exception:
            continue

    diffs = []
    for ans, d in by_answer.items():
        if ans in auto_by_ans and len(d) > 0:
            try:
                diffs.append(auto_by_ans[ans] - float(np.mean(list(d.values()))))
            except Exception:
                pass

    if len(diffs) > 0:
        m = float(np.mean(diffs))
        sd = float(np.std(diffs, ddof=1)) if len(diffs) > 1 else 0.0
        bias = m
        loa_low = m - 1.96 * sd
        loa_high = m + 1.96 * sd
    else:
        bias = loa_low = loa_high = np.nan

    # Total interactions (count)
    res = session.exec(
        select(func.count()).select_from(Interaction).where(
            (Interaction.category == category) & (Interaction.qtype == qtype)
        )
    )
    try:
        n_total = res.one()
    except Exception:
        first = res.first()
        n_total = int(first) if isinstance(first, (int,)) else 0

    return {
        "filters": {"category": category, "qtype": qtype},
        "n_interactions_total": int(n_total or 0),
        "n_interactions_used": len(by_answer),
        "n_unique_raters": len(raters),
        "kappa": {
            "mean": _nan_to_none(kappa_mean),
            "weights": "quadratic",
            "pairs": len(pairs_vals)
        },
        "icc": {"ICC2k": _nan_to_none(icc_val)},
        "auto_vs_human": {
            "bias": _nan_to_none(bias),
            "loa_low": _nan_to_none(loa_low),
            "loa_high": _nan_to_none(loa_high)
        }
    }
