# StrainLine demonstration script (2–3 minutes)

**Target runtime:** about 2 minutes 20 seconds at a clear speaking pace.  
**Demo workspace:** Radar Evidence. Use only the local G4375022208-ASF product and the attributed Kalka–Shimla OSM route.  
**Science boundary:** show radar evidence and observability only. Do not run or present signed displacement processing.

## Spoken script and screen actions

**0:00–0:25 — Problem**  
“Railways cross steep, vegetated terrain where optical imagery can be blocked by cloud and canopy. StrainLine is a prototype for inspecting whether radar data covers a railway corridor and whether its quality supports further investigation. It does not detect railway damage or decide whether a route is safe.”  
*Screen: open the StrainLine Corridor workspace briefly, then select Radar Evidence.*

**0:25–0:45 — Why NISAR**  
“NISAR's L-band wavelength is about 24 centimeters. NASA describes L-band as able to penetrate further into dense forest canopy than shorter-wavelength S-band. Repeat-pass radar can support interferometric observations, but coherence, atmosphere, processing and reference choices still matter.”  
*Screen: point out the L-band, HH, acquisition-pair and provisional metadata.*

**0:45–1:10 — Real product and spatial check**  
“This demonstration uses the real NISAR L2 GUNW granule G4375022208-ASF. Its saved NASA CMR record identifies the provisional collection, and its download receipt retains the transfer size and checksum evidence. The standalone ASF Search utility's latest saved run failed before its catalog query, so I am showing the retained product CMR record rather than claiming a live search just succeeded. We checked the actual UMM footprint polygon against the WGS84 Kalka–Shimla railway geometry, and the geometries intersect. Footprint overlap is only a location check, not proof of valid pixels or movement.”  
*Screen: point to the granule ID, provenance and OSM route overlay.*

**1:10–1:45 — Radar evidence**  
“The raster previews come from the product's actual unwrapped phase in radians, coherence, connected-component labels and combined validity screen. Click the railway line to inspect the corresponding full-resolution source cell; the same cell's phase and quality values stay together as layers change. Phase is a radar observable, not a ground-displacement value. Coherence describes phase consistency, not how much the ground moved.”  
*Screen: switch through each layer, click one route location, and point to the source-cell table and local OSM-segment distance.*

**1:45–2:10 — Coverage result**  
“Using the projected OSM centerline and an all-touched 80-meter grid rasterization, 1,478 radar cells touch the route. Under our explicitly stated finite-phase, coherence-range, connected-component, subswath and anomaly screen, 1,471 pass and 7 fail: 99.53 percent. This is radar observability under that screen, not movement coverage, rail-track coverage, or a safety result. The grid is 80 meters, much coarser than the railway assets.”  
*Screen: point to the valid/invalid coverage summary.*

**2:10–2:25 — Limitations and next evidence**  
“Two blockers remain visible. The official product QA summary reports an identification-group failure, but the failed field and effect are not in the delivered QA files. The physical sign of this stored phase is unresolved, so we do not convert it to signed LOS displacement. This is provisional data, and no local date-matched GNSS validation is available. The next steps are to obtain the QA diagnostic, authoritative phase-sign evidence and suitable independent observations before any displacement analysis.”

## If something fails during the live demo

- If the evidence endpoint cannot read the local product, stop the raster walkthrough. Do not substitute a mock or synthetic image.
- If the CMR/sidecar or checksum evidence panel is incomplete, describe that provenance as unavailable instead of implying it is verified.
- If the display or network basemap fails, continue only with the actual local HDF5 evidence panel; the Radar Evidence raster itself is local. Do not claim a live CMR query ran during this demonstration.
- Keep the QA FAIL and unresolved phase-sign banners visible. Do not launch the Three-Lane processor for this product.
