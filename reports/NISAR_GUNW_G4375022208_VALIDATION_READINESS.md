# StrainLine independent validation readiness — Phase 5

**Granule:** `G4375022208-ASF`  
**Product:** `NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001`  
**Pair:** reference 2026-10-04; secondary 2026-10-16  
**Maturity:** provisional L-band, frequency A, HH; ascending, left-looking; 80 m; EPSG:32644  
**Scope:** validation-readiness investigation only. No displacement values were calculated, published, or displayed. The original HDF5, CMR sidecar, checksum files, application, and scientific formulas were not modified.

## Decision for the next scientific processing phase

**NO-GO for signed LOS displacement processing or quantitative validation claims.** The exact field behind the QA identification-group FAIL is not in the delivered QA artifacts, and the product-specific QA log is absent from the CMR file manifest. The processing chain fixes the mathematical operand order as reference SLC × conjugate(secondary SLC), but authoritative material reviewed still does not bind that exact stored, flattened phase to the signed one-way range / toward-away LOS direction. No date-specific GNSS observations or solutions were verified for the pair.

**GO for targeted readiness work only:** obtain the missing SDS QA diagnostic, request or retrieve corridor-local CORS records and site logs, and obtain an authoritative signed-convention statement or controlled known-sign reference case. Do not calculate displacement until the first two science gates are resolved and validation strategy and uncertainty are defined.

## Findings by evidence status

### Confirmed

- The product-specific QA_SUMMARY has `Passes all identification group checks? = FAIL`, while `QA completed with no exceptions? = PASS`. It does not list a failed member, observed/expected value, severity, or diagnostic.
- The CMR UMM sidecar’s `DataGranule.ArchiveAndDistributionInformation` contains ten archived assets: the main HDF5, browse images, ISO XML, runconfig YAML, KMLs, QA report PDF, QA_STATS HDF5, and QA_SUMMARY CSV. There is no QA `LOG.txt` entry. The three downloaded QA files exactly match the CMR filenames/sizes/checksums recorded in the Phase 3 report.
- Product identity, reference/secondary dates, relevant RSLC input names, track, frame, pass, look, band, frequency, polarization, and product version agree between the HDF5 information inspected and the CMR sidecar. Both reference and secondary input-data-exception flags are zero. `referenceListOfObservationModes` and `secondaryListOfObservationModes` each contain `(NOT SPECIFIED)` in the HDF5 and are rendered the same way in the QA PDF. This is a candidate anomaly only; it is not identified as the QA failure.
- The failed summary row is in the **identification/metadata QA category**. QA_SUMMARY reports the listed raster NaN/invalid-percentage checks and coordinate-grid check as PASS. This rules out interpreting this particular row as a reported phase-array invalid-percentage failure. It does not clear geolocation or phase quality from the unknown field-level failure.
- ISCE3 source at recorded tag `v0.25.16` multiplies reference SLC by conjugated secondary SLC. The unwrap workflow writes the SNAPHU output and the RUNW-to-GUNW workflow maps the phase layer without a later global negation. This establishes the stored phase's **mathematical construction** but does not resolve its physical signed LOS meaning. See the Phase 4 report for the detailed chain and equation comparison.
- The IGS station directory lists `DRDN00IND` in Dehradun at 30.340287° N, 78.044164° E, with its latest reported RINEX data at CDDIS dated 2026-11-13. Distance from that station coordinate to the project railway centerline is about **109.6 km**, calculated in UTM zone 44N from the WGS84 route GeoJSON. It is a regional geodetic station, not local railway ground truth.
- The official IGS data description says daily RINEX files represent 24-hour observations at 30-second intervals; IGS guidance states global data centers should keep daily files online for at least one year. CDDIS requires authenticated access after anonymous FTP was discontinued. The Earthdata token was read only from local `EARTHDATA_TOKEN.env`; it was never printed. The date-specific HEAD requests to CDDIS failed at connection establishment in this environment, so neither file was verified as present or downloaded.
- Survey of India (SoI) operates an official CORS station map and reference-data service. Its published procedures describe registration and ordering historical station or virtual-reference-station observations in RINEX and other formats. These services require a registered login/subscription or data order; public service descriptions alone do not establish availability for this project.

### Partially confirmed

