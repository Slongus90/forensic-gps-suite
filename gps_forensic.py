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
from pathlib import Path
from datetime import datetime
from xml.sax.saxutils import escape as xml_escape
from typing import List, Dict, Any, Optional, Tuple
from concurrent.futures import ProcessPoolExecutor, as_completed

# --- OPTIONALE MODULE ---
try:
    from tqdm import tqdm
    HAS_TQDM = True
except ImportError:
    HAS_TQDM = False

try:
    import folium
    from folium.plugins import HeatMap, MarkerCluster
    HAS_FOLIUM = True
except ImportError:
    HAS_FOLIUM = False

try:
    import psutil
    HAS_PSUTIL = True
except ImportError:
    HAS_PSUTIL = False


# --- KONFIGURATION ---
PHOTO_EXTS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".webp", ".heic", ".heif"}
VIDEO_EXTS = {".mov", ".mp4", ".m4v"}

DEFAULT_CONFIG = {
    "chunk_size": 50,
    "max_workers": os.cpu_count() or 4,
    "dup_dist_m": 5.0,
    "dup_time_s": 10,
    "thumbnail_size": 200,
}

# --- LOGGING & UTILS ---
def setup_logging(out_dir: Path):
    out_dir.mkdir(parents=True, exist_ok=True)
    log_file = out_dir / "forensic_audit.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
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


def pick_best_datetime(item: Dict[str, Any]) -> str:
    for k in ("DateTimeOriginal", "CreateDate", "MediaCreateDate", "TrackCreateDate"):
        v = item.get(k)
        if v:
            return str(v)
    return ""


# --- CORE PROCESSING ---
def get_thumbnail_base64(file_path: str) -> str:
    """Extrahiert Vorschaubild via ExifTool (nur wenn folium verfügbar, für interaktive Karte)."""
    try:
        cmd = ["exiftool", "-b", "-ThumbnailImage", file_path]
        img_data = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        if img_data:
            return base64.b64encode(img_data).decode("utf-8")
    except Exception:
        pass
    return ""


def run_exiftool_batch(paths: List[str]) -> List[Dict[str, Any]]:
    cmd = [
        "exiftool", "-n", "-json", "-q",
        "-GPSLatitude", "-GPSLongitude", "-GPSAltitude",
        "-DateTimeOriginal", "-CreateDate", "-MediaCreateDate", "-TrackCreateDate",
        "-Make", "-Model", "-FileType", "-MIMEType", "-FileName", "-Directory",
    ] + paths
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return json.loads(proc.stdout) if proc.stdout.strip() else []
    except Exception:
        return []


def process_batch(file_batch: List[Path], thumb_size: int) -> List[Dict[str, Any]]:
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

        dt = pick_best_datetime(item)
        make = str(item.get("Make", "") or "")
        model = str(item.get("Model", "") or "")
        filetype = str(item.get("FileType", "") or "")
        mimetype = str(item.get("MIMEType", "") or "")
        alt = item.get("GPSAltitude", "")

        # Google Maps URL (stabiler)
        gmaps = f"https://www.google.com/maps?q={lat},{lon}"

        results.append({
            "path": path,
            "datetime": dt,
            "make": make,
            "model": model,
            "filetype": filetype,
            "mimetype": mimetype,
            "lat": float(lat),
            "lon": float(lon),
            "alt": alt,
            "gmaps": gmaps,
            "thumb": get_thumbnail_base64(path) if HAS_FOLIUM else "",
        })

    return results


# --- ANALYSIS ---
def detect_duplicates(rows: List[Dict[str, Any]], dist_m: float, time_s: int) -> List[Dict[str, Any]]:
    """Identifiziert zeitlich und räumlich nahe Aufnahmen (Events/Cluster)."""
    enriched: List[Tuple[datetime, Dict[str, Any]]] = []
    for r in rows:
        d = parse_dt(r.get("datetime", ""))
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


