# timeline/timeline_builder.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime

def _parse_iso(dt_iso: str) -> Optional[datetime]:
    if not dt_iso:
        return None
    try:
        # "Z" -> "+00:00"
        s = dt_iso.replace("Z", "+00:00")
        return datetime.fromisoformat(s)
    except Exception:
        return None

def build_timeline(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Erwartet Rows mit mindestens:
      - lat, lon
      - dt_utc (optional), dt_naive_iso (optional)
    Sortierung:
      - bevorzugt dt_utc wenn vorhanden
      - sonst dt_naive_iso
      - sonst ganz ans Ende
    Setzt timeline_index (1..N)
    """
    scored: List[Tuple[int, datetime, Dict[str, Any]]] = []
    tail: List[Dict[str, Any]] = []

    for r in rows:
        dt_utc = _parse_iso(r.get("dt_utc", ""))
        dt_nv  = _parse_iso(r.get("dt_naive_iso", ""))
        if dt_utc:
            scored.append((0, dt_utc, r))
        elif dt_nv:
            scored.append((1, dt_nv, r))
        else:
            tail.append(r)

    scored.sort(key=lambda x: (x[0], x[1]))
    out: List[Dict[str, Any]] = []
    idx = 1
    for _, _, r in scored:
        nr = dict(r)
        nr["timeline_index"] = idx
        idx += 1
        out.append(nr)

    for r in tail:
        nr = dict(r)
        nr["timeline_index"] = idx
        idx += 1
        out.append(nr)

    return out
