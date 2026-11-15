# StrainLine final scientific review

**Review date:** 2026-11-15  
**Product:** CMR concept `G4375022208-ASF`; NISAR L-band GUNW, frequency A / HH  
**Scope:** independent review of the saved product record, local HDF5 and ancillary QA files, railway geometry, validity calculation, interpretation shown by the application, and the documented processing path. This review does not calculate displacement or alter product data.

## Executive decision

**GO for a read-only evidence demonstration. NO-GO for signed LOS displacement processing, ground-motion claims, or railway-condition conclusions.** The product and corridor overlap and the stated `1,471 / 1,478 = 99.53%` screen result were independently reproduced from the local files. That percentage is radar-cell availability under the project's explicit validity screen; it is not movement coverage. The product remains PROVISIONAL, has an unresolved identification-group QA FAIL, and does not have an established physical phase sign for this exact stored layer and acquisition order.

The mask audit found an additional caveat: all 1,471 screen-passing railway cells have bit 24 set. The HDF5 `mask.description` says this bit identifies pixels masked out and filled with interpolated data during **ionospheric-phase filtering**. It does not, by itself, establish that the primary GUNW unwrapped-phase pixels are invalid. It does mean the corridor's ionospheric phase estimates were masked/interpolated under that filter and must not be presented as independent, direct correction evidence. The 99.53% number is retained as defined; it is not reinterpreted as all mask bits clear.

## Findings and evidence classifications

