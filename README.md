# StrainLine · Ground Context Intelligence

This repository's original software and documentation are released under the [MIT License](LICENSE). External data, basemap tiles, route geometry, and product files retain their own licenses and attribution requirements.

**Inspect the radar evidence. Check the support. Document what remains unresolved.**

StrainLine is a prototype for checking radar evidence along mapped infrastructure corridors. Its current real-data workspace displays the phase and quality layers from one NISAR product and reports whether the product's raster cells pass a stated screen along the railway geometry. Its broader Three-Lane analysis workflow is experimental and is not scientifically cleared for the current G4375022208-ASF product.

This is not a damage detector, displacement result, safety assessment, or repair recommendation. The current product's physical phase sign and QA identification failure are unresolved. Radar validity is not ground-motion coverage. A single interferogram is one between-acquisition phase observation; it does not establish a long-term trend. LOS is not vertical settlement.

## Run locally

Use Python 3.11 or newer (64-bit recommended). From the project root in PowerShell, create the environment and install the declared API/science/test requirements:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt -r requirements-test.txt
python -m uvicorn backend.main:app --reload
```

Open [http://127.0.0.1:8000](http://127.0.0.1:8000). Start Uvicorn from the project root so the relative package paths resolve. The Radar Evidence workspace opens first as a read-only view of the local G4375022208-ASF product and included Kalka–Shimla route; Corridor, Ground Context, Robustness Lab, Field Cases, and Data & Provenance remain available in the navigation rail. If the HDF5 and CMR sidecar are absent, Radar Evidence shows an unavailable state and the Corridor workspace remains usable. The map uses online OpenStreetMap tiles and fonts load from a CDN. CMR catalog search returns metadata only.

To reproduce the **Radar evidence** workspace on a clean machine, provide the exact G4375022208-ASF HDF5 and matching `.h5.cmr.json` sidecar in `data/raw/`. These 2.33 GB source files and QA siblings are ignored by Git and are not included in a clean checkout. The WGS84 Kalka–Shimla OSM GeoJSON is included. See [the clean setup audit](reports/REPRODUCIBILITY_AUDIT.md) for product placement, QA artifacts, checks and launch steps. Once those files are present, select **Radar evidence** in the left navigation. It displays decimated previews of actual phase, coherence, connected-component and combined-validity layers. Click the railway line to inspect the corresponding full-resolution source cell and its distance along the nearest mapped OSM way geometry; this is not an official railway kilometer post because the relation is stored as separate ways. Click elsewhere on the raster to inspect that source cell. One selection stays synchronized across displayed layer values. The current screen reports 1,478 centerline-touched cells; 1,471 pass the documented phase/coherence/component/subswath/anomaly screen (99.53%). This is radar observability under that screen, not ground movement or asset-level coverage. All 1,471 passing cells also carry the product's bit-24 ionospheric-phase-filter mask; see the [scientific review](reports/FINAL_SCIENTIFIC_REVIEW.md) for the caveat. Product provenance, provisional maturity, identification-group QA FAIL, unresolved physical phase sign and limitations remain visible. The source HDF5 is read-only; this workspace does not convert phase to displacement or make safety conclusions.

Run the automated calculation and failure-condition tests after installing the requirements above:

```powershell
python -m unittest discover -s tests -v
```

Install only scientific or API dependencies with `python -m pip install -r requirements-science.txt` or `requirements-api.txt`. Earthdata access is optional for metadata search. To enable downloads, copy `.env.example` to `.env` and add a short-lived Earthdata Login token there. The backend reads it locally; never put tokens in browser files or commit `.env`.

## Free Render deployment

[`render.yaml`](render.yaml) prepares a Render **Free** FastAPI Web Service with no disk. It uses `pip install -r requirements.txt` and `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`; `autoDeployTrigger: off` avoids deployment until you manually trigger it. Connect the public GitHub repository to Render, select **New → Blueprint**, and review that the service plan says **Free** before creating it. The expected public URL is `https://strainline.onrender.com` if that service name is available.

