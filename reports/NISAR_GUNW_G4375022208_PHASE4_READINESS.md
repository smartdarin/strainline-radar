# Phase 4: Phase convention and independent validation readiness

**Granule:** `G4375022208-ASF`  
**Product:** `NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001`  
**Pair:** reference 2026-10-04; secondary 2026-10-16  
**Maturity:** provisional L-band, frequency A, HH; ascending, left-looking; 80 m; EPSG:32644  
**Scope:** evidence and readiness only. No displacement was calculated, displayed, or published. The HDF5, sidecar, checksums, and scientific calculations were not modified.

## Decision

**NO-GO for signed LOS displacement processing at present.** The processing chain establishes a mathematical phase convention—reference complex phase minus secondary complex phase, followed by subtraction of the modeled geometric phase and integer-cycle unwrapping. The available authoritative documents do not unambiguously connect that exact stored phase to a signed one-way range change or a toward-positive/away-positive LOS scalar for this GUNW processing version. A ± sign cannot safely be selected from the source evidence reviewed.

**Conditional readiness:** The pixels and spatial support are promising for a *single-pair exploratory relative LOS study* once (a) SDS resolves the QA identification failure and (b) the signed conversion is authoritatively tied to this processing chain. It would still be provisional, relative to a chosen reference area, and not a rail-condition or vertical-settlement result. The 80 m posting is not track-asset scale.

No phase-to-displacement conversion has been applied. This report contains no displacement values.

## 1. QA identification-group failure

### What the delivered QA artifacts say

The QA_SUMMARY CSV reports the check **“Passes all identification group checks?” = FAIL**. It reports the file-open and coordinate-grid checks as PASS, all listed phase/coherence/connected-component missingness or invalid-value checks as PASS, and “QA completed with no exceptions?” as PASS. The summary provides no failed member name, observed value, expected value, or diagnostic text.

The QA report PDF identifies QA software 17.0.0 and displays both `referenceListOfObservationModes` and `secondaryListOfObservationModes` as `['(NOT SPECIFIED)']`. This is a notable candidate for follow-up, but none of the three delivered QA artifacts identifies it as the failed field. It must not be presented as the cause.

The HDF5 `/science/LSAR/identification` values inspected agree internally with the granule identity and pair: granule ID, track 55, frame 17, ascending pass, left look, L-band, frequency A, HH, and the 2026-10-04 / 2026-10-16 zero-Doppler times. Its processing inputs name the matching RSLCs for those two dates; both input-exception flags are zero. The two observation-mode fields are present with the same `(NOT SPECIFIED)` value shown in the PDF. QA_STATS is a statistical summary of raster layers (its `reference_document` is D-107726); it contains no field-level record explaining the identification check. Thus the available comparison finds agreement for the core pair identity, but cannot identify the complete schema/check failure.

The CMR-delivered granule manifest included the QA report PDF, QA_STATS HDF5, and QA_SUMMARY CSV, but no QA `LOG.txt`. The official ISCE3 NISAR QA documentation describes the log as the artifact containing textual validation errors. Without that log or an SDS diagnostic, the exact failed field is **not available** from the artifacts on hand.

### Interpretation and action

This is an identification/metadata validation category, not a reported phase-array or coherence-array failure. It does not itself establish that the phase sign is wrong, and it does not by itself demonstrate a raster failure. However, identification metadata can define acquisition identity and processing assumptions; since the failed member is unknown, the failure cannot be dismissed as harmless. Request the product-specific `LOG.txt` or field-level nisarqa/SDS validation output and resolve the finding before signed displacement processing.

## 2. Phase processing chain and sign evidence

### Product-specific facts

The HDF5 records ISCE3 software version `0.25.16`, reference input RSLC dated 2026-10-04, secondary input RSLC dated 2026-10-16, `flatteningMethod=With geometry offsets`, SNAPHU unwrapping, and MCF initializer. The inspected output is:

`/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/unwrappedPhase`

The NASA/JPL SDS ATBD (D-95677 Rev. A, §5.9) defines absolute interferometric phase as `φ_abs = (4π/λ) δr`, with `δr` described as a one-way path-length difference, but does not define in that equation whether the difference is secondary-minus-reference or reference-minus-secondary. The same ATBD’s flattening equation is `I_flattened = I × exp(-4πi δr/λ)`: modeled geometric phase is removed from the interferogram. The sign/order represented by its `δr` is not explicitly cross-linked there to this granule’s cross-multiplication operands and a named toward-positive LOS convention.

### Source-level trace at the recorded release

