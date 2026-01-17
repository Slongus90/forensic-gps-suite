# forensic-gps-suite

Tool to extract and analyze GPS metadata from photos and videos. Recursively scans media files and exports CSV, KML, interactive maps, monthly summaries, duplicate location events, and SQLite datasets. Suitable for research, analysis, and data review workflows on Linux and WSL.

## Features

- Recursively scans common photo/video formats for GPS metadata.
- Exports CSV, KML, SQLite, monthly CSV breakdowns, and duplicate-event reports.
- Optional interactive HTML map output (folium) with thumbnails.
- Parallelized EXIF processing for large collections.

## Requirements

- Python 3.8+
- [ExifTool](https://exiftool.org/) available on the `PATH`
- Optional Python packages:
  - `tqdm` for progress bars
  - `folium` for interactive map output
  - `psutil` for memory usage reporting

## Installation

```bash
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install tqdm folium psutil
```

Install ExifTool (examples):

```bash
# Ubuntu / Debian
sudo apt-get install libimage-exiftool-perl

# macOS (Homebrew)
brew install exiftool
```

## Usage

```bash
python gps_forensic.py \
  --sd /path/to/media \
  --od /path/to/output
```

### CLI Options

| Option | Description | Default |
| --- | --- | --- |
| `--sd` | Scan directory (root). | required |
| `--od` | Output directory (all artifacts). | required |
| `--oc` | Optional main CSV output path. | `<od>/test.csv` |
| `--threads` | Worker processes. | CPU count |
| `--chunk-size` | Batch size for ExifTool calls. | `50` |
| `--dup-dist` | Duplicate detection distance in meters. | `5.0` |
| `--dup-time` | Duplicate detection time window in seconds. | `10` |
| `--no-monthly` | Disable monthly CSV export. | off |

## Outputs

When a scan completes, the following artifacts are written to the output directory:

- `test.csv` (or `--oc` path)
- `forensic_data.sqlite`
- `locations.kml`
- `interactive_map.html` (only if `folium` is installed)
- `monthly_YYYY_MM.csv` (unless `--no-monthly` is set)
- `duplicates_report.csv` (only when duplicates are detected)
- `forensic_audit.log`

## Examples

Scan a dataset and write outputs to `./out`:

```bash
python gps_forensic.py --sd ./media --od ./out
```

Disable monthly CSVs and increase duplicate detection tolerance:

```bash
python gps_forensic.py \
  --sd ./media \
  --od ./out \
  --no-monthly \
  --dup-dist 15 \
  --dup-time 60
```

## Troubleshooting

- **No GPS data found**: Ensure the files contain GPS EXIF metadata and that ExifTool can read it.
- **interactive_map.html not created**: Install `folium`.
- **Slow runs**: Increase `--threads` or `--chunk-size` if your machine has available CPU/RAM.

## Contributing

Issues and pull requests are welcome. Please include sample files or logs when reporting problems.

## License

Add your preferred license here.
