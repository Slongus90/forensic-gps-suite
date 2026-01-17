#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import csv
import json
import math
import logging
import sqlite3
import argparse
import subprocess
import base64
import hashlib
from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- Timeline Module (A + optional C) ---
try:
    from timeline import (
        resolve_best_timestamp,
        normalize_time,
        build_timeline,
        analyze_movement,
        detect_gaps,
        export_timeline_csv,
        export_timeline_geojson,
        export_gaps_csv,
        export_movement_csv,
        export_manifest_csv,
    )
    HAS_TIMELINE = True
except Exception:
    HAS_TIMELINE = False

# --- OPTIONAL: tqdm ---
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

# --- OPTIONAL: folium ---
try:
    import folium
    from folium.plugins import HeatMap, MarkerCluster
    try:
        from folium.plugins import TimestampedGeoJson
        HAS_TIMESTAMPED = True
    except Exception:
        HAS_TIMESTAMPED = False
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False
    HAS_TIMESTAMPED = False

# --- OPTIONAL: psutil ---
try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v"}

DEFAULT_CONFIG = {
    "chunk_size": 50,
    "max_workers": os.cpu_count() or 4,
    "dup_dist_m": 5.0,
    "dup_time_s": 10,
    "thumbnail_size": 200,
}

def setup_logging(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "forensic_audit.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.FileHandler(log_file, encoding="utf-8"), logging.StreamHandler(sys.stdout)],
    )
    return logging.getLogger("GPSForensic")

def get_mem_usage():
    if HAS_PSUTIL:
        process = psutil.Process(os.getpid())
        return f"{process.memory_info().rss / 1024 / 1024:.2f} MB"
    return "N/A"

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

def haversine_m(lat1, lon1, lat2, lon2) -> float:
    R = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlon / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def sha256_file(path: Path, bufsize: int = 1024 * 1024) -> str:
    h = hashlib.sha256()
    try:
        with open(path, "rb") as f:
            while True:
                b = f.read(bufsize)
                if not b:
                    break
                h.update(b)
        return h.hexdigest()
    except Exception:
        return ""

def get_thumbnail_base64(file_path: str) -> str:
    try:
        cmd = ["exiftool", "-b", "-ThumbnailImage", file_path]
        img_data = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        if img_data:
            return base64.b64encode(img_data).decode("utf-8")
    except Exception:
        pass
    return ""

def run_exiftool_batch(paths: List[str]) -> List[Dict[str, Any]]:
    # -n: numerisch (GPS)
    # Ergänzt TZ- und Zeitquellenfelder, damit A sauber arbeitet
    cmd = [
        "exiftool", "-n", "-json", "-q",
        "-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
        "-GPSDateTime", "-GPSDateStamp", "-GPSTimeStamp",
        "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate", "-TrackCreateDate",
        "-OffsetTimeOriginal", "-OffsetTime", "-TimeZone", "-TimeZoneOffset",
        "-Make", "-Model", "-FileType", "-MIMEType",
        "-FileName", "-Directory",
    ] + paths

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return json.loads(proc.stdout) if proc.stdout.strip() else []
    except Exception:
        return []

def process_batch(file_batch: List[Path], make_thumbs: bool) -> List[Dict[str, Any]]:
    results: List[Dict[str, Any]] = []
    raw_data = run_exiftool_batch([str(p) for p in file_batch])

    for item in raw_data:
        lat = item.get("GPSLatitude")
        lon = item.get("GPSLongitude")
        if lat is None or lon is None:
            continue

        directory = item.get("Directory", "") or ""
        filename = item.get("FileName", "") or ""
        path = str(Path(directory) / filename)

        results.append({
            "path": path,
            "lat": float(lat),
            "lon": float(lon),
            "alt": item.get("GPSAltitude", ""),
            "gmaps": f"https://www.google.com/maps?q={lat},{lon}",
            "make": str(item.get("Make", "") or ""),
            "model": str(item.get("Model", "") or ""),
            "filetype": str(item.get("FileType", "") or ""),
            "mimetype": str(item.get("MIMEType", "") or ""),
            # Zeit-Felder (roh) fürs Timeline-Modul:
            "GPSDateTime": item.get("GPSDateTime", ""),
            "DateTimeOriginal": item.get("DateTimeOriginal", ""),
            "MediaCreateDate": item.get("MediaCreateDate", ""),
            "TrackCreateDate": item.get("TrackCreateDate", ""),
            "CreateDate": item.get("CreateDate", ""),
            "OffsetTimeOriginal": item.get("OffsetTimeOriginal", ""),
            "OffsetTime": item.get("OffsetTime", ""),
            "TimeZone": item.get("TimeZone", ""),
            "TimeZoneOffset": item.get("TimeZoneOffset", ""),
            # Map:
            "thumb": get_thumbnail_base64(path) if (HAS_FOLIUM and make_thumbs) else "",
        })

    return results

