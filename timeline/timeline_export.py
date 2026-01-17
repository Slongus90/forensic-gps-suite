# timeline/timeline_export.py
# -*- coding: utf-8 -*-

from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional
import csv
import json

def export_timeline_csv(timeline: List[Dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "timeline_index",
        "dt_utc",
        "dt_local",
        "dt_naive_iso",
        "datetime_raw",
        "time_source",
        "time_confidence",
        "tz_info",
        "timezone_assumed",
        "lat",
        "lon",
        "alt",
        "path",
        "sha256",
        "gmaps",
        "make",
        "model",
        "filetype",
        "mimetype",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in timeline:
            w.writerow({k: r.get(k, "") for k in fieldnames})

def export_movement_csv(segments: List[Dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["from_index", "to_index", "from_dt", "to_dt", "distance_m", "delta_s", "speed_kmh", "movement"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for s in segments:
            w.writerow({k: s.get(k, "") for k in fieldnames})

def export_gaps_csv(gaps: List[Dict[str, Any]], csv_path: Path) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["after_index", "before_index", "from_dt", "to_dt", "gap_seconds", "gap_level"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for g in gaps:
            w.writerow({k: g.get(k, "") for k in fieldnames})

def export_manifest_csv(rows: List[Dict[str, Any]], csv_path: Path) -> None:
    """
    Minimaler Nachweis-Manifest (C-Modus), pro Datei:
      path, sha256, size_bytes, mtime_iso
    """
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["path", "sha256", "size_bytes", "mtime_iso"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

def export_timeline_geojson(timeline: List[Dict[str, Any]], geojson_path: Path) -> None:
    """
    GeoJSON für folium.plugins.TimestampedGeoJson
    - nutzt dt_utc wenn vorhanden, sonst dt_naive_iso
    """
    geojson_path.parent.mkdir(parents=True, exist_ok=True)
    features = []
    for r in timeline:
        lat = r.get("lat")
        lon = r.get("lon")
        t = r.get("dt_utc") or r.get("dt_naive_iso")
        if lat is None or lon is None or not t:
            continue

        props = {
            "time": t,
            "popup": str(Path(r.get("path", "")).name),
            "path": r.get("path", ""),
            "sha256": r.get("sha256", ""),
            "datetime_raw": r.get("datetime_raw", ""),
            "time_source": r.get("time_source", ""),
            "time_confidence": r.get("time_confidence", ""),
            "tz_info": r.get("tz_info", ""),
            "timezone_assumed": r.get("timezone_assumed", ""),
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
