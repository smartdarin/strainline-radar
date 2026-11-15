# Draft: NISAR GUNW identification QA clarification

**To:** ASF User Services (`uso@asf.alaska.edu`) or the NISAR topic on the NASA Earthdata Forum  
**Subject:** Request for field-level identification QA diagnostic — NISAR GUNW `G4375022208-ASF`

Hello ASF/NISAR support,

I am reviewing the NISAR L-band GUNW product below for a read-only scientific evidence demonstration and would appreciate the product-specific diagnostic behind its identification QA result.

- **CMR granule concept:** `G4375022208-ASF`
- **Granule ID:** `NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001`
- **Product:** L2 GUNW, frequency A / HH; CMR collection `NISAR_L2_GUNW_PROVISIONAL_V1`
- **Recorded processing metadata:** product version 1.0.11; product specification 1.5.0; CRID P05023; processing software 0.25.16
- **QA software:** version 17.0.0, per the product QA report
- **Acquisitions:** reference 2026-10-04; secondary 2026-10-16

The delivered `QA_SUMMARY.csv` reports `Passes all identification group checks? = FAIL`, while the coordinate-grid check, listed raster NaN/invalid-percentage checks, and `QA completed with no exceptions?` are PASS. The summary does not identify the failed field, observed/expected values, severity, or impact. The CMR asset manifest retained with the product lists the QA report PDF, QA_STATS HDF5, and QA_SUMMARY CSV, but no `LOG.txt`; no product-specific QA log is present among the local downloaded artifacts.

Could you please provide, if retained:

1. The product-specific `LOG.txt` or equivalent field-level QA diagnostic for this granule and QA software version.
2. The exact identification field/check that failed, its observed value and expected value, and the validator rule/schema version.
3. The failure severity and whether it affects only descriptive identification metadata or has implications for acquisition identity/order, geolocation, phase interpretation, or another science-quality category.
4. Whether any formal disposition, caveat, or correction applies to this granule.

The HDF5 and QA PDF show `referenceListOfObservationModes` and `secondaryListOfObservationModes` as `(NOT SPECIFIED)`. I am recording that as an observed metadata value only; I am **not** assuming it caused the identification failure. Please confirm whether it is related only if the diagnostic establishes that connection.

This request is a draft only and has not been sent. No credentials, access tokens, personal contact details, or machine-specific file paths are included.

Thank you,

StrainLine project reviewer

## Support channel reference

The [ASF NISAR Data User Guide contact page](https://nisar-docs.asf.alaska.edu/contact/) identifies the NASA Earthdata Forum as the preferred venue for NISAR questions and lists ASF User Services at `uso@asf.alaska.edu` as an alternative.