The 2.33 GB HDF5 and CMR sidecar stay on the local computer and are excluded from Git. The hosted Radar Evidence API loads the compact real-data evidence files in [`docs/data/`](docs/data/): four source-derived PNG previews, exact values and coordinates for all 1,478 railway-touched source cells, product metadata, QA findings, limitations, and a SHA-256 manifest. The current extracted bundle is about 2.8 MB (ZIP: about 2.1 MB). Radar previews, metadata, and railway-cell inspection therefore work without HDF5 on Render. Arbitrary off-railway pixel inspection, HDF5 inspection, and product download are explicitly local-only on the hosted instance. The other five workspaces remain available; workflows that need uploaded rasters, a full GUNW, or persistent server-side files need those inputs locally or must be run in the local Windows app.

To rebuild the deployment evidence package, install the project requirements, make sure the exact source HDF5 and matching CMR sidecar are present in `data/raw/`, then run:

```powershell
python scripts/build_pages_demo.py
```

The build refuses to proceed if product identity or the 1,478/1,471 QA cross-check fails. It writes the previews, cell samples, manifest and compressed archive. Keep `.env`, `.env.*` (except the harmless `.env.example` template), `EARTHDATA_TOKEN.env`, the source HDF5, sidecar and other credentials out of Git. Do not add Earthdata credentials as Render environment variables; public evidence does not need them.