def detect_duplicates(rows: List[Dict[str, Any]], dist_m: float, time_s: int) -> List[Dict[str, Any]]:
    enriched: List[Tuple[datetime, Dict[str, Any]]] = []
    for r in rows:
        # hier bleibt "datetime_raw" ggf. später; wir nutzen best-effort auf CreateDate/DateTimeOriginal
        candidate = r.get("DateTimeOriginal") or r.get("CreateDate") or ""
        d = parse_dt(str(candidate))
        if d:
            enriched.append((d, r))

    enriched.sort(key=lambda x: x[0])
    clusters: List[List[Tuple[datetime, Dict[str, Any]]]] = []
    current: List[Tuple[datetime, Dict[str, Any]]] = []

    for dt, row in enriched:
        if not current:
            current.append((dt, row))
            continue

        prev_dt, prev_row = current[-1]
        dt_diff = abs((dt - prev_dt).total_seconds())
        dist = haversine_m(prev_row["lat"], prev_row["lon"], row["lat"], row["lon"])

        if dt_diff <= time_s and dist <= dist_m:
            current.append((dt, row))
        else:
            if len(current) > 1:
                clusters.append(list(current))
            current = [(dt, row)]

    if len(current) > 1:
        clusters.append(list(current))

    dup_rows: List[Dict[str, Any]] = []
    for cid, cl in enumerate(clusters, 1):
        for _, r in cl:
            nr = r.copy()
            nr["cluster_id"] = cid
            nr["cluster_size"] = len(cl)
            dup_rows.append(nr)

    return dup_rows

def export_main_csv(rows: List[Dict[str, Any]], csv_path: Path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["path", "lat", "lon", "alt", "gmaps", "make", "model", "filetype", "mimetype"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fieldnames})

def export_monthly_csv(rows: List[Dict[str, Any]], out_dir: Path):
    base = out_dir / "csv"
    base.mkdir(parents=True, exist_ok=True)

    buckets: Dict[str, List[Dict[str, Any]]] = {}
    for r in rows:
        candidate = r.get("DateTimeOriginal") or r.get("CreateDate") or ""
        d = parse_dt(str(candidate))
        if not d:
            key = "unknown/unknown.csv"
        else:
            key = f"{d.year}/{d.year}-{d.month:02d}.csv"
        buckets.setdefault(key, []).append(r)

    for key, items in buckets.items():
        target = base / key
        target.parent.mkdir(parents=True, exist_ok=True)
        export_main_csv(items, target)