| Finding | Classification | Evidence and limits |
|---|---|---|
| Granule identity and pair dates | **Verified** | HDF5 identification metadata matches the local CMR UMM sidecar and the downloaded granule name. Reference is 2026-10-04; secondary is 2026-10-16. The CMR sidecar is the archived record snapshot; no live CMR re-query succeeded in this review environment. |
| Live CMR record state | **Partially verified** | The preserved UMM record is locally consistent with the HDF5. The current record was not re-fetched from CMR during this review, so any post-download catalog update is not checked here. |
| Product maturity | **Verified** | Sidecar collection is `NISAR_L2_GUNW_PROVISIONAL_V1`; the product is PGE 0.25.16 / CRID P05023. ASF's current availability documentation says VALIDATED L0–L2 products released 2026-11-06 begin with acquisitions from 2026-10-21; this 2026-10-04 acquisition remains PROVISIONAL, with pre-2026-10-21 reprocessing planned for 2027. PROVISIONAL means calibrated and validated at a limited set of sites, pending more complete geographic validation; it does not mean validated at this corridor. |
| Transfer provenance and integrity | **Verified** | Local download receipt records HTTP 200, 2,327,838,720 bytes, CMR MD5 and SHA-256; earlier Phase 2/3 verification reports record matching checksums and readable HDF5 identity. This review did not modify the product, sidecar, or checksums. The receipt's `checksum_verified` flag is false because no independent SHA-256 was supplied as an expected download argument; `cmr_checksum_verified` and `size_verified` are true. A fresh byte-for-byte digest is intentionally reported separately in the final verification rather than inferred from that flag. |
| CMR / HDF5 footprint intersection | **Verified** | The saved UMM has one polygon. Its WGS84 polygon intersects the attributed WGS84 OSM centerline under Shapely geometry intersection. The HDF5 `boundingPolygon` also intersects the centerline. This is exact vector intersection, not a bounding-box-only match; it does not establish pixel quality. Local implementation: `backend/footprint.py` (`corridor_geometry`, `umm_footprint`) and `backend/main.py` (`_catalog_result`). |
| GUNW layer identity, units and grid | **Verified** | The inspected primary phase path is `/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/unwrappedPhase`, units radians, 4,221 × 4,311 cells. Coherence and connected components are companion HH layers. Product grid is EPSG:32644 with 80 m spacing. ASF's GUNW guide documents geocoded unwrapped phase in radians, 80 m posting, normalized coherence and connected components. |
| Phase as physical ground motion | **Unresolved** | Phase is an interferometric radar observable in radians. Phase color or sign is not a toward/away direction without a proven phase-to-range convention for this exact product, software release, and reference/secondary order. The current Radar Evidence workspace correctly labels phase and explicitly says sign is unresolved. |
| Phase-to-one-way-range scale factor | **Partially verified** | `backend/gunw_reader.py:176` multiplies phase by wavelength divided by `4π`. This is the phase scale under a specific one-way range/sign convention; its applicability to the physical signed direction of this exact stored phase remains unresolved. |
| Existing phase-to-range calculation used as a physical signed result for this product | **Incorrect** | `backend/corridor_sampler.py:47` and `backend/gunw_reader.py:176` can generate phase-scaled results later named `*_los_mm`. The code's `phase_convention_reviewed` field is only a caller-supplied Boolean (`backend/product_validation.py:12-21`), not scientific verification. Do not run/use that output as signed LOS for this granule, and do not treat the metadata gate as resolution of the sign question. No formula was changed in this review. |
| Coherence interpretation | **Verified** | ASF's phase guide defines coherence as phase-spectrum correlation with values 0–1; it is evidence about phase consistency/observability, not displacement. This product's railway median is 0.745 (from the prior QA report); any thresholds are descriptive, not mission pass thresholds. |
| Connected-component handling | **Partially verified** | The railway-touched cells have component label 1; 0 is the invalid/no-component label used by the project's screen and QA report. A nonzero component is not, by itself, proof of correct unwrapping or ground motion. The code screens nonzero/non-fill labels; cross-lane workflows separately require component agreement. |
| Mask interpretation | **Partially verified** | HDF5 attributes describe low-byte water/reference-subswath/secondary-subswath encoding, anomaly bytes 8–23, bit 24 as the ionospheric-phase mask, and fill 255. Along this centerline: 0 water flags, 0 reference/secondary anomaly flags, 0 fill values; 7 cells have mask 10 (secondary subswath zero); 1,471 cells have mask 16,777,228 (both swaths nonzero, bit 24 set). Thus all 1,471 counted cells pass the project's phase/coherence/component/swath/anomaly screen, but not every mask flag is clear. The screen intentionally does not count bit 24 as a main-phase invalid flag; its exact downstream effect on the primary phase is not established by this mask alone. |
| Railway-grid intersection and 99.53% result | **Verified under the stated method** | `backend/gunw_qa.py:59-104` projects the OSM geometry into the product CRS, rasterizes with `all_touched=True`, then counts finite phase, finite coherence in [0,1], nonzero/non-fill component, both nonzero subswath digits, and clear reference/secondary anomaly bytes. Independent recomputation returned 1,478 touched cells, 1,471 passing, 7 failing, 95.83389 km projected geometry; 1,471/1,478 = 99.526…%, rounded to 99.53%. The seven fail because secondary subswath is zero. The route is a centerline, not a rail footprint; 80 m cells are not track-asset measurements. |
| Radar Evidence observability-versus-movement messaging | **Verified** | Radar Evidence presents phase in radians, coherence, components, mask/validity, source-cell sampling, warnings and limitations; it makes no motion or safety call. |
| Broader analysis workflow used as a signed product result | **Incorrect** | Other application workflows can calculate phase-scaled signed-looking `LOS` proxies from user-provided samples after a Boolean review gate. They are not authorized for this product until the QA and sign blockers are resolved. |
| QA identification-group failure | **Unresolved** | The product-specific QA_SUMMARY says `Passes all identification group checks? = FAIL`; the coordinate-grid check and listed raster NaN/invalid checks are PASS, and `QA completed with no exceptions? = PASS`. QA PDF lists identification values but does not mark the failed field. QA_STATS has no field-level failure diagnostic. The local CMR manifest contains ten product/ancillary assets and no `LOG.txt`; recursive local data scan found no product QA log. Failure severity beyond `FAIL`, failed field, observed/expected value, and scientific impact are unavailable. `(NOT SPECIFIED)` observation-mode values are present but are not proven to cause the failure. |
| Independent validation | **Unresolved** | Prior validation-readiness work found no verified local/date-matched CORS or GNSS solution for this pair. No GNSS validation claim is made. |

## Reproduced validity calculation

The exact calculation is:

```text
route_cells = rasterize(projected OSM centerline, 80 m grid, all_touched=True)
screen_valid = finite(phase)
               AND finite(coherence) AND 0 <= coherence <= 1
               AND connected_component != 0 AND != fill
               AND reference_subswath > 0 AND secondary_subswath > 0
               AND reference_anomaly_flags == 0
               AND secondary_anomaly_flags == 0
```

