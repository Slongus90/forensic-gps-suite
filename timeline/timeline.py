# timeline.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import csv
import json

def parse_dt(dt: str) -> Optional[datetime]:
    if not dt:
        return None
    fmts = [
        "%Y:%m:%d %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y:%m:%d %H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
    ]
    for f in fmts:
        try:
            return datetime.strptime(dt, f)
        except Exception:
            pass
    return None


def build_timeline(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Rekonstruiert Zeitachse aus rows:
    - nur Einträge mit parsebarem datetime
    - sortiert aufsteigend
    - ergänzt "dt_obj" + "dt_iso"
    """
    tl: List[Tuple[datetime, Dict[str, Any]]] = []
    for r in rows:
        d = parse_dt(r.get("datetime", "") or "")
        if not d:
            continue
        nr = dict(r)
        nr["dt_obj"] = d
        # ISO mit Sekunden; TZ falls vorhanden bleibt erhalten
        try:
            nr["dt_iso"] = d.isoformat(timespec="seconds")
        except TypeError:
            nr["dt_iso"] = d.isoformat()
        tl.append((d, nr))

    tl.sort(key=lambda x: x[0])
    out: List[Dict[str, Any]] = []
    for idx, (_, r) in enumerate(tl, 1):
        r["timeline_index"] = idx
        out.append(r)
    return out


def export_timeline_csv(timeline: List[Dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["timeline_index", "dt_iso", "datetime", "lat", "lon", "path", "gmaps", "make", "model", "filetype", "mimetype"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in timeline:
            w.writerow({k: r.get(k, "") for k in fieldnames})


def export_timeline_geojson(timeline: List[Dict[str, Any]], geojson_path: Path) -> None:
    """
    GeoJSON für folium.plugins.TimestampedGeoJson:
    - Punkt-Features mit "times" / "time" via properties["time"]
    """
    geojson_path.parent.mkdir(parents=True, exist_ok=True)

    features = []
    for r in timeline:
        lat = r.get("lat")
        lon = r.get("lon")
        dt_iso = r.get("dt_iso")
        if lat is None or lon is None or not dt_iso:
            continue

        props = {
            "time": dt_iso,
            "popup": str(Path(r.get("path", "")).name),
            "path": r.get("path", ""),
            "datetime": r.get("datetime", ""),
            "gmaps": r.get("gmaps", ""),
            "make": r.get("make", ""),
            "model": r.get("model", ""),
            "timeline_index": r.get("timeline_index", ""),
        }

        features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [float(lon), float(lat)]},
            "properties": props
        })

    fc = {"type": "FeatureCollection", "features": features}
    with open(geojson_path, "w", encoding="utf-8") as f:
        json.dump(fc, f, ensure_ascii=False, indent=2)


def timeline_coords(timeline: List[Dict[str, Any]]) -> List[List[float]]:
    """
    Für PolyLine: [[lat, lon], ...]
    """
    coords: List[List[float]] = []
    for r in timeline:
        lat = r.get("lat")
        lon = r.get("lon")
        if lat is None or lon is None:
            continue
        coords.append([float(lat), float(lon)])
    return coords
