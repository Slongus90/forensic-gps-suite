# timeline/movement_analysis.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime
import math


def _parse_iso(dt_iso: str) -> Optional[datetime]:
    """Parse ISO string (supports trailing 'Z')."""
    if not dt_iso:
        return None
    try:
        return datetime.fromisoformat(dt_iso.replace("Z", "+00:00"))
    except Exception:
        return None


def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _pick_pair_dt(a: Dict[str, Any], b: Dict[str, Any]) -> Tuple[Optional[datetime], Optional[datetime], str]:
    """
    Pick a consistent datetime basis for a pair.

    IMPORTANT: We must never subtract offset-aware and offset-naive datetimes.

    Rules:
      1) If BOTH have dt_utc -> use dt_utc (aware)
      2) Else if BOTH have dt_naive_iso -> use dt_naive_iso (naive)
      3) Else -> return (None, None, "") to indicate "unknown"
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


def analyze_movement(
    timeline: List[Dict[str, Any]],
    stop_speed_kmh: float = 3.0,
    jump_speed_kmh: float = 180.0,
    min_stop_duration_s: int = 180,
) -> List[Dict[str, Any]]:
    """
    Segmentanalyse zwischen aufeinanderfolgenden Timeline-Punkten.

    Output:
      {
        "from_index", "to_index",
        "from_dt", "to_dt",
        "distance_m", "delta_s", "speed_kmh",
        "movement": "stop|move|jump|unknown",
        "dt_basis": "dt_utc|dt_naive_iso|"
      }

    dt Basis (forensisch konservativ):
      - dt_utc nur wenn beide Punkte dt_utc haben
      - dt_naive_iso nur wenn beide Punkte dt_naive_iso haben
      - sonst: unknown (kein Rechnen, kein Crash)
    """
    segs: List[Dict[str, Any]] = []

    for i in range(1, len(timeline)):
        a = timeline[i - 1]
        b = timeline[i]

        lat1, lon1 = a.get("lat"), a.get("lon")
        lat2, lon2 = b.get("lat"), b.get("lon")

        # Strings für Report (unabhängig von dt_basis)
        a_t = a.get("dt_utc") or a.get("dt_naive_iso") or ""
        b_t = b.get("dt_utc") or b.get("dt_naive_iso") or ""

        if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
            segs.append({
                "from_index": a.get("timeline_index"),
                "to_index": b.get("timeline_index"),
                "from_dt": a_t,
                "to_dt": b_t,
                "distance_m": "",
                "delta_s": "",
                "speed_kmh": "",
                "movement": "unknown",
                "dt_basis": "",
            })
            continue

        dist = haversine_m(float(lat1), float(lon1), float(lat2), float(lon2))

        dt_a, dt_b, basis = _pick_pair_dt(a, b)
        if not dt_a or not dt_b:
            segs.append({
                "from_index": a.get("timeline_index"),
                "to_index": b.get("timeline_index"),
                "from_dt": a_t,
                "to_dt": b_t,
                "distance_m": round(dist, 2),
                "delta_s": "",
                "speed_kmh": "",
                "movement": "unknown",
                "dt_basis": "",
            })
            continue

        delta_s = (dt_b - dt_a).total_seconds()
        if delta_s <= 0:
            segs.append({
                "from_index": a.get("timeline_index"),
                "to_index": b.get("timeline_index"),
                "from_dt": a_t,
                "to_dt": b_t,
                "distance_m": round(dist, 2),
                "delta_s": round(delta_s, 3),
                "speed_kmh": "",
                "movement": "unknown",
                "dt_basis": basis,
            })
            continue

        speed_kmh = (dist / delta_s) * 3.6

        movement = "move"
        if speed_kmh >= jump_speed_kmh:
            movement = "jump"
        elif speed_kmh <= stop_speed_kmh and delta_s >= min_stop_duration_s:
            movement = "stop"

        segs.append({
            "from_index": a.get("timeline_index"),
            "to_index": b.get("timeline_index"),
            "from_dt": a_t,
            "to_dt": b_t,
            "distance_m": round(dist, 2),
            "delta_s": round(delta_s, 3),
            "speed_kmh": round(speed_kmh, 3),
            "movement": movement,
            "dt_basis": basis,
        })

    return segs