The route mask contains 1,478 cells; 1,471 satisfy that predicate and 7 do not. No water flags, anomaly flags, or fill pixels occur in the 1,478 touched cells. Bit 24 is set on all 1,471 passing cells and is reported separately above. This is **radar data availability under this screen**. It is not a percentage of route length moving, stable, safe, settled, or validated.

## QA clarification request decision

The request draft is saved at [`NISAR_QA_CLARIFICATION_REQUEST.md`](NISAR_QA_CLARIFICATION_REQUEST.md). It asks ASF/NISAR support for the product-specific `LOG.txt` or exact validator result, field, observed and expected values, severity, rule/version, and effect on data interpretation. It has not been sent.

## Readiness recommendation

- **GO:** read-only product/provenance/footprint review; actual radar-layer and source-cell demonstration; repeatable coverage calculation with the mask caveat shown.
- **NO-GO:** signed LOS conversion, publishing displacement values, interpreting the 99.53% as movement or asset coverage, using the failed QA as harmless, or presenting this granule as validated at Kalka–Shimla.
- Before any signed processing: obtain the field-level QA diagnostic; authoritative evidence tying the exact stored `unwrappedPhase` through the recorded processing release to a signed LOS range convention; review current product-specific known issues; establish a correction/reference/uncertainty plan; obtain suitable independent observations if claiming validation.

## Authoritative references

- ASF/NASA DAAC, [GUNW product guide](https://nisar-docs.asf.alaska.edu/gunw/) — product layers, posting, interpolation, phase screen and corrections.
- ASF/NASA DAAC, [phase and coherence guide](https://nisar-docs.asf.alaska.edu/phase/) — phase observable, coherence range/meaning and atmospheric sensitivity.
- ASF/NASA DAAC, [availability and maturity overview](https://nisar-docs.asf.alaska.edu/availability-overview/) and [provisional known issues](https://nisar-docs.asf.alaska.edu/provisional-known-issues/) — release dates, maturity, limited validation, CRID and known limitations.
- NASA/JPL SDS, [L2 GUNW Product Specification D-102272 Rev. E](https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-102272_RevE_NASA_SDS_Product_Specification_L2_GUNW_Nov8_2024_w-sigs.pdf) and [L1/L2 ATBD D-95677 Rev. A](https://nisar-docs.asf.alaska.edu/atbd/) — layer and algorithm specifications.
- ISRO/SAC, [NISAR L/S-band Level-1/Level-2 Product Format Document v1.2.1](https://bhoonidhi.nrsc.gov.in/NISAR/NISAR_Data_Product_Format_Document_V1.2.1_digisigned.pdf) — GUNW data structure and mask description; compare with the local HDF5 `mask.description` attribute.
- NASA CMR, [granule search API / UMM JSON](https://cmr.earthdata.nasa.gov/search/site/docs/search/api.html) and [granule spatial extent guidance](https://wiki.earthdata.nasa.gov/spaces/CMR/pages/391316263/Spatial+Extent+Granule) — metadata representation and spatial extent.
- NASA/JPL, [NISAR Science Users' Handbook](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_FINAL_9-6-19.pdf), §§6.6.1, 15.2 — interferometric terminology and LOS context.
- NASA/JPL ISCE3, [`Crossmul.cpp` at v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/cxx/isce3/signal/Crossmul.cpp), [`unwrap.py`](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/unwrap.py), and [`geocode_insar.py`](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/geocode_insar.py) — recorded source trace for mathematical formation; does not alone resolve physical sign.
- NASA/JPL, [nisarqa outputs](https://github.com/isce-framework/nisarqa) — `SUMMARY.csv` is high-level PASS/FAIL and `LOG.txt` is the textual listing of QA errors.

## Local implementation references

- `backend/gunw_metadata.py` — HDF5 identity, dates, polarization, projection and layer validation.
- `backend/gunw_qa.py:21-43,59-104` — mask decode, all-touched corridor raster and validity predicate.
- `backend/footprint.py:6-30`; `backend/main.py:179-218` — exact UMM polygon/route intersection.
- `backend/radar_evidence.py:98-175,236-338` — read-only evidence metadata, previews, cell sampling and railway selection.
- `backend/gunw_reader.py:176-193`; `backend/corridor_sampler.py:47-91,160-220`; `backend/product_validation.py:7-30` — phase scaling, sampling, and caller-supplied review gate requiring caution.
