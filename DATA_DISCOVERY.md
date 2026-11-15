# Data discovery and verification log

**Current status · 15 November 2026**

## Current local real-data case

- The workspace contains the downloaded NISAR L2 GUNW granule `G4375022208-ASF`, its saved CMR UMM sidecar, and the official QA report PDF, QA_STATS HDF5 and QA_SUMMARY CSV under the ignored `data/raw/` tree.
- CMR sidecar collection: `NISAR_L2_GUNW_PROVISIONAL_V1`. The pair is reference 2026-10-04 and secondary 2026-10-16, frequency A / HH, ascending / left-looking, EPSG:32644 at 80 m posting.
- Both the saved CMR UMM polygon and HDF5 product footprint intersect the attributed WGS84 Kalka–Shimla railway OSM relation 331109 geometry.
- Independent local QA reproduction rasterizes the projected centerline with `all_touched=True`: 1,478 touched cells, 1,471 pass the stated combined phase/coherence/component/subswath/anomaly screen, 7 fail because their secondary subswath code is zero (99.53% under that screen).
- This is radar observability, not movement coverage. Every one of the 1,471 passing route cells also has bit 24 set in the mask; the HDF5 describes this as the ionospheric-phase filtering mask for masked/interpolated ionospheric estimates.
- QA_SUMMARY reports an identification-group FAIL. The delivered CMR asset manifest and local QA tree contain the QA PDF, QA_STATS and QA_SUMMARY but no `LOG.txt`; the field and impact remain unresolved.
- The physical sign of this stored unwrapped phase remains unresolved. No signed displacement, railway safety conclusion, or GNSS validation is available. Keep the current read-only Radar Evidence workspace separate from the legacy Three-Lane processor.

## Discovery-method evidence caveat

The standalone `StrainLine_Data/13_Metadata_Notes/discover_nisar_gunw.py` utility is an ASF Search (`asf_search`) metadata search. Its saved latest run, dated 2026-11-14, is explicitly `NOT SEARCHED` because name resolution failed while retrieving the OSM route. Its CSV contains only a header. Do **not** cite that run as proof that the selected granule was discovered by a successful local query.

The product's saved `.h5.cmr.json` sidecar retains the NASA CMR concept record, granule UMM, archived assets and the transfer receipt. The CMR/ASF record plus the local download verification establish the provenance for the product currently demonstrated. The application also contains a separate live NASA CMR catalog implementation. A live catalog query was not performed during this final local review; do not suggest that a live search ran during a demonstration unless verified on the day.

## Current maturity context

ASF/NASA's current NISAR availability overview states that VALIDATED L0–L2 collections released on 2026-11-06 cover L-band acquisitions beginning 2026-10-21; pre-2026-10-21 validated reprocessing is planned for 2027. The selected 2026-10-04 pair remains in the PROVISIONAL collection. ASF describes PROVISIONAL data as calibrated and validated at limited sites, pending more complete validation over broader areas. Its maturity must be shown accurately.

## Useful source files

- Local product and CMR sidecar: `data/raw/<granule>.h5` and `data/raw/<granule>.h5.cmr.json` (ignored, not distributed).
- Official QA siblings: `data/raw/qa/` (ignored, not distributed).
- Attributed WGS84 route: `StrainLine_Data/00_AOI/route/kalka_shimla_railway_osm_relation_331109.geojson`.
- Local quality calculation: `backend/gunw_qa.py`; reproduce with `python scripts/inspect_gunw_qa.py <product.h5> <route.geojson>`.
- Scientific interpretation and documented caveats: [`reports/FINAL_SCIENTIFIC_REVIEW.md`](reports/FINAL_SCIENTIFIC_REVIEW.md).

## Sources

- ASF/NASA DAAC, [NISAR data availability and maturity](https://nisar-docs.asf.alaska.edu/availability-overview/), [GUNW guide](https://nisar-docs.asf.alaska.edu/gunw/), [phase guide](https://nisar-docs.asf.alaska.edu/phase/).
- NASA CMR, [granule search and UMM JSON API](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html).
- ISRO/SAC, [NISAR L1/L2 Product Format Document](https://bhoonidhi.nrsc.gov.in/NISAR/NISAR_Data_Product_Format_Document_V1.2.1_digisigned.pdf).