1. **Reference/secondary ordering.** The product metadata and input filenames identify 2026-10-04 as reference (earlier) and 2026-10-16 as secondary. ISRO’s NISAR Level-1/Level-2 Product Format Document says RUNW is generated in the radar geometry of the earlier (“reference”) acquisition.
2. **Interferogram operands.** In ISCE3 [`Crossmul.cpp`, tag `v0.25.16`](https://github.com/isce-framework/isce3/blob/v0.25.16/cxx/isce3/signal/Crossmul.cpp), the cross-multiplication is `refSlcUpsampled * conj(secSlcUpsampled)`. Thus the complex interferogram argument is mathematically `arg(S_ref) − arg(S_sec)` before geometric flattening (modulo `2π`).
3. **Flattening.** The same implementation applies the conjugate of the modeled geometry phase factor when flattening is enabled. This removes that modeled phase; it is not a global sign flip of the residual interferometric phase.
4. **Unwrapping.** The release’s [`unwrap.py`](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/unwrap.py) passes the wrapped interferogram into SNAPHU and stores its unwrapped result. Unwrapping resolves integer-cycle ambiguity; no operand swap or negation is present in this workflow step.
5. **RUNW to GUNW.** The release’s [`geocode_insar.py`](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/geocode_insar.py) maps RUNW interferogram layers into GUNW `unwrappedInterferogram` layers through geocoding/interpolation. The traced path contains no phase negation. ISRO’s product format identifies the GUNW `unwrappedPhase` as derived from the reference and secondary RSLC layers.

Accordingly, the **established mathematical output convention** is the unwrapped, flattened phase originating from `S_ref × conj(S_sec)`, i.e. reference phase minus secondary phase, with the modeled geometry phase removed. No later sign inversion was found in the exact software release recorded by this product.

### Why physical LOS sign is still not established

The NASA NISAR Science Users’ Handbook §15.2 writes a deformation phase as `Δφ = φ₂ − φ₁ − φ′ = 4π Δd/λ` (printed p. 155), while its §15.2.1 defines sensor-to-target range change as `Δρ = −u·s`, with `s` directed from ground target to satellite; motion toward the sensor therefore has `Δρ < 0`. It also cautions that authors differ on whether toward-sensor LOS motion is positive. The handbook’s `φ₂ − φ₁` deformation notation is not explicitly reconciled with the production code’s `S_ref × conj(S_sec)` (`φ_ref − φ_sec`) plus the exact flattening-phase definition for this GUNW. The ATBD leaves the signed order of `δr` unspecified in its phase equation.

The sources do establish the familiar **magnitude scale** for an ideal deformation-only phase, `|Δρ| = λ |Δφ| / (4π)`, but the sign linking this stored `Δφ` to signed `Δρ` or a chosen LOS-positive direction is unresolved. This is not resolved by the HH label, orbit direction, raster appearance, or a color map. No visual sign inference was used.

To resolve the sign, the needed evidence is an SDS statement or source-level derivation binding all three definitions for ISCE3 0.25.16: (i) focused RSLC complex phase versus one-way range, (ii) the sign/order of the modeled geometry phase removed by flattening, and (iii) the selected signed LOS scalar (toward-positive or away-positive). A controlled, independently known-sign validation case may corroborate that documentation, but must not replace it with an assumed sign.

## 3. Quantitative exploratory suitability once gates are cleared

Existing Phase 3 QA found 1,478 railway-touched 80 m cells; 1,471 (99.53%) passed the combined phase/coherence/connected-component/subswath screen. Every touched cell had finite phase and coherence; 1,368/1,478 (92.56%) had coherence ≥0.5 (descriptive threshold only). These figures support spatial observation availability, not correctness of displacement. The analysis mask also leaves seven touched cells without a valid secondary subswath code.

For one pair, after resolving sign and identification QA, the data could support *exploratory relative LOS phase/range change* over coherent, connected regions with an explicit stable reference, atmospheric/orbit/topographic residual assessment, and uncertainty limits. Provisional maturity, 80 m posting, a single 12-day pair, unremoved residual atmospheric/ionospheric and other error sources, lack of local ground validation, and the unresolved QA flag prohibit operational or engineering interpretation. LOS motion must not be relabeled as vertical settlement; that requires additional viewing geometries or justified motion constraints.

## 4. Independent reference observations

### Public GNSS option found

The IGS station directory lists `DRDN00IND` at Dehradun (30.340287° N, 78.044164° E), with daily RINEX data reported at CDDIS through 2026-11-13. The station coordinate is about **109.6 km** from the Kalka–Shimla route centerline, computed from the project’s WGS84 railway GeoJSON in UTM 44N. IGS describes its global data centers as archiving daily GNSS files and CDDIS identifies daily observation files as 24-hour, 30-second RINEX. This makes DRDN a real regional geodetic reference candidate; it is not a corridor-local control point and cannot validate local railway deformation on its own. The public station listing confirms ongoing archive reporting, but this review did not retrieve or inspect the two exact 2026-10-04 and 2026-10-16 RINEX files or solve station coordinates for those dates.

### Better corridor-local option

Survey of India operates a CORS data service and publishes registration/data-ordering procedures for RINEX observations from reference stations or virtual reference stations. The public information reviewed does not expose a verified station coordinate and date-specific data availability near the route, nor prove public access for this project. A registered, locally eligible researcher should query SoI CORS for stations near Kalka, Shimla, and the intervening corridor and request the two acquisition dates plus a sufficiently long continuous time series. Station logs, monument stability, reference-frame realization, antenna changes, data gaps, and coordinate-solution uncertainty must be checked before using it as validation.

### Validation design recommendation

1. First obtain date-matched RINEX and station logs from the nearest eligible SoI CORS site(s); use DRDN00IND as a regional reference / processing control, not as a substitute for a corridor station.
2. Process both epochs into a consistent terrestrial reference frame using precise orbit/clock products, antenna calibrations, and documented tropospheric/ionospheric handling. Compare the 12-day 3-D GNSS displacement projected into the NISAR LOS vector at the station location, with covariance and temporal alignment.
3. Use more than one stable station where possible; check for station motion, equipment changes, snow/vegetation environment, local multipath, and reference-frame common-mode errors.
4. The pair spans 12 days. Continuous GNSS positions around both radar acquisition times are required to distinguish an epoch difference from a daily average or transient. No station solution was downloaded or calculated as part of this phase.

## 5. GO / NO-GO table

| Activity | Decision | Basis |
|---|---|---|
| Read-only phase/mask/coherence/support QA | **GO** | Existing product QA and corridor support are documented. |
| Preserve mathematical convention for interpretation | **GO with explicit definition** | Stored phase traces to flattened `S_ref × conj(S_sec)` with no unwrap/geocode sign flip. |
| Convert phase to signed LOS displacement | **NO-GO** | Authoritative source chain does not bind product sign to signed one-way range / LOS direction. |
| Quantitative exploratory relative LOS after gates | **CONDITIONAL GO** | Pixel support is adequate, subject to resolving phase sign and QA identification failure and explicitly modeling reference/corrections/uncertainty. |
| Claim ground truth from GNSS now | **NO-GO** | No date-specific GNSS files/solutions inspected; known IGS station is ~109.6 km away, and local SoI CORS holdings/coordinates require access verification. |
| Interpret LOS as vertical settlement or assess rail safety | **NO-GO** | One viewing geometry and an 80 m single-pair product do not support those claims. |

## 6. Reproduction, integrity, and test status

Phase 3’s read-only raster/route scan can be reproduced using the instructions in [`NISAR_GUNW_G4375022208_SCIENTIFIC_QA.md`](NISAR_GUNW_G4375022208_SCIENTIFIC_QA.md). No new application code or scientific calculations were changed for Phase 4. The HDF5, CMR sidecar, SHA-256 workflow, and prior report remain intact.

The full test suite passed: **56 tests** (`python -m unittest discover -s tests`; 4.689 s). The original 2,327,838,720-byte HDF5 was rehashed after the investigation: MD5 `f6995d15ad0bc7e958ceacb04b5b4bd1` and SHA-256 `459e67aaf84207f68a5b825c825c4d36952ac709168f636e06f3da95192bf9f2`, matching the recorded Phase 3 values. No application or scientific-processing files were edited; this Phase 4 report is the only new file.

## Sources

- NASA/JPL, [ISCE3 `Crossmul.cpp`, v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/cxx/isce3/signal/Crossmul.cpp).
- NASA/JPL, [ISCE3 NISAR `unwrap.py`, v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/unwrap.py) and [ `geocode_insar.py`, v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/geocode_insar.py).
- NASA/JPL, [NISAR Science Users’ Handbook](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_FINAL_9-6-19.pdf), §§15.2–15.2.1, pp. 155–157.
- NASA/JPL SDS, [NISAR L1/L2 Algorithm Theoretical Basis Document D-95677 Rev. A](https://nisar-docs.asf.alaska.edu/atbd/), §§5.8–5.9.
- ISRO/SAC, [NISAR L & S Band Level-1 & Level-2 Data Product Format Document v1.2.1](https://bhoonidhi.nrsc.gov.in/NISAR/NISAR_Data_Product_Format_Document_V1.2.1_digisigned.pdf), §§8.1, 9.1, 9.3, 10.3.
- International GNSS Service, [DRDN00IND station metadata](https://network.igs.org/DRDN00IND), [data access](https://www.igs.org/data-access/), and [GNSS daily data archive description](https://connect.igs.org/data/).
- Survey of India, [CORS portal and SOPs](https://surveyofindia.gov.in/pages/continuously-operating-reference-stations-cors-) and [VRS/CORS observation ordering SOP](https://surveyofindia.gov.in/UserFiles/files/SoP%20for%20VRS%20Data%20downloading.pdf).