def export_sqlite(rows: List[Dict[str, Any]], db_path: Path):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS evidence
           (id INTEGER PRIMARY KEY, path TEXT, sha256 TEXT, dt_utc TEXT, dt_naive TEXT,
            datetime_raw TEXT, time_source TEXT, time_confidence TEXT, tz_info TEXT, timezone_assumed INTEGER,
            make TEXT, model TEXT, filetype TEXT, mimetype TEXT,
            lat REAL, lon REAL, alt TEXT, maps_url TEXT)"""
    )
    data = []
    for r in rows:
        data.append((
            None,
            r.get("path", ""),
            r.get("sha256", ""),
            r.get("dt_utc", ""),
            r.get("dt_naive_iso", ""),
            r.get("datetime_raw", ""),
            r.get("time_source", ""),
            r.get("time_confidence", ""),
            r.get("tz_info", ""),
            1 if str(r.get("timezone_assumed", "")).lower() in ("true", "1", "yes") else 0,
            r.get("make", ""),
            r.get("model", ""),
            r.get("filetype", ""),
            r.get("mimetype", ""),
            r.get("lat", ""),
            r.get("lon", ""),
            str(r.get("alt", "")),
            r.get("gmaps", ""),
        ))
    # Wichtig: Die Tabelle hat 18 Spalten -> exakt 18 Platzhalter.
    cur.executemany("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", data)
    conn.commit()
    conn.close()

def export_kml(rows: List[Dict[str, Any]], kml_path: Path):
    kml_path.parent.mkdir(parents=True, exist_ok=True)
    header = '<?xml version="1.0" encoding="UTF-8"?>' \
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Forensic Export</name>'
    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(header)
        for r in rows:
            name = xml_escape(Path(r.get("path", "")).name)
            desc = xml_escape(
                f"dt_utc: {r.get('dt_utc','')}\n"
                f"dt_naive: {r.get('dt_naive_iso','')}\n"
                f"raw: {r.get('datetime_raw','')} ({r.get('time_source','')}/{r.get('time_confidence','')})\n"
                f"tz: {r.get('tz_info','')} assumed={r.get('timezone_assumed','')}\n"
                f"sha256: {r.get('sha256','')}\n"
                f"device: {r.get('make','')} {r.get('model','')}\n"
                f"url: {r.get('gmaps','')}\n"
                f"path: {r.get('path','')}"
            )
            f.write(f'<Placemark><name>{name}</name>')
            f.write(f"<description>{desc}</description>")
            f.write(f'<Point><coordinates>{r["lon"]},{r["lat"]},0</coordinates></Point></Placemark>')
        f.write("</Document></kml>")

def export_duplicates_csv(dups: List[Dict[str, Any]], csv_path: Path):
    if not dups:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["cluster_id", "cluster_size", "path", "lat", "lon", "alt", "gmaps", "make", "model", "filetype", "mimetype"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in dups:
            w.writerow({k: r.get(k, "") for k in fieldnames})

def export_interactive_map(
    rows: List[Dict[str, Any]],
    html_path: Path,
    timeline: Optional[List[Dict[str, Any]]] = None,
    timeline_geojson_path: Optional[Path] = None,
    segments: Optional[List[Dict[str, Any]]] = None,
    gaps: Optional[List[Dict[str, Any]]] = None,
):
    if not HAS_FOLIUM or not rows:
        return

    html_path.parent.mkdir(parents=True, exist_ok=True)

    m = folium.Map(location=[rows[0]["lat"], rows[0]["lon"]], zoom_start=4, tiles="cartodbpositron")

    marker_cluster = MarkerCluster(name="Beweismittel").add_to(m)
    HeatMap([[r["lat"], r["lon"]] for r in rows], name="Heatmap").add_to(m)

    for r in rows:
        thumb_html = ""
        if r.get("thumb"):
            thumb_html = f'<img src="data:image/jpeg;base64,{r["thumb"]}" style="width:100%;">'

        popup_content = (
            f'<div style="width:260px">'
            f"<b>{xml_escape(Path(r.get('path','')).name)}</b><br>"
            f"dt_utc: {xml_escape(str(r.get('dt_utc','')))}<br>"
            f"dt_naive: {xml_escape(str(r.get('dt_naive_iso','')))}<br>"
            f"raw: {xml_escape(str(r.get('datetime_raw','')))}<br>"
            f"src: {xml_escape(str(r.get('time_source','')))} / {xml_escape(str(r.get('time_confidence','')))}<br>"
            f"tz: {xml_escape(str(r.get('tz_info','')))} (assumed={xml_escape(str(r.get('timezone_assumed','')))})<br>"
            f"sha256: <code>{xml_escape(str(r.get('sha256','')))}</code><br>"
            f"<hr>{thumb_html}"
            f'<br><a href="{r.get("gmaps","")}" target="_blank">Google Maps</a>'
            f"</div>"
        )

        folium.Marker(
            [r["lat"], r["lon"]],
            popup=folium.Popup(popup_content, max_width=320),
        ).add_to(marker_cluster)

    # --- Zeitachse: Route (segmentiert nach Movement) ---
    if timeline and segments:
        seg_layer = folium.FeatureGroup(name="Zeitachse (Segmente)", show=True)
        seg_layer.add_to(m)

        # Farbwahl bewusst simpel (A): move=green, stop=blue, jump=red, unknown=gray
        color_map = {"move": "green", "stop": "blue", "jump": "red", "unknown": "gray"}

        # Index->Koordinaten
        idx_to_coord = {}
        for r in timeline:
            if r.get("lat") is None or r.get("lon") is None:
                continue
            idx_to_coord[int(r["timeline_index"])] = (float(r["lat"]), float(r["lon"]))

        for s in segments:
            try:
                a = int(s["from_index"])
                b = int(s["to_index"])
            except Exception:
                continue
            if a not in idx_to_coord or b not in idx_to_coord:
                continue

            movement = s.get("movement", "unknown")
            col = color_map.get(movement, "gray")
            tooltip = f"{movement} | {s.get('distance_m','')} m | {s.get('speed_kmh','')} km/h | Δt={s.get('delta_s','')}s"
            folium.PolyLine(
                [idx_to_coord[a], idx_to_coord[b]],
                weight=4,
                opacity=0.85,
                color=col,
                tooltip=tooltip,
            ).add_to(seg_layer)

    # --- Gaps Layer ---
    if gaps:
        gap_layer = folium.FeatureGroup(name="Zeitlücken (Gaps)", show=False)
        gap_layer.add_to(m)
        # wir markieren den Punkt NACH der Lücke, falls vorhanden
        idx_to_row = {int(r["timeline_index"]): r for r in timeline} if timeline else {}
        for g in gaps:
            bi = g.get("before_index")
            if bi is None:
                continue
            try:
                bi = int(bi)
            except Exception:
                continue
            r = idx_to_row.get(bi)
            if not r:
                continue
            txt = f"{g.get('gap_level','gap')} | {g.get('gap_seconds','')}s\n{g.get('from_dt','')} -> {g.get('to_dt','')}"
            folium.CircleMarker(
                location=[r["lat"], r["lon"]],
                radius=7,
                color="orange",
                fill=True,
                fill_opacity=0.8,
                tooltip=txt,
            ).add_to(gap_layer)

    # --- Playback ---
    if HAS_TIMESTAMPED and timeline_geojson_path and timeline_geojson_path.exists():
        try:
            data = json.loads(timeline_geojson_path.read_text(encoding="utf-8"))
            TimestampedGeoJson(
                data,
                transition_time=200,
                period="PT1H",
                add_last_point=True,
                auto_play=False,
                loop=False,
                max_speed=5,
                loop_button=True,
                date_options="YYYY-MM-DD HH:mm:ss",
                time_slider_drag_update=True,
                name="Zeitachse (Playback)",
            ).add_to(m)
        except Exception:
            pass

    folium.LayerControl().add_to(m)
    m.save(str(html_path))

def main():
    ap = argparse.ArgumentParser(description="High-Performance Forensic GPS Suite (alles unter --od)")
    ap.add_argument("--sd", required=True, help="Scan Directory (Root)")
    ap.add_argument("--od", required=True, help="Output Directory (ALLES landet hier drin)")
    ap.add_argument("--oc", default=None, help="Optional: Haupt-CSV Pfad/Name (Default: <od>/test.csv)")
    ap.add_argument("--threads", type=int, default=DEFAULT_CONFIG["max_workers"], help="Worker Prozesse")
    ap.add_argument("--chunk-size", type=int, default=DEFAULT_CONFIG["chunk_size"], help="Batchgröße für ExifTool")
    ap.add_argument("--dup-dist", type=float, default=DEFAULT_CONFIG["dup_dist_m"], help="Duplikat: Distanz (m)")
    ap.add_argument("--dup-time", type=int, default=DEFAULT_CONFIG["dup_time_s"], help="Duplikat: Zeit (s)")
    ap.add_argument("--no-monthly", action="store_true", help="Keine Monats-CSVs erzeugen")

    # A: erweiterte Analyseparameter
    ap.add_argument("--gap-s", type=int, default=30*60, help="Gap Schwelle in Sekunden")
    ap.add_argument("--major-gap-s", type=int, default=6*60*60, help="Major Gap Schwelle in Sekunden")
    ap.add_argument("--critical-gap-s", type=int, default=24*60*60, help="Critical Gap Schwelle in Sekunden")
    ap.add_argument("--stop-speed-kmh", type=float, default=3.0, help="Stop wenn <= speed und delta>=min-stop")
    ap.add_argument("--jump-speed-kmh", type=float, default=180.0, help="Jump wenn >= speed")
    ap.add_argument("--min-stop-s", type=int, default=180, help="Min Stopdauer in Sekunden")
    ap.add_argument("--tz", default="Europe/Berlin", help="Default Zeitzone Label (nur wenn Annahmen erlaubt)")

    # C: court mode (keine Zeit-Annahmen)
    ap.add_argument("--court", action="store_true", help="Court-Mode: keine Zeit-Annahmen (keine impliziten TZ-Annahmen)")

    # Beweissicherung (opt-in): Datei-Hashes + Manifest nur wenn explizit gewünscht.
    ap.add_argument("--sha256", action="store_true", help="SHA256 + evidence_manifest.csv berechnen (kann dauern)")

    args = ap.parse_args()

    src = Path(args.sd).expanduser()
    dst = Path(args.od).expanduser()
    if not src.exists():
        print(f"Error: {src} not found")
        sys.exit(1)

    dst.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(dst)

    out_csv = Path(args.oc).expanduser() if args.oc else (dst / "test.csv")
    out_sqlite = dst / "forensic_data.sqlite"
    out_kml = dst / "locations.kml"
    out_html = dst / "interactive_map.html"
    out_dups = dst / "duplicates_report.csv"

    # Timeline Outputs
    out_timeline_csv = dst / "timeline.csv"
    out_timeline_geojson = dst / "timeline.geojson"
    out_gaps_csv = dst / "gaps_report.csv"
    out_movement_csv = dst / "movement_report.csv"
    out_manifest_csv = dst / "evidence_manifest.csv"

    logger.info(f"Scan: {src}")
    logger.info(f"Output Dir: {dst}")
    logger.info(f"Main CSV: {out_csv}")
    logger.info(f"Threads: {args.threads} | Chunk: {args.chunk_size} | Folium: {HAS_FOLIUM} | TimelineMod: {HAS_TIMELINE}")
    logger.info(f"Court mode: {args.court}")

    exts = PHOTO_EXTS | VIDEO_EXTS
    files = [Path(r) / f for r, _, fs in os.walk(src) for f in fs if Path(f).suffix.lower() in exts]
    if not files:
        logger.warning("Keine Medien gefunden.")
        return

    chunks = [files[i:i + max(1, int(args.chunk_size))] for i in range(0, len(files), max(1, int(args.chunk_size)))]
    all_rows: List[Dict[str, Any]] = []

    make_thumbs = (not args.court)  # C: keine Thumbs (weniger Daten, weniger „Interpretation“)
    with ProcessPoolExecutor(max_workers=int(args.threads)) as executor:
        futures = {executor.submit(process_batch, c, make_thumbs): c for c in chunks}
        pbar = tqdm(total=len(files), desc="Analysiere EXIF") if HAS_TQDM else None

        for fut in as_completed(futures):
            batch = futures[fut]
            try:
                res = fut.result()
            except Exception as e:
                logger.error(f"Batch-Fehler: {e}")
                res = []
            all_rows.extend(res)
            if pbar:
                pbar.update(len(batch))

        if pbar:
            pbar.close()

    if not all_rows:
        logger.warning("Keine GPS-Daten in den Dateien gefunden.")
        return

    # Hashes + Manifest: NUR wenn explizit aktiviert (opt-in)
    if args.sha256:
        logger.info("Berechne SHA256 (explizit via --sha256 aktiviert; kann dauern)...")
        manifest_rows: List[Dict[str, Any]] = []
        for r in all_rows:
            p = Path(r["path"])
            r["sha256"] = sha256_file(p)
            try:
                st = p.stat()
                manifest_rows.append({
                    "path": str(p),
                    "sha256": r["sha256"],
                    "size_bytes": st.st_size,
                    "mtime_iso": datetime.fromtimestamp(st.st_mtime).isoformat(timespec="seconds"),
                })
            except Exception:
                manifest_rows.append({
                    "path": str(p),
                    "sha256": r["sha256"],
                    "size_bytes": "",
                    "mtime_iso": "",
                })
        export_manifest_csv(manifest_rows, out_manifest_csv)
    else:
        logger.info("SHA256/Manifest übersprungen (nur mit --sha256 aktiv)")
        for r in all_rows:
            r["sha256"] = ""

    # Timeline Enrichment (A + C)
    if HAS_TIMELINE:
        enriched_rows: List[Dict[str, Any]] = []
        for r in all_rows:
            # 1) beste Zeitquelle ermitteln
            tsel = resolve_best_timestamp(r)
            r["datetime_raw"] = tsel["datetime_raw"]
            r["time_source"] = tsel["time_source"]
            r["time_confidence"] = tsel["time_confidence"]

            # 2) Zeitzonen normalisieren
            norm = normalize_time(
                datetime_raw=r.get("datetime_raw", ""),
                item=r,
                default_tz=args.tz,
                assume_if_missing=(not args.court),  # C: keine Annahmen
            )
            r.update(norm)

            enriched_rows.append(r)

        # Zeitachse sortieren/indexieren
        timeline = build_timeline(enriched_rows)

        # Movement + Gaps (C erlaubt, aber nur wenn Zeitstempel vorhanden)
        segments = analyze_movement(
            timeline,
            stop_speed_kmh=float(args.stop_speed_kmh),
            jump_speed_kmh=float(args.jump_speed_kmh),
            min_stop_duration_s=int(args.min_stop_s),
        )
        gaps = detect_gaps(
            timeline,
            gap_s=int(args.gap_s),
            major_gap_s=int(args.major_gap_s),
            critical_gap_s=int(args.critical_gap_s),
        )

        export_timeline_csv(timeline, out_timeline_csv)
        export_movement_csv(segments, out_movement_csv)
        export_gaps_csv(gaps, out_gaps_csv)

        # GeoJSON fürs Playback (in C okay, ist reine Darstellung)
        export_timeline_geojson(timeline, out_timeline_geojson)

        logger.info(f"Zeitachse: {len(timeline)} | Segmente: {len(segments)} | Gaps: {len(gaps)}")
    else:
        logger.warning("Timeline-Module fehlen/Importfehler -> keine Zeitachsen-Exports.")
        timeline = None
        segments = None
        gaps = None
        enriched_rows = all_rows

    # Standard Exporte
    export_main_csv(all_rows, out_csv)
    export_sqlite(enriched_rows if HAS_TIMELINE else all_rows, out_sqlite)
    export_kml(enriched_rows if HAS_TIMELINE else all_rows, out_kml)

    # Map (C: reduziert, A: voll)
    if HAS_FOLIUM:
        export_interactive_map(
            enriched_rows if HAS_TIMELINE else all_rows,
            out_html,
            timeline=timeline if HAS_TIMELINE else None,
            timeline_geojson_path=out_timeline_geojson if HAS_TIMELINE else None,
            segments=(segments if (HAS_TIMELINE and not args.court) else None),  # C: keine segmentfarben nötig
            gaps=(gaps if (HAS_TIMELINE and not args.court) else None),
        )
    else:
        logger.warning("Folium nicht installiert -> interactive_map.html wird nicht erzeugt.")

    if not args.no_monthly:
        export_monthly_csv(all_rows, dst)

    dups = detect_duplicates(all_rows, float(args.dup_dist), int(args.dup_time))
    if dups:
        export_duplicates_csv(dups, out_dups)
        logger.info(f"Duplikate/Events: {len(dups)} (Report: {out_dups})")

    logger.info(f"Fertig. Memory Usage: {get_mem_usage()}")
    logger.info(f"Outputs unter: {dst}")

if __name__ == "__main__":
    main()
