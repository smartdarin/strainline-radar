# Run NISAR GUNW discovery

The search utility is metadata-only and never downloads HDF5 products. Run from the StrainLine project root in PowerShell.

```powershell
.\.venv\Scripts\python.exe -m pip install -r StrainLine_Data\requirements-search.txt
.\.venv\Scripts\python.exe StrainLine_Data\13_Metadata_Notes\discover_nisar_gunw.py --fetch-osm-route
```

`--fetch-osm-route` retrieves the Kalka–Shimla railway relation (OSM relation 331109), writes attributed WGS84 GeoJSON under `StrainLine_Data\00_AOI\route`, then searches ASF separately for validated and provisional NISAR L-band GUNW. The search uses the route's 1 km buffer for catalog discovery and exact route-centerline intersection to classify records.

Authentication first checks the user’s standard `.netrc` / Windows `_netrc` for `urs.earthdata.nasa.gov`. If no credentials are found, the script prompts for username and a non-echoed password; it does not write credentials. If you already have the route GeoJSON, skip route retrieval and pass it with `--route path\to\route.geojson`.

Outputs are written to `StrainLine_Data\13_Metadata_Notes\nisar_gunw_search_results.csv` and `nisar_gunw_product_metadata_report.md`. Review matching rows and the report before selecting anything. No product download command is implemented in this script; an HDF5 download requires a separate explicit approval and workflow.

The archived run on 2026-11-14 could not resolve `api.openstreetmap.org`, so neither route retrieval nor ASF searches ran; its CSV contains only a header and its report is marked `NOT SEARCHED`. This script run is not the evidence for the locally selected G4375022208-ASF product. The saved product CMR sidecar and verified transfer receipt are the provenance artifacts for the current read-only Radar Evidence demonstration. Retry this metadata-only search when DNS/network access is available and retain a new successful run record separately.