# --- EXPORTS ---
def export_main_csv(rows: List[Dict[str, Any]], csv_path: Path):
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["path", "datetime", "make", "model", "filetype", "mimetype", "lat", "lon", "alt", "gmaps"]
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
        d = parse_dt(r.get("datetime", ""))
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
           (id INTEGER PRIMARY KEY, path TEXT, timestamp TEXT, make TEXT,
            model TEXT, filetype TEXT, mimetype TEXT, lat REAL, lon REAL, alt TEXT, maps_url TEXT)"""
    )
    data = [
        (None, r["path"], r.get("datetime", ""), r.get("make", ""), r.get("model", ""),
         r.get("filetype", ""), r.get("mimetype", ""), r["lat"], r["lon"], str(r.get("alt", "")), r.get("gmaps", ""))
        for r in rows
    ]
    cur.executemany("INSERT INTO evidence VALUES (?,?,?,?,?,?,?,?,?,?,?)", data)
    conn.commit()
    conn.close()


def export_kml(rows: List[Dict[str, Any]], kml_path: Path):
    kml_path.parent.mkdir(parents=True, exist_ok=True)
    header = '<?xml version="1.0" encoding="UTF-8"?>' \
             '<kml xmlns="http://www.opengis.net/kml/2.2"><Document><name>Forensic Export</name>'
    with open(kml_path, "w", encoding="utf-8") as f:
        f.write(header)
        for r in rows:
            desc = xml_escape(
                f"Time: {r.get('datetime','')}\n"
                f"Device: {r.get('make','')} {r.get('model','')}\n"
                f"URL: {r.get('gmaps','')}\n"
                f"Path: {r.get('path','')}"
            )
            f.write(f'<Placemark><name>{xml_escape(Path(r["path"]).name)}</name>')
            f.write(f"<description>{desc}</description>")
            f.write(f'<Point><coordinates>{r["lon"]},{r["lat"]},0</coordinates></Point></Placemark>')
        f.write("</Document></kml>")


def export_interactive_map(rows: List[Dict[str, Any]], html_path: Path):
    if not HAS_FOLIUM or not rows:
        return

    html_path.parent.mkdir(parents=True, exist_ok=True)

    # Startpunkt: erster Treffer
    m = folium.Map(location=[rows[0]["lat"], rows[0]["lon"]], zoom_start=4, tiles="cartodbpositron")

    marker_cluster = MarkerCluster(name="Beweismittel").add_to(m)
    HeatMap([[r["lat"], r["lon"]] for r in rows], name="Heatmap").add_to(m)

    for r in rows:
        thumb_html = ""
        if r.get("thumb"):
            thumb_html = f'<img src="data:image/jpeg;base64,{r["thumb"]}" style="width:100%;">'

        popup_content = (
            f'<div style="width:220px">'
            f"<b>{xml_escape(Path(r['path']).name)}</b><br>"
            f"{xml_escape(str(r.get('datetime','')))}<br>"
            f"{xml_escape(str(r.get('make','')))} {xml_escape(str(r.get('model','')))}<br>"
            f"<hr>{thumb_html}"
            f'<br><a href="{r.get("gmaps","")}" target="_blank">Google Maps</a>'
            f"</div>"
        )

        folium.Marker(
            [r["lat"], r["lon"]],
            popup=folium.Popup(popup_content, max_width=260),
        ).add_to(marker_cluster)

    folium.LayerControl().add_to(m)
    m.save(str(html_path))


def export_duplicates_csv(dups: List[Dict[str, Any]], csv_path: Path):
    if not dups:
        return
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = ["cluster_id", "cluster_size", "path", "datetime", "make", "model", "filetype", "mimetype", "lat", "lon", "alt", "gmaps"]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in dups:
            w.writerow({k: r.get(k, "") for k in fieldnames})


# --- MAIN ---
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
    args = ap.parse_args()

    src = Path(args.sd).expanduser()
    dst = Path(args.od).expanduser()

    if not src.exists():
        print(f"Error: {src} not found")
        sys.exit(1)

    dst.mkdir(parents=True, exist_ok=True)
    logger = setup_logging(dst)

    # Alle Output-Dateien: IMMER unter dst (außer --oc, wenn du explizit woanders willst)
    out_csv = Path(args.oc).expanduser() if args.oc else (dst / "test.csv")
    out_sqlite = dst / "forensic_data.sqlite"
    out_kml = dst / "locations.kml"
    out_html = dst / "interactive_map.html"
    out_dups = dst / "duplicates_report.csv"

    logger.info(f"Scan: {src}")
    logger.info(f"Output Dir: {dst}")
    logger.info(f"Main CSV: {out_csv}")
    logger.info(f"Threads: {args.threads} | Chunk: {args.chunk_size} | Folium: {HAS_FOLIUM}")

    # 1) Sammeln
    exts = PHOTO_EXTS | VIDEO_EXTS
    files = [Path(r) / f for r, _, fs in os.walk(src) for f in fs if Path(f).suffix.lower() in exts]
    if not files:
        logger.warning("Keine Medien gefunden.")
        return

    # 2) Parallel Processing
    chunks = [files[i:i + max(1, int(args.chunk_size))] for i in range(0, len(files), max(1, int(args.chunk_size)))]
    all_rows: List[Dict[str, Any]] = []

    with ProcessPoolExecutor(max_workers=int(args.threads)) as executor:
        futures = {executor.submit(process_batch, c, DEFAULT_CONFIG["thumbnail_size"]): c for c in chunks}
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

    # Sortierung nach Datum (unbekannt ans Ende)
    all_rows.sort(key=lambda r: (parse_dt(r.get("datetime", "")) is None, parse_dt(r.get("datetime", "")) or datetime.max))

    logger.info(f"Treffer: {len(all_rows)}. Export startet...")

    # 3) Exporte (ALLES nach dst/out_csv)
    export_main_csv(all_rows, out_csv)
    export_sqlite(all_rows, out_sqlite)
    export_kml(all_rows, out_kml)

    if HAS_FOLIUM:
        export_interactive_map(all_rows, out_html)
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