- The SoI public interactive map currently reports a national network of roughly 1,142 stations (the page snapshot shows connected, disconnected, and connected-but-not-fixed counts). The station markers and station details are populated dynamically; the retrievable page text did not expose a verified station table, coordinates, site logs, per-station historical date coverage, or a corridor query result. No SoI station name, exact coordinate, railway distance, or 2026 observation availability is asserted in this report.
- NRSC/ISRO documents a Himalayan GNSS CORS program and publishes a regional map with labeled locations including Shimla and Sundernagar, as well as Dehradun and Manali. It also describes continuous CORS and campaign-mode GNSS observations and time-series processing. The reviewed public document does not associate a named marker unambiguously with a particular CORS site, supply station coordinates/site logs, or provide the two 2026 daily data files. These are promising local-provider leads, not confirmed validation stations.
- DRDN00IND’s continuously reported archive listing makes it plausible that daily RINEX is available for both 2026 dates, which are earlier than its reported latest data and within IGS’s stated minimum daily retention period. Actual date-specific file existence, completeness, quality, and coordinate solutions remain unconfirmed because CDDIS access failed from this environment.
- The QA issue is clearly an identification/metadata check failure, not a reported raster missingness check. The unidentified metadata member could still encode pair identity, acquisition configuration, or other metadata relevant to interpreting the product. Therefore its scientific effect cannot be classified as benign or as geolocation/phase-affecting without the diagnostic.

### Unresolved

- **Exact QA field and severity:** not in QA_SUMMARY, QA_STATS, or the QA report PDF. The `(NOT SPECIFIED)` observation-mode fields are suspicious but not proven to have caused the failure. The “FAIL” is the only reported severity/status; no finer severity or impact category is supplied.
- **QA impact:** the summary category says identification group. It does not identify whether the field relates only to descriptive metadata or influences geolocation, pair ordering, or processing interpretation. Do not treat the row as harmless.
- **Phase sign:** no authoritative product spec, product log, or controlled known-sign reference result reviewed here explicitly binds the exact GUNW `unwrappedPhase` from ISCE3 0.25.16 to signed range change and toward-positive or away-positive LOS displacement. The handbook’s deformation equation and its separate range/LOS definitions are not explicitly reconciled to the production operand and flattening conventions. Sign remains NO-GO; no plot-based inference was made.
- **Local independent GNSS validation:** exact SoI/NRSC station identifiers, coordinate epochs, distances from those coordinates to the railway, historical observations for both dates, access approval, station logs, and processing-ready position solutions have not been obtained.
- **Pair-specific external reference:** no verified local GNSS pair solution exists in this review. A distant station cannot validate local rail-corridor motion by itself.

### Not available in this review

- Product-specific `QA_LOG.txt` or alternate SDS/n isanqa diagnostic containing failed field-level messages. The complete CMR manifest represented in the local sidecar does not list a QA log. The official nisarqa output specification says `LOG.txt` is the textual listing of errors; therefore it must be requested from the SDS/ASF support path or obtained from the source QA run if retained.
- Actual RINEX observation files for DRDN00IND for 2026-10-04 and 2026-10-16 and daily coordinate solutions at those epochs. No observations were downloaded because the CDDIS HEAD requests could not establish a connection.
- A verified SoI CORS station inventory with exact coordinates and archived data status for the Kalka–Shimla corridor. The official public page is interactive/dynamic and the station data did not load through the available text access; no CORS data order was submitted.
- Authoritative source/log/reference data establishing the phase-to-signed-LOS convention for this specific stored phase.

## QA resolution path

The complete CMR asset manifest is stronger evidence than checking a guessed filename alone: it advertises the three QA products and other sidecars but no log. The nisarqa public documentation defines `SUMMARY.csv` as a high-level PASS/FAIL check summary and `LOG.txt` as the textual list of errors. The next action is to request the exact `LOG.txt` or field-level check output from ASF/NISAR SDS for this granule and QA software version 17.0.0. If the log is not retained, request the validator rule, field, observed value, expected value, and impact statement from the product team. Re-run the corresponding metadata validation only against an official schema/rule set; do not edit the HDF5 or suppress the failure to force a pass.

## GNSS investigation and recommended acquisition

