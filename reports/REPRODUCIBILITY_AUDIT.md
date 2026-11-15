# StrainLine reproducibility and portability audit

**Audit date:** 2026-11-15  
**Scope:** clean-machine installation and reproduction of the read-only Radar Evidence demonstration for G4375022208-ASF. This is a filesystem and documentation audit; the HDF5, sidecar, and credential files were not modified or published.

## Findings

| Check | Finding | Classification |
|---|---|---|
| Absolute machine paths | Application data roots use `Path(__file__).resolve()` and repository-relative paths (`backend/main.py`, `backend/radar_evidence.py`). One generated metadata note contained a personal Windows path; it has been replaced with a repository-relative route path. Sampler provenance JSON intentionally records resolved absolute input/output paths, so those generated analysis artifacts are machine-specific and should not be published without redaction or a portability-safe export. |
| Python version | README requires Python 3.11+, consistent with Earthdata/earthaccess runtime requirements and current testing. Python 3.11 x64 is the tested baseline. |
| Dependencies | `requirements.txt` includes API and science requirements; `requirements-test.txt` adds no test-only package because tests use `unittest`. Minimum/maximum version ranges are not a lockfile, so exact transitive versions are not pinned. Geo-spatial packages (`rasterio`, `pyproj`, `shapely`, `h5py`, `numpy`) need compatible platform wheels/libraries. |
| Frontend dependencies | Browser JavaScript is served locally with the app; Leaflet, fonts and OpenStreetMap tiles load from external services. Offline use can lose the map background/fonts. Node.js is needed for the documented JavaScript syntax check, not for app runtime. |
| Environment and credentials | The downloader reads `EARTHDATA_TOKEN` from process environment first, then project `.env`, then project `EARTHDATA_TOKEN.env` (`backend/download.py:11-34`). Both files are ignored by `.gitignore`; `.env.example` contains an empty placeholder. The backend does not print token values. A user must provide their own token only if downloading; an existing local product/sidecar can be demonstrated without credentials. |
| Data layout | Railway GeoJSON is part of the project at `StrainLine_Data/00_AOI/route/`. The product, matching `.h5.cmr.json` sidecar, and QA siblings are under `data/raw/` (QA under `data/raw/qa/`). All files under `data/raw/` are ignored. The approximately 2.33 GB HDF5, sidecar and downloaded QA products are therefore not present in a clean clone/package by design. |
| Product portability | Radar Evidence currently targets one granule and fixed relative filenames, and returns unavailable if the HDF5, sidecar, or route is missing. Reproduce the demonstration by placing the exact verified HDF5 and matching CMR sidecar under `data/raw/`; no application code contains a user-specific absolute path. |
| Startup and relative paths | Run Uvicorn from the project root using `backend.main:app`; static assets, downloads and selected evidence files resolve relative to the package/repository root. Starting from another working directory is not documented/supported. |
| Tests | README's `python -m unittest discover -s tests -v` command is correct; the current full suite contains 60 tests. Tests use temporary HDF5/GeoJSON fixtures where appropriate, not substitutes for the actual product in the UI. |
| Stale documentation | `README.md`, `PITCH.md`, `DATA_DISCOVERY.md`, and the saved metadata note had claims that predated the actual downloaded product and/or implied a current search succeeded. README and the project-facing discovery/pitch notes were updated to distinguish current verified evidence from the failed latest standalone ASF-search run. Older QA/readiness reports retain historical test counts that were true when those reports were written. |
| Repository publication status | This workspace has no `.git` metadata available, so this audit cannot inspect tracked/untracked status. `.gitignore` excludes `.env`, `EARTHDATA_TOKEN.env`, `data/raw/*`, and processed data. Do not stage or upload the product, token files, or private analysis data. |

## Clean setup for the live Radar Evidence demo

From a fresh copy of the project, in Windows PowerShell (adjust Python installation only; no source path needs editing):

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-test.txt
```

Then provide the exact product files locally:

1. Use the app's selected-product download flow with your own NASA Earthdata authentication, or obtain the official ASF/CMR product and CMR sidecar through an authorized method.
2. Place the exact granule HDF5 and matching `<granule>.h5.cmr.json` in `data/raw/`. The filenames must match the selected G4375022208-ASF granule.
3. Keep the OSM route at `StrainLine_Data/00_AOI/route/kalka_shimla_railway_osm_relation_331109.geojson`.
4. For independent QA rechecks, separately obtain the three CMR-listed QA assets (PDF, QA_STATS HDF5, QA_SUMMARY CSV) into `data/raw/qa/`. They are not required by the UI endpoint itself. No product-specific QA `LOG.txt` is currently available.
5. Do not copy tokens into the project for this demo unless downloading. If download is needed, create a local ignored `.env` with `EARTHDATA_TOKEN=<your short-lived token>`; do not commit it, print it, or put it in a command-line argument. The project `.env.example` is only a template.

Run verification and start the app:

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
node --check frontend\app.js
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000`, choose **Radar evidence**, and verify the QA warning, unresolved phase sign, local product ID and valid/invalid cell counts before presenting. The endpoint reads actual local HDF5 cells; it does not fall back to synthetic data.

## Reproduction limitations

- To reproduce this exact demonstration, another person needs the 2.33 GB product and authentic matching CMR sidecar; those are intentionally excluded from Git. The exact file can be re-downloaded, but needs a working network and Earthdata authentication.
- Current dependency requirements specify ranges rather than exact resolved versions; the same numerical behavior cannot be promised across arbitrary future package releases without a maintained lockfile.
- The latest standalone ASF `asf_search` report in `StrainLine_Data/13_Metadata_Notes/` is marked `NOT SEARCHED` because DNS resolution failed. It is not a successful candidate-search record. For this demo, show the preserved CMR sidecar and download receipt and be clear that the local app did not conduct a live search during the presentation.
- The historical support/phase-sign blockers are scientific, not setup problems. A clean install does not clear the QA failure or resolve phase sign.
