# NISAR GUNW metadata and integrity report

Generated from the downloaded HDF5 and its authoritative NASA CMR UMM sidecar. No ground displacement was calculated or inferred.

## Product identity and provenance

- CMR concept ID: `G4375022208-ASF`
- Granule: `NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001`
- CMR collection and maturity: `NISAR_L2_GUNW_PROVISIONAL_V1` (provisional)
- Product version: `1.0.11`; product specification: `1.5.0`
- CMR was re-queried by concept ID immediately before transfer. The CMR granule identity, official ASF HTTPS data URL, HDF5 size, and HDF5 identity were checked.
- Product file: `data/raw/NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001.h5`
- CMR metadata sidecar: corresponding `.h5.cmr.json` file in `data/raw/`.

## Acquisitions and geometry

- Reference acquisition: 2026-10-04 00:04:50.000000000 to 00:05:24.999342105 UTC
- Secondary acquisition: 2026-10-16 00:04:50.000000000 to 00:05:24.999342105 UTC
- Track/frame: 55 / 17; pass: ascending; look direction: left; orbit type: MOE
- Radar band and frequency: L band; 1,239,000,000 Hz
- Frequency/polarization: A / HH
- HDF5 bounding polygon CRS: WGS 84 longitude/latitude; bounds: 76.499337–79.763551° E, 29.344222–32.035289° N
- Exact vector intersection against the attributed Kalka–Shimla railway GeoJSON: **intersects**. This is an HDF5 footprint check; usable radar pixel support along the railway remains a separate analysis step.
- Raster grid CRS: EPSG:32644 (WGS 84 / UTM zone 44N); pixel spacing 80 m east-west by 80 m north-south.

## HDF5 structure

- File size: 2,327,838,720 bytes (about 2.17 GiB)
- HTTP response: 200
- NASA CMR MD5: `f6995d15ad0bc7e958ceacb04b5b4bd1`; verified against the downloaded bytes.
- Locally computed SHA-256: `459e67aaf84207f68a5b825c825c4d36952ac709168f636e06f3da95192bf9f2`
- HDF5 readability and embedded granule ID: verified.
- Unwrapped phase: `/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/unwrappedPhase`; units are radians; shape 4221 × 4311.
- Coherence: `/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/coherenceMagnitude`; dimensions match phase.
- Connected components: `/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/connectedComponents`; dimensions match phase.
- Mask: `/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/mask`; dimensions match phase.
- Available QA ancillary products listed by CMR (not downloaded): QA report PDF (1,170,338 bytes), QA_STATS HDF5 (156,787 bytes), and QA_SUMMARY CSV (2,665 bytes). CMR provides MD5 checksums for these files.

## Interpretation limits

- The product is provisional; maturity is taken from the CMR collection, not from the HDF5.
- The HDF5 inspector does not determine phase sign. Confirm the official phase/reference-secondary convention before interpreting signed movement.
- No displacement, deformation, or railway condition conclusion is reported here. Spatial overlap alone does not confirm valid radar pixel coverage or adequate coherence along the corridor.
