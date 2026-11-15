"""Read-only quality summaries for geocoded NISAR GUNW products.

This module reports coverage and validity only. It does not convert phase to
displacement or alter any scientific processing products.
"""

from __future__ import annotations

import json
from pathlib import Path

import h5py
import numpy as np
from affine import Affine
from pyproj import CRS, Transformer
from rasterio.features import rasterize
from shapely.geometry import shape
from shapely import transform as transform_geometry


def decode_gunw_mask(mask: np.ndarray, fill_value: int = 255) -> dict[str, np.ndarray]:
    """Decode GUNW's decimal subswath digits and byte anomaly flags.

    In bits 0-7 the product stores a decimal-coded water/reference-swath/
    secondary-swath value. Bytes 8-23 carry secondary/reference anomaly flags;
    bit 24 is the ionosphere phase mask.
    """
    values = np.asarray(mask, dtype=np.uint32)
    low_byte = values & 0xFF
    water = low_byte // 100
    reference_swath = (low_byte // 10) % 10
    secondary_swath = low_byte % 10
    fill = values == fill_value
    return {
        "not_fill": ~fill,
        "water": water == 1,
        "reference_swath": reference_swath,
        "secondary_swath": secondary_swath,
        "both_subswaths_valid": (~fill) & (reference_swath > 0) & (secondary_swath > 0),
        "reference_anomaly_clear": ((values >> 16) & 0xFF) == 0,
        "secondary_anomaly_clear": ((values >> 8) & 0xFF) == 0,
        "ionosphere_phase_masked": ((values >> 24) & 1) != 0,
    }


def _project_route(route_path: Path, epsg: int):
    data = json.loads(route_path.read_text(encoding="utf-8"))
    features = data.get("features", [])
    if not features:
        raise ValueError("Route GeoJSON has no features")
    geometries = [shape(feature["geometry"]) for feature in features]
    from shapely import union_all

    route = union_all(geometries)
    transformer = Transformer.from_crs(CRS.from_epsg(4326), CRS.from_epsg(epsg), always_xy=True)
    return transform_geometry(route, transformer.transform, interleaved=False)


def inspect_gunw_quality(product_path: str | Path, route_geojson: str | Path) -> dict:
    """Summarize the GUNW layers and route support without modifying inputs."""
    product_path = Path(product_path)
    route_geojson = Path(route_geojson)
    base = "/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"
    layer = f"{base}/HH"

    with h5py.File(product_path, "r") as h5:
        phase_ds = h5[f"{layer}/unwrappedPhase"]
        coh_ds = h5[f"{layer}/coherenceMagnitude"]
        cc_ds = h5[f"{layer}/connectedComponents"]
        mask_ds = h5[f"{base}/mask"]
        phase = phase_ds[:]
        coherence = coh_ds[:]
        components = cc_ds[:]
        mask = mask_ds[:]
        x = h5[f"{base}/xCoordinates"][:]
        y = h5[f"{base}/yCoordinates"][:]
        epsg = int(h5[f"{base}/projection"].attrs["epsg_code"])
        fill = int(mask_ds.attrs.get("_FillValue", 255))

    if not (phase.shape == coherence.shape == components.shape == mask.shape == (len(y), len(x))):
        raise ValueError("GUNW QA layer dimensions do not match the coordinate grid")
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    affine = Affine(dx, 0, float(x[0] - dx / 2), 0, dy, float(y[0] - dy / 2))
    route = _project_route(route_geojson, epsg)
    corridor = rasterize(
        [(route, 1)], out_shape=phase.shape, transform=affine,
        all_touched=True, dtype="uint8",
    ).astype(bool)
    if not corridor.any():
        raise ValueError("Railway GeoJSON does not intersect the GUNW raster grid")

    decoded = decode_gunw_mask(mask, fill)
    finite_phase = np.isfinite(phase)
    finite_coherence = np.isfinite(coherence) & (coherence >= 0) & (coherence <= 1)
    cc_valid = (components != 0) & (components != int(cc_ds_fill(product_path, layer)))
    common_valid = (
        finite_phase & finite_coherence & cc_valid & decoded["both_subswaths_valid"]
        & decoded["reference_anomaly_clear"] & decoded["secondary_anomaly_clear"]
    )

    def counts(selection: np.ndarray) -> dict[str, int | float]:
        return {
            "count": int(selection.sum()),
            "percent_of_grid": float(selection.mean() * 100),
            "corridor_count": int((selection & corridor).sum()),
            "corridor_percent": float((selection & corridor).sum() / corridor.sum() * 100),
        }

    finite_coh_values = coherence[np.isfinite(coherence)]
    return {
        "shape": list(phase.shape),
        "epsg": epsg,
        "spacing_m": {"x": dx, "y": dy},
        "route_length_m": float(route.length),
        "corridor_raster_cells": int(corridor.sum()),
        "validity": {
            "finite_phase": counts(finite_phase),
            "finite_coherence_0_to_1": counts(finite_coherence),
            "connected_component_nonzero_and_not_fill": counts(cc_valid),
            "both_subswaths_valid": counts(decoded["both_subswaths_valid"]),
            "common_valid_phase_coherence_cc_and_subswaths": counts(common_valid),
        },
        "coherence": {
            "min": float(finite_coh_values.min()),
            "max": float(finite_coh_values.max()),
            "mean": float(finite_coh_values.mean()),
            "std": float(finite_coh_values.std()),
            "corridor_percentiles": [
                float(v) for v in np.nanpercentile(coherence[corridor], [0, 10, 25, 50, 75, 90, 100])
            ],
            "common_valid_corridor_percent_by_threshold": {
                str(threshold): float((common_valid & corridor & (coherence >= threshold)).sum() / corridor.sum() * 100)
                for threshold in (0.2, 0.3, 0.4, 0.5, 0.6, 0.7)
            },
        },
        "connected_components": {
            str(int(label)): int(count)
            for label, count in zip(*np.unique(components, return_counts=True))
        },
        "mask": {
            "fill_value": fill,
            "unique_values": {
                str(int(value)): int(count)
                for value, count in zip(*np.unique(mask, return_counts=True))
            },
            "water_pixel_count": int(decoded["water"].sum()),
            "reference_anomaly_flag_pixel_count": int((~decoded["reference_anomaly_clear"]).sum()),
            "secondary_anomaly_flag_pixel_count": int((~decoded["secondary_anomaly_clear"]).sum()),
            "ionosphere_phase_masked_pixel_count": int(decoded["ionosphere_phase_masked"].sum()),
        },
    }


def cc_ds_fill(product_path: Path, layer: str) -> int:
    with h5py.File(product_path, "r") as h5:
        return int(h5[f"{layer}/connectedComponents"].attrs.get("_FillValue", 65535))