1. Use SoI’s official CORS map and Reference Data Shop after registration to query a corridor buffer around the route, export each candidate’s exact coordinate and station log, and order RINEX spanning both radar acquisition epochs. Confirm historical holdings, equipment changes, monument stability, sample rate, and access terms before selecting a station. The pair dates are 12 days apart; continuous observations around each zero-Doppler time are preferable to daily positions alone.
2. Ask NRSC for the station inventory and site logs for its Himalayan CORS program near Shimla/Sundernagar, and whether 2026 RINEX and daily coordinate time series can be shared for those dates. The public NRSC material confirms regional GNSS monitoring, but not station-level coordinates or accessible holdings.
3. Treat DRDN00IND as a regional reference/control candidate only. If local SoI/NRSC RINEX is unavailable, a reference station roughly 110 km away cannot be labeled local ground truth; atmospheric gradients, local deformation, reference-frame processing, and GNSS spatial decorrelation can make it unsuitable to validate this corridor.
4. After obtaining data, estimate epoch-matched GNSS 3-D displacement in a consistent reference frame with station covariance and documented antenna/orbit/clock handling. Project the independent vector onto the NISAR LOS vector at the same station location and compare only after the NISAR signed phase convention is resolved. This comparison has not been performed here.

## Phase-sign decision

Retain the Phase 4 NO-GO. The source trace establishes `S_ref × conj(S_sec)` and that unwrapping/geocoding do not globally reverse it. The unresolved link is the sign of focused RSLC phase versus one-way range, the signed ordering of the geometry range correction used in flattening, and the positive direction of LOS displacement. The required evidence is an authoritative SDS/ISCE3 statement or a derivation from the exact release that explicitly links those three definitions; a controlled known-sign product/target can independently corroborate it. No displacement conversion should be implemented before that evidence is recorded.

## GO / NO-GO

| Next activity | Decision | Reason |
|---|---|---|
| Continue read-only QA and metadata investigation | **GO** | Existing product and QA artifacts are readable; no product modifications required. |
| Request SDS diagnostic and station records | **GO** | Necessary and bounded evidence-gathering work. |
| Retrieve/inspect date-specific RINEX after network access is available | **GO, conditional on access** | CDDIS/SoI records can provide independent observations; date-specific holdings remain unchecked. |
| Signed LOS displacement processing | **NO-GO** | Phase-to-physical-sign relation and QA failure remain unresolved. |
| Claim corridor GNSS validation now | **NO-GO** | No local station/date-matched RINEX or GNSS displacement solution was inspected. |
| Vertical settlement, railway safety, or operational alert | **NO-GO** | One provisional 80 m LOS pair and no local independent validation cannot support these claims. |

## Integrity and tests

The Phase 4 report remains the technical source for the previous detailed mathematical derivation and raster QA. This Phase 5 report is the only new project file. No code, scientific calculations, original HDF5, CMR sidecar, or checksum files were changed. The complete suite was run after report creation: **56 tests passed** (`python -m unittest discover -s tests`; 2.792 s).

## Sources

- NASA/JPL, [ISCE3 Crossmul.cpp v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/cxx/isce3/signal/Crossmul.cpp), [unwrap.py v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/unwrap.py), and [geocode_insar.py v0.25.16](https://github.com/isce-framework/isce3/blob/v0.25.16/python/packages/nisar/workflows/geocode_insar.py).
- NASA/JPL, [NISAR Science Users’ Handbook](https://assets.science.nasa.gov/content/dam/science/missions/nisar/nisar-jpl/pdf/NISAR_FINAL_9-6-19.pdf), §§15.2–15.2.1.
- NASA/JPL SDS, [NISAR L1/L2 ATBD D-95677 Rev. A](https://nisar-docs.asf.alaska.edu/atbd/), §§5.8–5.9.
- ISRO/SAC, [NISAR Level-1/Level-2 Product Format Document v1.2.1](https://bhoonidhi.nrsc.gov.in/NISAR/NISAR_Data_Product_Format_Document_V1.2.1_digisigned.pdf).
- ISCE Framework, [nisarqa documentation](https://github.com/isce-framework/nisarqa) (QA outputs and log purpose).
- IGS, [DRDN00IND metadata](https://network.igs.org/DRDN00IND), [data access](https://www.igs.org/data-access/), and [daily GNSS data archive information](https://connect.igs.org/data/).
- Survey of India, [CORS station map](https://corswebmap.surveyofindia.gov.in/), [CORS registration and service information](https://surveyofindia.gov.in/pages/continuously-operating-reference-stations-cors-), and [observation ordering SOP](https://surveyofindia.gov.in/UserFiles/files/SoP%20for%20VRS%20Data%20downloading.pdf).
- NRSC/ISRO, [GNSS CORS and Himalayan geodynamics program summary](https://www.nrsc.gov.in/sites/default/files/pdf/ebooks/3.%20%2050yeares%20Achivements_compressed.pdf) and [regional Geodynamics and CORS map](https://www.nrsc.gov.in/nrscnew/assets/pdf/announcements/DRM_Meet_2023/S-IV_GeologicalDisasters.pdf).
