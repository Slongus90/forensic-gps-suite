# Forensic GPS & Timeline Analysis Suite

**Sprache:** [English](README.md) | Deutsch

Dieses Projekt unterstützt die forensische Analyse von GPS- und Zeitdaten aus Foto- und Videodateien
(EXIF/QuickTime) mit dem Ziel **gerichtsfester, reproduzierbarer Dokumentation**.

Der Fokus liegt auf:
- konservativer Zeitachsenrekonstruktion
- klarer Trennung zwischen Fakten und Annahmen
- lückenloser Nachvollziehbarkeit aller Verarbeitungsschritte

## Funktionen

- Extraktion von GPS-Koordinaten aus Medien
- Ermittlung der bestmöglichen Zeitquelle (GPS, EXIF, MediaCreateDate)
- Zeitzonen-Normalisierung mit expliziter Kennzeichnung von Annahmen
- Aufbau einer chronologischen Timeline
- Analyse von:
  - Bewegungssegmenten (Stop / Move / Jump)
  - Zeitlücken (Gaps, Major Gaps, Critical Gaps)
- Exportformate:
  - CSV (gerichtstauglich)
  - SQLite
  - GeoJSON
  - KML
  - optionale interaktive Karte (nur außerhalb Court-Mode)
- Optional: SHA256-Hashing & Beweis-Manifest

## Voraussetzungen

- Python 3.9+
- [ExifTool](https://exiftool.org/) im `PATH`
- Optional für Komfortfunktionen:
  - `tqdm` (Fortschrittsanzeige)
  - `folium` (interaktive Karte)
  - `psutil` (Speicher- und Prozessdaten)

## Schnellstart

```bash
python3 gps_forensic.py \
  --sd "/pfad/zum/material" \
  --od "/pfad/zum/output" \
  --court \
  --sha256
```

## Output-Struktur

* `timeline.csv` – chronologische Zeitachse
* `movement_report.csv` – Bewegungsanalyse
* `gaps_report.csv` – erkannte Zeitlücken
* `evidence_manifest.csv` – Hashwerte (optional)
* `forensic_audit.log` – vollständiges Audit-Log

## Court-Mode (Gerichtsmodus)

Bei Aktivierung von `--court` gilt:
- **keine impliziten Zeitzonenannahmen**
- keine Heuristiken oder Interpretationen
- keine Thumbnails oder visuelle Anreicherung
- nur belegbare, prüfbare Daten

Dieser Modus ist für gerichtliche Verfahren vorgesehen.

## Forensische Grundsätze

* keine Mischung von timezone-aware und naive Zeitstempeln
* jede Annahme wird explizit gekennzeichnet
* reproduzierbare Ergebnisse bei identischen Eingaben

## Lizenz / Haftung

Dieses Tool unterstützt forensische Analysen, ersetzt jedoch **keine rechtliche Bewertung
oder sachverständige Begutachtung**.
