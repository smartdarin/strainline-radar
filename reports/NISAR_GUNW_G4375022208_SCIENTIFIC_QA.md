# Scientific QA: NISAR GUNW G4375022208-ASF

**Purpose:** read-only scientific QA and phase-convention review. No displacement values were calculated, and no product arrays or processing calculations were changed.

## Executive decision

- **Railway observation support: PASS for exploratory phase analysis.** The WGS84 railway centerline touches 1,478 cells on the 80 m GUNW grid. Of those, 1,471 (99.53%) have finite phase and coherence, nonzero connected-component labels, and valid reference and secondary subswath codes. Coherence is at least 0.5 in 1,368/1,478 (92.56%) of the touched cells. The 0.5 cutoff is an illustrative screening threshold, not a NISAR acceptance threshold.
- **Signed displacement processing: NO-GO.** The product is in the provisional CMR collection, its official QA summary reports an unexplained identification-group failure, and the reviewed authoritative material does not unambiguously define the signed physical meaning of this exact GUNW `unwrappedPhase` for the product's reference/secondary order. Do not assign toward/away sign or vertical settlement from this phase until the sign is resolved with authoritative SDS/processor evidence or a known-sign validation case.
- **No ground displacement, settlement, or deformation has been estimated.** One pair also cannot establish a trend.

## Product provenance and integrity

| Item | Verified value |
|---|---|
| CMR concept ID | `G4375022208-ASF` |
| Granule ID | `NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001` |
| CMR collection / maturity | `NISAR_L2_GUNW_PROVISIONAL_V1` / provisional |
| Product version / specification | 1.0.11 / 1.5.0 |
| Reference acquisition | 2026-10-04 00:04:50.000000000–00:05:24.999342105 UTC |
| Secondary acquisition | 2026-10-16 00:04:50.000000000–00:05:24.999342105 UTC |
| Track / frame / pass / look | 55 / 17 / ascending / left-looking |
| Frequency / polarization | L band, frequency A / HH |
| Product raster | 4,221 rows × 4,311 columns; 80 m × 80 m; EPSG:32644 (WGS 84 / UTM zone 44N) |
| Main HDF5 | 2,327,838,720 bytes; HDF5 readable; embedded granule identity matches |
| HDF5 MD5 / SHA-256 | `f6995d15ad0bc7e958ceacb04b5b4bd1` / `459e67aaf84207f68a5b825c825c4d36952ac709168f636e06f3da95192bf9f2` |

The product checksum was recomputed after QA and matches the existing CMR MD5 and recorded SHA-256. The HDF5 and its CMR metadata sidecar were preserved.

## Exact phase layer and convention evidence

The phase layer inspected is:

`/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/unwrappedPhase`

It is a float32 4,221 × 4,311 raster in radians; its `_FillValue` is NaN. The associated layers are `coherenceMagnitude`, `connectedComponents`, and the frequency-A `unwrappedInterferogram/mask`.

The product's recorded InSAR software version is 0.25.16. The official ISCE3 `Crossmul.cpp` at tag `v0.25.16` explicitly forms the interferogram as reference SLC multiplied by the complex conjugate of the secondary SLC. The NASA NISAR Science Users' Handbook independently gives the raw interferogram as `Arg(I1 I2*)` and describes the reference SLC as the first image acquired. Therefore the operands are established for this granule: 2026-10-04 reference first, 2026-10-16 secondary conjugated second. The handbook and SDS ATBD describe unwrapped interferometric phase as proportional to differential range/LOS motion, with a two-way 4π/λ factor. However, the signed definition of the differential range/LOS scalar in those passages is not explicitly tied to this GUNW layer's reference-secondary operands and a toward-positive convention. The Handbook separately defines range change as positive for increasing sensor-to-target distance, which is negative for motion toward the sensor, and notes that authors use different LOS-positive conventions.

For this granule the HDF5 input metadata and acquisition timestamps identify 2026-10-04 as reference and 2026-10-16 as secondary. The official source confirms the interferogram operand order, but the SDS GUNW user guide and product metadata reviewed here do not, by themselves, state an unambiguous signed conversion from this exact stored `unwrappedPhase` layer to positive-toward or positive-away LOS motion. Therefore **the physical phase sign remains unresolved**. The scale is one phase cycle per 2π radians and the documented physical relationship is proportional to LOS range change with a two-way phase factor (4π/λ); a signed displacement conversion must not be applied until the sign has been confirmed.