Render Free services have an ephemeral filesystem, sleep after 15 minutes without traffic and can take about a minute to wake. Free plans also have monthly instance-hour, bandwidth and build limits. No disk is provisioned and the service can be suspended if included usage is exhausted without a payment method. The service is suitable for a public judge demo, not dependable production uptime or durable uploads. See [Render's Free plan limits](https://render.com/docs/free).

## Architecture

```text
frontend/                   Corridor · Ground Context · Robustness Lab · Field cases · Data & provenance · Radar Evidence
backend/main.py              FastAPI API, CMR proxy, exact footprint check, exports
backend/radar_evidence.py    Read-only real GUNW previews, validity and railway-cell inspection
backend/gunw_reader.py       Original single-centerline GUNW processor
backend/gunw_metadata.py     Reads documented product identity, pair, orbit and raster metadata
backend/corridor_sampler.py  Three chainage-aligned GUNW sampler and terrain-raster join
backend/control_lane_engine.py Shared motion, relative LOS, ambiguous/no-call logic
backend/reference_robustness.py Tests Control A, Control B, and paired-reference sensitivity
backend/terrain_matching.py  Terrain and radar covariate match calculations
backend/terrain_raster.py   DEM-derived slope/aspect and categorical land-cover sampling
backend/footprint.py         CMR UMM polygon geometry helpers
backend/temporal_analysis.py Compatibility gate for multi-pair descriptions
backend/dual_band_check.py   Conservative L/S comparability gate
backend/case_generator.py    Explainable field case and proposed survey plan
tests/                       Synthetic calculations and failure conditions
data/raw/                    Local source products; excluded from Git
data/processed/              Derived local files; excluded from Git
reports/                     Export targets
```

## Investigation workflow

1. **Select a corridor.** Load an attributed WGS84 GeoJSON alignment. It stays in the browser. The map shows the real route on a georeferenced OpenStreetMap basemap.
2. **Find products.** Search provisional L-band GUNW metadata. A bounding-box match is discovery only. Use the exact vector intersection action to check the route against the CMR UMM polygon; this still does not prove usable radar pixels.
3. **Retrieve and inspect.** To enable one selected-product download, sign in to NASA Earthdata Login and generate a replacement user token if the previous one was exposed. Store it locally as `EARTHDATA_TOKEN=<your token>` in the project-root `.env`, or as the sole raw token line in the project-root `EARTHDATA_TOKEN.env`. Keep either file private and restart the backend after changing it. Do not put credentials in the browser, command line, source files, or chat. The server uses the Earthdata `earthaccess` session, writes under `data/raw/`, streams to a resumable `.part` file, and publishes the HDF5 only after checks pass. A selected catalog result is re-fetched by CMR concept ID; its granule identity, official data URL, file size and CMR checksum are checked, and the HDF5 must be readable with the expected embedded granule ID. The workflow also writes a `{filename}.cmr.json` sidecar with the authoritative CMR record and download receipt; signed query strings are removed from stored links. Keep product, sidecar, checksum, dates, orbit/look geometry, polarization, maturity and reference ordering together. If a transfer is interrupted, retry the selected download to resume from `data/raw/<granule>.h5.part` when ASF honors the HTTP Range request.
   After download, select **Inspect local HDF5** to read the product's own granule id, reference/secondary start and end times, orbit/pass, look direction, band, center frequency, phase dimensions, grid spacing, projection and bounding polygon. If a corridor is loaded, it also checks exact intersection against the HDF5 bounding polygon and displays that footprint. Maturity still comes from CMR. The inspector does not decide phase sign; complete a documented phase convention review before signed interpretation.
4. **Build the Three-Lane support.** Provide an aligned GeoJSON FeatureCollection containing three `LineString` features with `properties.lane` equal to `asset`, `control_a`, and `control_b`. The GUNW sampler uses the same chainage stations and spatial radius. It returns median LOS proxies and valid-pixel counts. It no-calls lane groups with different connected components or subswath pairs.
5. **Pass the product evidence gate.** The legacy analysis API checks supplied product metadata: CMR granule and record URL, collection and maturity, acquisition dates, orbit/look geometry, polarization, exact footprint intersection, and a `phase_convention_reviewed` assertion. This is a completeness check, not independent authentication or scientific review. The current G4375022208 product's phase sign remains unresolved; do not set this field to true to bypass the blocker, and do not use the broader Three-Lane processor for signed LOS results from this granule.
6. **Establish matching.** Provide per-pixel DEM elevation, slope, aspect, land-cover class, coherence, and phase/mask validity samples from traceable ancillary data. The backend summarizes these on each lane and checks explicit analyst limits. API analysis refuses to run if covariate records are missing or either control fails. Example limits in generated requests are placeholders only; replace and cite them.
7. **Run the test.** For each section, `common_motion = median(control A, control B)` and `asset_relative = asset LOS − common_motion`. The absolute lane values stay visible. Controls that disagree are ambiguous; insufficient pixels or bad radar quality are no-call. Candidate limits are analyst settings, not safety thresholds.
8. **Investigate and export.** Candidate, ambiguous, and no-call sections produce field evidence cases. Each contains the lane values, reasons, product record and proposed measurement locations at the asset, both controls and a stable reference. Processed requests carry the lane centerlines and the union of nominal sample windows; the Corridor map displays those support zones, and the GeoJSON export combines them with candidate locations. The polygons describe where the sampler looked, not where usable radar pixels were found. Export PDF, CSV, GeoJSON and provenance JSON. No missing coordinate is invented.

## Sample three lanes from a GUNW product

Install `requirements-science.txt`, then run:

### Generate terrain-screened control candidates

Before drawing two controls by hand, you can create candidate offset lanes from a verified WGS84 corridor and screen them against DEM and land-cover terrain around each shared chainage station. This is a preliminary terrain screen only: it does not establish radar comparability, and it does not automatically designate the best controls. The analyst reviews the candidate report and GeoJSON, chooses two eligible lanes on opposite sides where possible, and the subsequent GUNW sampler applies coherence, support, connected-component, and subswath gates.

Place the alignment GeoJSON, projected-metre DEM GeoTIFF, and integer categorical land-cover GeoTIFF in `data/raw/`, then run (replace the filenames and offset distances for your corridor):

```powershell
python -m backend.control_candidates `
  --centerline data\raw\rail-alignment.geojson `
  --dem data\raw\dem-projected-metres.tif `
  --land-cover data\raw\land-cover-categorical.tif `
  --offsets-m 150 250 400 --radius-m 80 --spacing-m 160 `
  --report data\processed\control-candidates.json `
  --geojson data\processed\control-candidates.geojson
```

Inspect `control-candidates.json` and open `control-candidates.geojson` in StrainLine's map or a GIS viewer. Candidate IDs combine side and offset, such as `left_150m` and `right_250m`. If two candidates are terrain-eligible and appropriate after map review, request a sampler-ready three-lane file by adding:

```powershell
  --select-a left_150m --select-b right_250m `
  --selected-lanes data\raw\three-lanes.geojson
```

Append those options to the candidate command above. The tool rejects duplicate or terrain-ineligible selections. Review the selected lane geometry and candidate report; radar quality is still pending until sampling against a real GUNW product. Adjust offsets, support radius, station spacing, and terrain thresholds for the effective resolution and context of the study, and document the source dataset identity, version, license, and category scheme.

Put the source files under `data/raw/`:

- One downloaded `.h5` / `.he5` GUNW product.
- A WGS84 GeoJSON `FeatureCollection` with three aligned `LineString` features, whose `properties.lane` values are exactly `asset`, `control_a`, and `control_b`. Draw the controls in nearby terrain expected to be comparable; the sampler and terrain-match gate will reject unsuitable controls, but they cannot choose valid terrain on your behalf.
- A traceable DEM GeoTIFF in a projected metre CRS.
- A one-band integer categorical land-cover GeoTIFF using a consistent classification scheme across all lanes.

For example, save the lane file as `data/raw/three-lanes.geojson`:

```json
{"type":"FeatureCollection","features":[
  {"type":"Feature","properties":{"lane":"asset"},"geometry":{"type":"LineString","coordinates":[[76.91,30.70],[76.93,30.72]]}},
  {"type":"Feature","properties":{"lane":"control_a"},"geometry":{"type":"LineString","coordinates":[[76.92,30.70],[76.94,30.72]]}},
  {"type":"Feature","properties":{"lane":"control_b"},"geometry":{"type":"LineString","coordinates":[[76.90,30.70],[76.92,30.72]]}}
]}
```

These coordinates only illustrate the file structure; replace them with the verified route and terrain-matched controls. Do not use this example as study data.

```powershell
python -m backend.corridor_sampler `
  --gunw data\raw\selected-granule.h5 `
  --lanes data\raw\three-lanes.geojson `
  --dem data\raw\dem-projected-metres.tif --dem-units m `
  --land-cover data\raw\land-cover-categorical.tif `
  --output data\processed\three-lane-request.json `
  --polarization HH --min-coherence 0.4 --spacing-m 80 --radius-m 80
```

The GeoJSON must contain one chainage-aligned feature per lane and each line must be WGS84. Supply a traceable DEM in a projected metre CRS and declare whether its elevation values are metres or feet. Supply a one-band integer categorical land-cover raster and verify that its category scheme is consistent across all lanes. Raster sampling uses the nearest raster cell; DEM slope and downslope compass aspect come from a least-squares plane fit to up to 3×3 valid neighboring DEM cells. Flat terrain retains a null aspect because its direction is undefined; the aspect match is treated as not applicable when either lane is flat. Missing raster support stays missing and can prevent a terrain match. The sampler records absolute source paths, SHA-256 fingerprints, CRS, band, vertical units, and methods; the user must still record dataset identity, version, license, and attribution. An optional pre-sampled `--terrain-match` JSON remains supported. Values shown above are example analyst choices, not universal recommendations or extra spatial resolution. The sampler requires the HDF5 unwrapped-phase layer to declare radians before conversion and uses the GUNW mask's documented water/reference-subswath/secondary-subswath digits; native support, phase convention, and selected product quality govern interpretation. It produces phase-derived LOS range-change proxies; it does not correct atmospheric contributions, infer vertical movement, validate against GNSS, or assign safety status.

The generated request intentionally requires metadata review before analysis. Inspect the local HDF5 product, confirm its exact footprint intersection with the imported corridor, and complete the `provenance` fields from that HDF5 record and NASA CMR: granule ID and URL, collection and maturity, reference/secondary acquisition dates, orbit/frame geometry, look direction, polarization, and signed phase convention/order. Set `footprint_intersection` only after the exact geometry check. Set `phase_convention_reviewed` only after checking the documented convention for the specific product and recording the reference/secondary order; do not toggle it to bypass the gate. Then open StrainLine, load the corridor, and choose **Load processed lane observations** to submit `data/processed/three-lane-request.json`. The API rejects incomplete provenance or controls that fail terrain/radar matching.

The sampler-generated request contains processed section `samples`, `lane_geojson` for the selected centerlines and nominal support polygons, per-pixel `lane_pixels` with GUNW phase proxy, coherence, masks/components/swaths and (when supplied) DEM/land-cover covariates, matching thresholds, and provenance. The web UI sends the per-pixel records to `/api/terrain-match`; the robustness lab reuses those records to recalculate narrower radii. These large analysis JSONs are local artifacts. The browser does not upload HDF5 or ancillary rasters; keep their source files in `data/raw/` so the recorded hashes and paths remain reproducible. A request's supplied provenance is completeness-checked, not independently authenticated. If using Earthdata-authenticated downloads, copy `.env.example` to `.env` and put your short-lived token in `EARTHDATA_TOKEN`; keep that local file private.

## Time series and dual band

L/S comparison is unavailable until actual L- and S-band summaries share acquisition dates, geometry, polarization and spatial support. Compatible geometry does not erase wavelength-specific scattering differences. The API returns consistent, disagree, unavailable or not comparable.

Temporal reconstruction accepts three or more JSON result exports from processed Three-Lane analyses. It requires the same corridor, common reference acquisition, spatial phase-reference identifier, geometry, polarization, signed phase review, reference/secondary ordering and effective native support. It aligns sections by chainage, reports absolute and asset-relative changes, lists acquisition gaps and no-call sections, and offers CSV/JSON exports. A compatible history is attached to a generated field case only at the same 1 mm chainage key and corridor; case details and PDF reports retain usable observations, missing/no-call pairs, and the reason history is unavailable. No-call values are never interpolated. An individual pair is not a trend; the output is a screening series, not a validated deformation time series. Each record must pass the product metadata completeness gate; supplied records are still not independently authenticated.

The Reference Robustness Lab recomputes the uploaded observation against Control A alone, Control B alone, and the paired-control median. When the processed request retains per-pixel coordinates, phase-derived LOS, coherence, component, swath, DEM, and land-cover records, it also recalculates all lanes and matching gates at three concentric radii between the selected fraction and the original sampled radius. This tests narrower comparison windows using the actual pixels; it cannot create new offset control polygons or extend beyond uploaded support. Older section-summary files still support only the three reference choices. The current case session attaches the overall reference-sensitivity classification and per-chainage results; both the detail view and PDF report retain the assessment. Classifications reflect these supplied observations and analyst-selected thresholds, not damage probability.

## Data status and limitations

The current real-data case is one PROVISIONAL L-band GUNW, G4375022208-ASF, whose saved CMR UMM and HDF5 footprints intersect the attributed Kalka–Shimla railway centerline. The centerline rasterization touches 1,478 cells; 1,471 pass the defined screen and 7 fail. This is radar observation support, not movement coverage. The product QA identification-group FAIL is unresolved; bit 24 is set on every screen-passing route cell; physical phase sign and local date-matched GNSS validation are unresolved/unavailable. The read-only Radar Evidence workspace is suitable for a bounded demonstration. Signed displacement, settlement, railway safety, predictive maintenance and damage claims are not supported. The Bridge 57 incident is not treated as validation.

Matching summaries do not fully remove atmospheric delay, reference/unwrapping error, decorrelation, or spatially variable scattering. A single line-of-sight measurement cannot uniquely resolve 3D displacement. Field cases propose verification measurements and do not diagnose defects or prescribe repairs.

## Primary references

- [ASF NISAR availability and maturity](https://hyp3-docs.asf.alaska.edu/nisar-docs/availability-overview/)
- [ASF GUNW product guide](https://nisar-docs.asf.alaska.edu/gunw/)
- [ASF NISAR product specifications](https://nisar-docs.asf.alaska.edu/product-specification/)
- [NASA NISAR mission and data access](https://science.nasa.gov/mission/nisar/mission-overview/)
- [ISRO Bhoonidhi S-band products](https://bhoonidhi.nrsc.gov.in/NISAR/NisarProducts.html)
- [NASA calibration and validation](https://science.nasa.gov/mission/nisar/calibration-and-validation/)
- [Rasterio raster sampling and georeferencing](https://rasterio.readthedocs.io/en/stable/quickstart.html)
- [NASA Space Apps 2026 — Dancing with the SARs](https://www.spaceappschallenge.org/2026/challenges/dancing-with-the-sars/)



