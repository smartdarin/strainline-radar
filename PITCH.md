# STRAINLINE
## Ground Context Intelligence
### Inspect radar support along critical infrastructure

Railways in steep, vegetated terrain can be challenging to inspect consistently. StrainLine is a prototype that places real radar evidence next to a mapped infrastructure corridor and makes the data-quality limits visible.

The current demonstration uses one actual NISAR L-band GUNW product over the Kalka–Shimla railway. It checks exact polygon/centerline intersection, shows the product's unwrapped phase, coherence, connected components and validity screen, and lets a reviewer inspect source-grid cells along the railway geometry. The result describes radar data observability under a stated screen; it is not a measurement of railway movement or condition.

NISAR's L-band wavelength is about 24 cm. NASA/JPL describes it as penetrating further into dense forest canopy than shorter S-band. This makes L-band observations valuable to investigate in vegetated landscapes, but it does not guarantee coherent or valid phase at a particular site.

## Current evidence and limits

The demonstration granule is `G4375022208-ASF`, a PROVISIONAL 2026-10-04 / 2026-10-16 frequency-A HH pair with an 80 m EPSG:32644 grid. The saved CMR UMM polygon and the HDF5 product footprint intersect the attributed OSM relation 331109 centerline. Of 1,478 80 m cells touched by the mapped centerline, 1,471 pass the documented combined phase/coherence/component/subswath/anomaly screen (99.53%). Seven fail the screen because the secondary subswath code is zero. This percentage is not movement coverage or track-level support.

The product QA summary reports an unresolved identification-group failure, and the physical toward/away sign for its stored unwrapped phase is unresolved. All 1,471 screen-passing route cells have the bit-24 ionospheric-phase mask set; the product says those ionosphere estimates were masked and interpolated during filtering. This does not by itself invalidate the primary GUNW phase but limits claims about ionospheric correction. No date-matched local GNSS validation is available. No displacement or safety finding is presented.

The broader Three-Lane processor is experimental and is not cleared for signed interpretation of this product. Signed LOS processing requires resolution of the QA failure and authoritative phase-sign evidence; independent observations and documented uncertainty are needed before validation claims.

## Scope

StrainLine is not a railway damage detector, settlement meter, predictive-maintenance system, or safety classifier. The 80 m posting is not asset scale. One interferometric pair cannot establish a trend. A LOS observable is not vertical settlement. The Space Apps demonstration is a transparent evidence-inspection workflow and a statement of what still needs to be verified.