This review did not infer sign from a plotted phase image. It did not apply the phase values to displacement. GUNW documentation also says the estimated ionospheric screen is included but not applied to the main layers by default, and external phase corrections are not removed from the interferometric data by default. The product's correction layers and residual atmospheric, orbital, topographic, and decorrelation contributions remain relevant to later interpretation.

## Official ancillary QA products

The three sibling ancillary files were retrieved from the official ASF product directory identified by the CMR granule manifest. Their sizes and manifest MD5 values match:

| Ancillary product | Bytes | MD5 | Finding |
|---|---:|---|---|
| QA report PDF | 1,170,338 | `c61c0ef2bafcf0059fb110b82b01b7a7` | QA software 17.0.0; product software 0.25.16. Displays phase, coherence, and connected-component QA plots. Component label 0 is documented as invalid unwrapping. |
| QA_STATS HDF5 | 156,787 | `f8c506f19695b2bd079684ffaf26d6f8` | Contains phase/coherence/connected-component distribution statistics and one valid connected component. |
| QA_SUMMARY CSV | 2,665 | `edfb9fe2c31790412ada3b010f3baedc` | File-open and coordinate-grid checks PASS; all listed layer NaN/invalid percentage checks PASS; “Passes all identification group checks?” FAIL; QA completed without exceptions. |

The QA summary does not identify which identification field failed. Its report displays `referenceListOfObservationModes` and `secondaryListOfObservationModes` as `['(NOT SPECIFIED)']`; this is an observed metadata value, **not established as the cause** of the check failure. Treat the identification failure as unresolved and seek the SDS QA validation detail before treating the granule as cleared. The product being provisional is a separate, explicit maturity limitation.

## Pixel, mask, and coherence findings

The percentages below use the full 18,196,731-cell grid unless marked “railway”. Counts are direct reads from the HDF5 arrays; QA_STATS values were cross-checked against the ancillary CSV/PDF.

| Layer / condition | Full grid | Railway-touched cells |
|---|---:|---:|
| Finite unwrapped phase | 9,402,558 (51.67%) | 1,478 / 1,478 (100%) |
| Finite coherence in [0,1] | 9,334,875 (51.30%) | 1,478 / 1,478 (100%) |
| Nonzero connected component other than fill | 8,884,359 (48.82%) | 1,478 / 1,478 (100%) |
| Both reference and secondary subswath codes nonzero | 8,777,866 (48.24%) | 1,471 / 1,478 (99.53%) |
| Combined valid phase, coherence, component, and subswath | 8,258,612 (45.39%) | 1,471 / 1,478 (99.53%) |

- **Coherence:** finite values span 0.00575–0.99580; mean 0.56419 and standard deviation 0.22478. Railway-cell percentiles (0, 10, 25, 50, 75, 90, 100) are 0.173, 0.533, 0.647, 0.745, 0.822, 0.881, 0.964. Railway cells at or above 0.2, 0.3, 0.4, 0.5, 0.6, and 0.7 coherence are 99.39%, 98.78%, 97.63%, 92.56%, 82.95%, and 62.58%, respectively. These are descriptive thresholds, not mission-prescribed pass criteria.
- **Connected components:** values are 0 for 9,312,372 cells (51.18%) and 1 for 8,884,359 (48.82%); no other labels or the 65,535 fill value were found. The one nonzero label means there is one reported valid unwrapping component, not that all pixels are valid.
- **Phase missingness:** phase is finite in 51.67% of the grid; the ancillary QA reports 48.33% NaN and 0% Inf. QA's cumulative phase invalid percentage is 51.73% after its fill and near-zero criteria. These are distinct QA definitions and need not equal a simple finite-value complement.
- **Mask encoding:** the product HDF5 describes a low-byte decimal encoding: hundreds digit water flag, tens digit reference subswath, ones digit secondary subswath. A zero in either subswath digit marks an invalid corresponding acquisition sample; fill is 255. Higher bytes carry reference/secondary anomaly flags; bit 24 marks pixels masked for ionospheric phase filtering. No reference or secondary anomaly flags were set in this product. The ionosphere-mask bit is set in 8,323,086 cells (45.74% of the grid); it is a distinct mask and not synonymous with missing GUNW phase. The railway's seven excluded cells have reference subswath 1 and secondary subswath 0.
- **Subswath / polarization:** the product is frequency A / HH only. The mask shows subswath encoding on the cells; no separate B-frequency or alternate-pol observation is present in this granule.
- **Missing/anomalous values:** QA_STATS reports 0% Inf for the inspected phase, coherence, and connected-component layers. Phase/coherence NaNs and CC label 0 dominate invalid coverage as summarized above. Coherence values observed are within the expected normalized interval [0,1].

