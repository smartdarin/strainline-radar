# StrainLine NASA Space Apps demonstration checklist

## Before the event

- [ ] Use a clean Python 3.11+ environment and install `requirements.txt` plus `requirements-test.txt` from the project root.
- [ ] Place the exact real granule HDF5 and matching `.h5.cmr.json` sidecar in `data/raw/`; do not commit either file.
- [ ] Confirm `StrainLine_Data/00_AOI/route/kalka_shimla_railway_osm_relation_331109.geojson` is present and retain its OSM attribution.
- [ ] Keep the QA report, QA_STATS and QA_SUMMARY in `data/raw/qa/` for reference; no product-specific `LOG.txt` is available.
- [ ] Check the granule embedded ID, CMR concept ID, file size and local checksum record; do not claim current CMR re-query if the network is unavailable.
- [ ] Run `python -m unittest discover -s tests -v` and `node --check frontend/app.js`.
- [ ] Start the server from the project root: `python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000`.
- [ ] Verify `/api/health`, `/api/radar-evidence`, and each `/api/radar-evidence/preview/{phase,coherence,components,validity}` endpoint.
- [ ] Load the Radar Evidence workspace once before presenting; confirm phase sign and QA FAIL banners are visible.
- [ ] Ensure the coverage block says 1,471 valid / 7 invalid / 1,478 touched cells and labels this radar observability, not movement.
- [ ] If you require a map background, confirm internet access for OpenStreetMap tiles. The radar previews themselves come from the local HDF5.
- [ ] Do not paste an Earthdata token into slides, a command, browser code, or chat. A token is unnecessary for the demo if the HDF5 and sidecar are already available.

## During the demonstration

- [ ] Frame the product as one provisional L-band pair, not a validated corridor time series.
- [ ] Show the CMR ID, acquisition pair, HH polarization, ascending/left-looking geometry, EPSG:32644 and 80 m posting.
- [ ] Explain that L-band's longer wavelength is useful for observing vegetated landscapes, but does not guarantee valid phase at every cell.
- [ ] Show the exact railway / product footprint overlap, then explain that footprint overlap and radar-cell validity are separate checks.
- [ ] Switch through actual phase, coherence, connected-component and combined-validity layers.
- [ ] Click the OSM railway overlay and identify the sampled source-grid cell and local mapped-segment distance; do not call it an official railway chainage.
- [ ] Explain the 99.53% screen denominator and predicate. Mention that all 1,471 passing cells have bit 24 set for the ionospheric-phase filtering mask; do not state that every mask bit is clear.
- [ ] Keep the QA identification-group FAIL and unresolved physical phase sign visible.
- [ ] Say explicitly that phase in radians is not signed displacement, validity is not ground movement, and the 80 m cells are not track-asset measurements.
- [ ] Make no safety, damage, settlement, prediction, or GNSS-validation claim.

## Stop conditions

- [ ] If the product/sidecar is missing or identity checks fail, stop and do not substitute example or synthetic data.
- [ ] If the QA or phase-sign caveat is hidden, restore it before continuing.
- [ ] Do not run the Three-Lane processor for this GUNW while the signed phase convention and QA identification failure remain unresolved.
- [ ] Do not send the QA support request without separate approval.
