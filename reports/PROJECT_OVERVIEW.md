# StrainLine project overview

## The problem

Railway corridors in steep, vegetated terrain can be difficult to inspect repeatedly with optical imagery alone. StrainLine is a prototype that brings corridor geometry, radar data support, and quality evidence into one review workflow. Its current NISAR demonstration answers a bounded question: **does this real radar product spatially cover the mapped railway, and what do its phase and quality layers show?** It does not answer whether railway infrastructure is damaged or safe.

## Why NISAR L-band

NISAR L-band uses a wavelength near 24 cm. NASA/JPL describes its L-band signal as penetrating further into dense forest canopy than the shorter S-band signal. Repeat-pass interferometry can provide phase and coherence evidence over vegetated landscapes. These physical advantages do not guarantee coherence, a correct displacement estimate, or useful support at every site; the individual product's masks, QA and processing maturity still require review.

## What is implemented

- NASA CMR metadata discovery for provisional and validated NISAR L2 GUNW collections.
- Exact vector intersection between CMR UMM footprint polygons and a WGS84 railway geometry.
- Secure, selected-product download workflow with CMR metadata sidecar and checksum receipt.
- Read-only HDF5 metadata inspection and a Radar Evidence workspace for phase, coherence, connected components, combined validity, railway overlay and source-cell inspection.
- A reproducible all-touched route-to-grid validity calculation and a 60-test Python suite.
- Prior experimental Three-Lane, robustness and case-generation workflows; these remain separate from the read-only demo and are not scientifically cleared for the current product.

## Current verified demonstration case

| Evidence | Current result |
|---|---|
| Product | `G4375022208-ASF`, NISAR L2 GUNW, frequency A / HH, L band |
| CMR maturity | `NISAR_L2_GUNW_PROVISIONAL_V1`; acquired 2026-10-04 / 2026-10-16 |
| Grid | EPSG:32644, 80 m spacing, 4,221 × 4,311 cells |
| Geometry | The saved CMR UMM polygon and HDF5 footprint each intersect the attributed Kalka–Shimla OSM centerline |
| Route support | 1,478 touched cells; 1,471 pass the documented combined screen; 7 fail, primarily due to zero secondary-subswath code; 99.53% under that screen |
| QA | Product QA summary reports identification-group FAIL; field-level cause not delivered |
| Phase convention | Physical signed LOS direction for this stored phase is unresolved |
| Independent validation | No verified local, date-matched GNSS solution for this pair |

The mask description assigns bit 24 to the ionospheric-phase filtering mask. All 1,471 cells that pass the combined screen have this bit set, indicating those ionospheric phase estimates were masked and filled with interpolated values during filtering. This does not itself invalidate the primary GUNW phase layer, but it further limits claims about ionospheric correction. The validity percentage describes radar data support under the selected screen. It is not ground-motion coverage, track-level support, damage detection, settlement, or validation.

The product's saved CMR UMM sidecar is the durable discovery/provenance record used for this demonstration. The download receipt records HTTP 200, byte size, CMR MD5, local SHA-256 and HDF5 identity checks. The standalone `asf_search` utility's latest saved run failed at DNS resolution before querying products; that run is not represented as successful discovery evidence. Do not claim a live archive search occurred during the presentation unless one is run and verified on the day.

## Scientific status and next gates

The read-only Radar Evidence workspace is appropriate for the demonstration. It labels phase in radians and displays the provisional maturity, QA identification failure, unresolved physical phase sign, data provenance and limitations. Do not convert or publish signed displacement from this product. The broader Three-Lane code applies a phase-to-range scale and outputs signed-looking LOS proxy fields; a user-set metadata Boolean is not independent proof of the convention. Those workflows must remain unused for this product until the phase sign and QA failure are resolved.

Before a scientific displacement analysis, obtain the product-specific QA diagnostic and its impact statement; authoritative source or a controlled known-sign case binding the exact stored phase and reference/secondary order to physical LOS sign; documented reference/correction/uncertainty choices; and suitable independent measurements if validation is claimed. Revisit the product's PROVISIONAL status and known issues. The current granule predates the acquisition cutoff for the November 2026 VALIDATED release and is not itself a VALIDATED product.

## Boundaries

StrainLine is not a railway safety system, damage detector, settlement meter, or predictive-maintenance service. One 12-day interferometric pair cannot establish a long-term trend. LOS phase is not vertical settlement. An 80 m raster cell cannot resolve individual rails, sleepers, or other track assets. No GNSS validation or ground-truth result is claimed.

## Key project materials

- [`FINAL_SCIENTIFIC_REVIEW.md`](FINAL_SCIENTIFIC_REVIEW.md)
- [`NISAR_QA_CLARIFICATION_REQUEST.md`](NISAR_QA_CLARIFICATION_REQUEST.md) (draft; not sent)
- [`DEMO_SCRIPT.md`](DEMO_SCRIPT.md)
- [`DEMO_CHECKLIST.md`](DEMO_CHECKLIST.md)
- [`REPRODUCIBILITY_AUDIT.md`](REPRODUCIBILITY_AUDIT.md)
- [`NISAR_GUNW_G4375022208_SCIENTIFIC_QA.md`](NISAR_GUNW_G4375022208_SCIENTIFIC_QA.md)
- [`NISAR_GUNW_G4375022208_VALIDATION_READINESS.md`](NISAR_GUNW_G4375022208_VALIDATION_READINESS.md)

## References

- NASA/JPL, [NISAR science overview](https://www.jpl.nasa.gov/press-kits/nisar/mission-overview/science/).
- ASF/NASA DAAC, [GUNW guide](https://nisar-docs.asf.alaska.edu/gunw/), [phase guide](https://nisar-docs.asf.alaska.edu/phase/), and [availability/maturity overview](https://nisar-docs.asf.alaska.edu/availability-overview/).
- ISRO/SAC, [NISAR L/S-band Level-1/Level-2 Product Format Document v1.2.1](https://bhoonidhi.nrsc.gov.in/NISAR/NISAR_Data_Product_Format_Document_V1.2.1_digisigned.pdf).
