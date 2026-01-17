# timeline/gap_detection.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime


def _parse_iso(dt_iso: str) -> Optional[datetime]:
    if not dt_iso:
        return None
    try:
        return datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    except Exception:
        return None


def _pick_pair_dt(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime], str]:
    """
    Konsistente Basis für zwei Punkte:
      1) dt_utc nur wenn beide vorhanden
      2) dt_naive_iso nur wenn beide vorhanden
      3) sonst None/None
    """
    a_utc = _parse_iso(a.get("dt_utc", ""))
    b_utc = _parse_iso(b.get("dt_utc", ""))
    if a_utc is not None and b_utc is not None:
        return a_utc, b_utc, "dt_utc"

    a_nv = _parse_iso(a.get("dt_naive_iso", ""))
    b_nv = _parse_iso(b.get("dt_naive_iso", ""))
    if a_nv is not None and b_nv is not None:
        return a_nv, b_nv, "dt_naive_iso"

    return None, None, ""


def detect_gaps(
    timeline: List[Dict[str, Any]],
    gap_s: int = 30 * 60,
    major_gap_s: int = 6 * 60 * 60,
    critical_gap_s: int = 24 * 60 * 60,
) -> List[Dict[str, Any]]:
    """
    Liefert Gap-Ereignisse zwischen Punkten, wenn Zeitdifferenz > threshold.
    Forensisch konservativ: keine Mischrechnung aware/naive.
    """
    gaps: List[Dict[str, Any]] = []

    for i in range(1, len(timeline)):
        a = timeline[i - 1]
        b = timeline[i]

        dt_a, dt_b, basis = _pick_pair_dt(a, b)
        if not dt_a or not dt_b:
            continue

        delta = (dt_b - dt_a).total_seconds()
        if delta <= gap_s:
            continue

        level = "gap"
        if delta >= critical_gap_s:
            level = "critical"
        elif delta >= major_gap_s:
            level = "major"

        gaps.append({
            "after_index": a.get("timeline_index"),
            "before_index": b.get("timeline_index"),
            "from_dt": a.get("dt_utc") or a.get("dt_naive_iso") or "",
            "to_dt": b.get("dt_utc") or b.get("dt_naive_iso") or "",
            "gap_seconds": int(delta),
            "gap_level": level,
            "dt_basis": basis,
        })

    return gaps