## Railway coverage method and assessment

The attributed OSM relation GeoJSON at `StrainLine_Data/00_AOI/route/kalka_shimla_railway_osm_relation_331109.geojson` was projected from WGS84 into the raster's EPSG:32644 and rasterized with `all_touched=True`. This samples every 80 m grid cell touched by the OSM centerline; it is an observation-support check, not a buffered railway footprint or an engineering-scale measurement. The projected route length is approximately 95.83 km. The GUNW raster covers the complete line, and all 1,478 touched cells have finite phase, coherence, and a nonzero connected component. Seven cells have a zero secondary subswath code; the remaining 1,471 pass the combined validity screen.

**Assessment:** the raster has sufficient spatially distributed valid observations for exploratory corridor phase/coherence QA. The single connected component and high corridor coherence support an investigation, but do not establish that phase corresponds to real ground motion, do not resolve its sign, and do not certify stable rail infrastructure. The 80 m posting is coarse relative to track assets and the OSM centerline accuracy; per-asset or sub-track conclusions are not supported by this coverage test.

## GO / NO-GO gates

| Activity | Recommendation | Reason |
|---|---|---|
| Inspect phase, coherence, mask, and spatial support | **GO** | Real HDF5 and official QA inputs were inspected and corridor coverage is adequate for exploratory QA. |
| Continue exploratory analysis of phase patterns without physical sign claims | **GO, provisional only** | Valid corridor support is high; preserve the product's provisional status and QA identification failure in every downstream review. |
| Convert unwrapped phase to signed LOS displacement | **NO-GO** | Exact signed convention for this stored layer has not been established unambiguously from the SDS material reviewed; QA identification check also remains unexplained. |
| Interpret LOS as vertical settlement or issue railway condition conclusions | **NO-GO** | A single LOS measurement is not vertical-only motion; no displacement was computed, and the 80 m product grid is not asset-scale evidence. |

### Required gates before signed displacement

1. Obtain an SDS/ISCE3 statement or source-level implementation evidence that explicitly binds `unwrappedPhase` to the complex interferogram operand order and signed range-change convention for this GUNW processing release.
2. Resolve the QA identification-group failure with its field-level validation output; do not assume the observation-mode string caused it.
3. Review product maturity and known-sign validation evidence for the provisional processing release.
4. Only after those gates, document a LOS sign convention, reference epoch, corrections/reference strategy, and uncertainty treatment. LOS must remain LOS; vertical motion requires additional geometry/assumptions and cannot be stated from this product alone.

## Reproduction and tests

Run the read-only QA scan from the repository root:

```powershell
python scripts/inspect_gunw_qa.py `
  data/raw/NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001.h5 `
  StrainLine_Data/00_AOI/route/kalka_shimla_railway_osm_relation_331109.geojson
```

`backend/gunw_qa.py` performs read-only HDF5 statistics and line-to-grid support mapping. Its unit tests use small in-memory-style temporary HDF5 fixtures only to test mask decoding and geometry plumbing; they are not presented as NISAR observations.

The full test suite passed: **56 tests**.

## Sources

- NASA ASF, [NISAR GUNW product guide](https://nisar-docs.asf.alaska.edu/gunw/) (product layers, posting, interpolation, ionospheric screen and external phase corrections).
- NASA/JPL, [NISAR Science Users' Handbook](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_FINAL_9-6-19.pdf), §6.6.1 and §15.2 (reference/secondary interferogram construction and phase/LOS terminology).
- ISRO/SAC, [NISAR L- and S-band Level-1 and Level-2 Data Product Format Document, v1.2.1](https://bhoonidhi.nrsc.gov.in/NISAR/NISAR_Data_Product_Format_Document_V1.2.1_digisigned.pdf) (GUNW layer and mask specification).
- NASA/JPL SDS, [L2 GUNW Product Specification, JPL D-102272 Rev. E](https://nisar.asf.earthdatacloud.nasa.gov/NISAR-SAMPLE-DATA/DOCS/NISAR_D-102272_RevE_NASA_SDS_Product_Specification_L2_GUNW_Nov8_2024_w-sigs.pdf).
- NASA/JPL SDS, [L1/L2 Algorithm Theoretical Basis Document, JPL D-95677 Rev. A](https://nisar-docs.asf.alaska.edu/atbd/).
- NASA/JPL, [ISCE3 Crossmul.cpp, release tag v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/cxx/isce3/signal/Crossmul.cpp) (reference SLC multiplied by conjugated secondary SLC).

