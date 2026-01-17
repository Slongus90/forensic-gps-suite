# Forensic GPS & Timeline Analysis Suite

This project supports forensic analysis of GPS and timestamp data extracted from
photo and video files (EXIF / QuickTime), with emphasis on **court-admissible,
reproducible documentation**.

Core principles:
- conservative timeline reconstruction
- strict separation of facts vs assumptions
- full traceability of every processing step

## Features

- GPS extraction from media files
- Best-available timestamp resolution (GPS, EXIF, media metadata)
- Timezone normalization with explicit assumption flags
- Chronological timeline construction
- Analysis of:
  - movement segments (stop / move / jump)
  - temporal gaps (gap / major / critical)
- Export formats:
  - CSV (court-friendly)
  - SQLite
  - GeoJSON
  - KML
  - optional interactive map (non-court mode only)
- Optional SHA256 hashing & evidence manifest

## Requirements

- Python 3.9+
- [ExifTool](https://exiftool.org/) available in `PATH`
- Optional conveniences:
  - `tqdm` (progress display)
  - `folium` (interactive map)
  - `psutil` (memory and process details)

## Quick start

```bash
python3 gps_forensic.py \
  --sd "/path/to/evidence" \
  --od "/path/to/output" \
  --court \
  --sha256
```

## Output Files

* `timeline.csv` – chronological timeline
* `movement_report.csv` – movement analysis
* `gaps_report.csv` – detected temporal gaps
* `evidence_manifest.csv` – file hashes (optional)
* `forensic_audit.log` – full audit log

## Court Mode

When running with `--court`:
- **no implicit timezone assumptions**
- no heuristics or interpretive logic
- no thumbnails or visual enrichment
- only verifiable, raw evidence data

This mode is intended for legal proceedings.

## Forensic Principles

* no mixing of timezone-aware and naive timestamps
* every assumption is explicitly marked
* reproducible results with identical inputs

## Disclaimer

This tool assists forensic analysis but **does not replace legal evaluation
or certified expert testimony**.
