# timeline/timezone_normalizer.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional, Dict, Any
import re

# akzeptierte Formate (ExifTool typisch: "YYYY:MM:DD HH:MM:SS" optional +TZ)
EXIF_DT_PATTERNS = [
    "%Y:%m:%d %H:%M:%S%z",
    "%Y-%m-%d %H:%M:%S%z",
    "%Y:%m:%d %H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
]

TZ_OFFSET_RE = re.compile(r"([+-]\d{2}):?(\d{2})$")  # +02:00 oder +0200

def _parse_dt(raw: str) -> Optional[datetime]:
    if not raw:
        return None
    raw = raw.strip()
    # ExifTool kann "YYYY:MM:DD HH:MM:SS" liefern, manchmal mit "+02:00"
    # Python strptime kann "%z" mit "+0200" besser als "+02:00" -> normalisieren:
    m = TZ_OFFSET_RE.search(raw)
    if m and ":" in raw:
        raw = raw[:-6] + m.group(1) + m.group(2)  # "+02:00" -> "+0200"

    for fmt in EXIF_DT_PATTERNS:
        try:
            return datetime.strptime(raw, fmt)
        except Exception:
            pass
    return None

def _offset_from_exif(item: Dict[str, Any]) -> Optional[str]:
    # häufige EXIF TZ-Tags:
    for k in ("OffsetTimeOriginal", "OffsetTime", "TimeZone", "TimeZoneOffset"):
        v = item.get(k)
        if v:
            return str(v).strip()
    return None

def normalize_time(
    datetime_raw: str,
    item: Dict[str, Any],
    default_tz: str = "Europe/Berlin",
    assume_if_missing: bool = True,
) -> Dict[str, Any]:
    """
    Normalisiert Zeit:
    - dt_local: ISO string (wenn TZ bekannt)
    - dt_utc:   ISO string (wenn TZ bekannt)
    - timezone_assumed: bool
    - tz_info: z.B. "+0200" oder "unknown"
    - dt_naive_iso: ISO ohne TZ als Fallback
    """
    d = _parse_dt(datetime_raw)
    if not d:
        return {
            "dt_naive_iso": "",
            "dt_local": "",
            "dt_utc": "",
            "tz_info": "unknown",
            "timezone_assumed": False,
        }

    # dt_naive_iso immer befüllen (auch wenn TZ fehlt)
    dt_naive_iso = d.replace(tzinfo=None).isoformat(timespec="seconds")

    # Wenn datetime_raw bereits tz-aware ist:
    if d.tzinfo is not None:
        dt_local = d.isoformat(timespec="seconds")
        dt_utc = d.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        return {
            "dt_naive_iso": dt_naive_iso,
            "dt_local": dt_local,
            "dt_utc": dt_utc,
            "tz_info": "embedded",
            "timezone_assumed": False,
        }

    # Keine TZ in dt -> schauen ob EXIF Offset vorhanden:
    off = _offset_from_exif(item)
    if off:
        # normalize "+02:00" -> "+0200"
        m = TZ_OFFSET_RE.search(off)
        if m:
            off_norm = m.group(1) + m.group(2)
        else:
            off_norm = off.replace(":", "")
        try:
            # Offset in Minuten:
            sign = 1 if off_norm.startswith("+") else -1
            hh = int(off_norm[1:3])
            mm = int(off_norm[3:5]) if len(off_norm) >= 5 else 0
            tz = timezone(sign * (hh * 3600 + mm * 60))
            d_loc = d.replace(tzinfo=tz)
            dt_local = d_loc.isoformat(timespec="seconds")
            dt_utc = d_loc.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
            return {
                "dt_naive_iso": dt_naive_iso,
                "dt_local": dt_local,
                "dt_utc": dt_utc,
                "tz_info": off_norm,
                "timezone_assumed": False,
            }
        except Exception:
            pass

    # Keine TZ verfügbar -> je nach Modus:
    if not assume_if_missing:
        return {
            "dt_naive_iso": dt_naive_iso,
            "dt_local": "",
            "dt_utc": "",
            "tz_info": "unknown",
            "timezone_assumed": False,
        }

    # Heuristik (A-Modus): default_tz annehmen (ohne DST-Logik, bewusst konservativ)
    # -> Wir markieren timezone_assumed=True, dt_utc bleibt leer (weil DST ohne Zoneinfo riskant).
    # Optional: wenn du Zoneinfo willst, sag Bescheid; hier bleibt es forensisch safer.
    return {
        "dt_naive_iso": dt_naive_iso,
        "dt_local": f"{dt_naive_iso}",
        "dt_utc": "",
        "tz_info": f"assumed:{default_tz}",
        "timezone_assumed": True,
    }
