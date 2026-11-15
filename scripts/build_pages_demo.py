"""Export actual, read-only NISAR evidence for a static GitHub Pages demo.

The export contains decimated images rendered by the existing Radar Evidence
reader and exact source-cell samples touched by the existing railway rasterization
screen. It never calculates displacement or edits the source HDF5.
"""
from __future__ import annotations

import json
import hashlib
import sys
import zipfile
from pathlib import Path

import h5py
import numpy as np
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.features import rasterize

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.gunw_qa import decode_gunw_mask, inspect_gunw_quality, _project_route
from backend.radar_evidence import (
    BASE,
    FACTOR,
    LAYER_PATHS,
    PRODUCT,
    ROUTE,
    get_evidence_info,
    render_preview,
)

OUT = ROOT / "docs" / "data"
ARCHIVE = ROOT / "data" / "strainline_deployment_evidence.zip"


def _route_cells() -> tuple[list[dict], tuple[int, int]]:
    """Export actual full-resolution cells touched by the documented route screen."""
    qa_summary = inspect_gunw_quality(PRODUCT, ROUTE)
    with h5py.File(PRODUCT, "r") as h5:
        phase_ds = h5[LAYER_PATHS["phase"]]
        grid_shape = phase_ds.shape
        coherence_ds = h5[LAYER_PATHS["coherence"]]
        components_ds = h5[LAYER_PATHS["components"]]
        mask_ds = h5[LAYER_PATHS["mask"]]
        x = h5[f"{BASE}/xCoordinates"][:]
        y = h5[f"{BASE}/yCoordinates"][:]
        epsg = int(h5[f"{BASE}/projection"].attrs["epsg_code"])
        component_fill = int(components_ds.attrs.get("_FillValue", 65535))
        mask_fill = int(mask_ds.attrs.get("_FillValue", 255))
        dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
        transform = Affine(dx, 0, float(x[0] - dx / 2), 0, dy, float(y[0] - dy / 2))
        route = _project_route(ROUTE, epsg)
        route_lines = []
        to_projected_route = Transformer.from_crs(4326, epsg, always_xy=True)
        from backend.radar_evidence import _iter_lines
        route_geojson = json.loads(ROUTE.read_text(encoding="utf-8"))
        for segment_number, line in enumerate(_iter_lines(route_geojson), start=1):
            projected_line = [to_projected_route.transform(float(point[0]), float(point[1])) for point in line]
            if len(projected_line) >= 2:
                route_lines.append((segment_number, projected_line))
        touched = rasterize(
            [(route, 1)], out_shape=phase_ds.shape, transform=transform,
            all_touched=True, dtype="uint8",
        ).astype(bool)
        rows, cols = np.where(touched)
        to_wgs84 = Transformer.from_crs(CRS.from_epsg(epsg), CRS.from_epsg(4326), always_xy=True)
        longitudes, latitudes = to_wgs84.transform(x[cols], y[rows])

        result: list[dict] = []
        for row in np.unique(rows):
            idx = np.flatnonzero(rows == row)
            row_cols = cols[idx]
            phase = phase_ds[int(row), row_cols].astype(np.float64)
            coherence = coherence_ds[int(row), row_cols].astype(np.float64)
            components = components_ds[int(row), row_cols].astype(np.uint32)
            mask = mask_ds[int(row), row_cols].astype(np.uint32)
            decoded = decode_gunw_mask(mask, mask_fill)
            valid = (
                np.isfinite(phase) & np.isfinite(coherence) & (coherence >= 0) & (coherence <= 1)
                & (components != 0) & (components != component_fill)
                & decoded["both_subswaths_valid"]
                & decoded["reference_anomaly_clear"]
                & decoded["secondary_anomaly_clear"]
            )
            for local, original_idx in enumerate(idx):
                px, py = float(x[row_cols[local]]), float(y[int(row)])
                nearest = None
                for segment_number, line in route_lines:
                    cumulative = 0.0
                    for a, b in zip(line, line[1:]):
                        vx, vy = b[0] - a[0], b[1] - a[1]
                        length_sq = vx * vx + vy * vy
                        length = float(np.sqrt(length_sq))
                        t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / length_sq))
                        distance = float(np.hypot(px - (a[0] + t * vx), py - (a[1] + t * vy)))
                        if nearest is None or distance < nearest[0]:
                            nearest = (distance, segment_number, cumulative + t * length)
                        cumulative += length
                result.append({
                    "row": int(row),
                    "column": int(row_cols[local]),
                    "preview_row": float(row) / FACTOR,
                    "preview_column": float(row_cols[local]) / FACTOR,
                    "longitude": float(longitudes[original_idx]),
                    "latitude": float(latitudes[original_idx]),
                    "x_m": float(x[row_cols[local]]),
                    "y_m": float(y[int(row)]),
                    "phase_radians": float(phase[local]) if np.isfinite(phase[local]) else None,
                    "coherence": float(coherence[local]) if np.isfinite(coherence[local]) else None,
                    "connected_component": int(components[local]),
                    "raw_mask": int(mask[local]),
                    "passes_screen": bool(valid[local]),
                    "route_segment": nearest[1] if nearest else None,
                    "distance_along_segment_m": nearest[2] if nearest else None,
                    "distance_to_railway_m": nearest[0] if nearest else None,
                    "chainage_qualification": "Distance along nearest mapped OSM way segment; not official railway chainage.",
                })

    expected_total = int(qa_summary["corridor_raster_cells"])
    expected_valid = int(qa_summary["validity"]["common_valid_phase_coherence_cc_and_subswaths"]["corridor_count"])
    if len(result) != expected_total:
        raise RuntimeError(f"Route-cell export has {len(result)} cells; existing QA summary has {expected_total}.")
    if sum(cell["passes_screen"] for cell in result) != expected_valid:
        raise RuntimeError("Exported source-cell validity count does not match the existing QA summary.")
    return result, grid_shape


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    info = get_evidence_info()
    if info["granule_id"] != "NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001":
        raise RuntimeError("Unexpected GUNW granule identity; refusing static export.")
    layer_ranges = {}
    for layer in ("phase", "coherence", "components", "validity"):
        payload, headers = render_preview(layer)
        (OUT / f"{layer}.png").write_bytes(payload)
        layer_ranges[layer] = {"minimum": headers.get("X-Value-Min"), "maximum": headers.get("X-Value-Max")}
    cells, shape = _route_cells()
    export = {
        "provenance": "Actual NISAR GUNW HDF5 and matching CMR sidecar; no synthetic observations.",
        "grid_shape": [int(shape[0]), int(shape[1])],
        "sample_factor": FACTOR,
        "preview_layer_ranges": layer_ranges,
        "evidence": info,
        "railway_cells": cells,
    }
    (OUT / "evidence.json").write_text(json.dumps(export, separators=(",", ":")), encoding="utf-8")
    manifest = {
        "source_granule": info["granule_id"],
        "source_cmr_concept_id": info["cmr_concept_id"],
        "source_sha256_from_download_receipt": info["provenance"]["sha256_recorded"],
        "source_hdf5_not_included": True,
        "railway_cells": len(cells),
        "passing_cells": sum(cell["passes_screen"] for cell in cells),
        "artifacts": {},
    }
    for path in sorted(OUT.iterdir()):
        if path.is_file() and path.name != "manifest.json":
            manifest["artifacts"][path.name] = {"size_bytes": path.stat().st_size, "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    ARCHIVE.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ARCHIVE, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(OUT.iterdir()):
            if path.is_file():
                archive.write(path, arcname=path.name)
    print(json.dumps({
        "granule_id": info["granule_id"],
        "cells": len(cells),
        "valid_cells": sum(cell["passes_screen"] for cell in cells),
        "preview_pixels": info["preview"],
        "output": str(OUT.relative_to(ROOT)),
        "package_bytes": sum(path.stat().st_size for path in OUT.iterdir() if path.is_file()),
        "zip_bytes": ARCHIVE.stat().st_size,
    }))


if __name__ == "__main__":
    main()
