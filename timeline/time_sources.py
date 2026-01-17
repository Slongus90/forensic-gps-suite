# timeline/time_sources.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, Any, Optional, List, Tuple

@dataclass(frozen=True)
class TimeCandidate:
    value: str
    source: str
    confidence: str  # "high" | "medium" | "low"

# Reihenfolge = Priorität (hoch -> niedrig)
DEFAULT_PRIORITY: List[Tuple[str, str]] = [
    ("GPSDateTime", "high"),        # wenn vorhanden (GPS basierte Zeit)
    ("DateTimeOriginal", "high"),   # Foto EXIF
    ("MediaCreateDate", "medium"),  # Video/QuickTime
    ("TrackCreateDate", "medium"),
    ("CreateDate", "low"),
]

def resolve_best_timestamp(item: Dict[str, Any], priority: Optional[List[Tuple[str, str]]] = None) -> Dict[str, Any]:
    """
    Ermittelt den besten Zeitstempel anhand Priorität.
    Gibt zurück:
      {
        "datetime_raw": "...",
        "time_source": "...",
        "time_confidence": "high|medium|low"
      }
    """
    prio = priority or DEFAULT_PRIORITY

    for key, conf in prio:
        v = item.get(key)
        if v:
            return {
                "datetime_raw": str(v),
                "time_source": key,
                "time_confidence": conf,
            }

    return {
        "datetime_raw": "",
        "time_source": "",
        "time_confidence": "low",
    }
