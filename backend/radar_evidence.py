"""Read-only data access for the StrainLine NISAR Radar Evidence Explorer.

This module only previews documented GUNW layers and returns cell values. It
does not perform a phase-to-displacement conversion or modify the product.
"""
from __future__ import annotations

import json
import math
import struct
import zlib
from pathlib import Path
from typing import Any

import h5py
import numpy as np
from pyproj import CRS, Transformer

from backend.gunw_qa import decode_gunw_mask
from backend.gunw_qa import inspect_gunw_quality
from backend.gunw_metadata import inspect_gunw

ROOT = Path(__file__).resolve().parents[1]
GRANULE_ID = (
    "NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_"
    "20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001"
)
PRODUCT = ROOT / "data" / "raw" / f"{GRANULE_ID}.h5"
SIDECAR = ROOT / "data" / "raw" / f"{GRANULE_ID}.h5.cmr.json"
ROUTE = ROOT / "StrainLine_Data" / "00_AOI" / "route" / "kalka_shimla_railway_osm_relation_331109.geojson"
BASE = "/science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram"
POLARIZATION = "HH"
FACTOR = 4

LAYER_PATHS = {
    "phase": f"{BASE}/{POLARIZATION}/unwrappedPhase",
    "coherence": f"{BASE}/{POLARIZATION}/coherenceMagnitude",
    "components": f"{BASE}/{POLARIZATION}/connectedComponents",
    "mask": f"{BASE}/mask",
}


def _required_paths() -> tuple[Path, Path, Path]:
    if not PRODUCT.is_file():
        raise FileNotFoundError("The selected real NISAR GUNW product is not present in data/raw.")
    if not SIDECAR.is_file():
        raise FileNotFoundError("The product CMR metadata sidecar is missing.")
    if not ROUTE.is_file():
        raise FileNotFoundError("The attributed Kalka–Shimla railway GeoJSON is missing.")
    return PRODUCT, SIDECAR, ROUTE


def _read_context() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    product, sidecar_path, route_path = _required_paths()
    metadata = inspect_gunw(product, POLARIZATION)
    if metadata.get("granule_id") != GRANULE_ID:
        raise ValueError("The local HDF5 embedded granule identity does not match the selected product.")
    sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    record = sidecar.get("cmr_record", {})
    if record.get("id") != "G4375022208-ASF":
        raise ValueError("The CMR sidecar identity does not match G4375022208-ASF.")
    cmr = record.get("umm", {})
    archive = cmr.get("DataGranule", {}).get("ArchiveAndDistributionInformation", [])
    asset = next((item for item in archive if item.get("Name") == product.name), {})
    route_json = json.loads(route_path.read_text(encoding="utf-8"))
    return metadata, {"record": record, "umm": cmr, "asset": asset, "receipt": sidecar.get("download_receipt", {})}, route_json


def _iter_lines(geojson: dict[str, Any]):
    def visit(value):
        if value.get("type") == "FeatureCollection":
            for feature in value.get("features", []):
                yield from visit(feature)
        elif value.get("type") == "Feature":
            yield from visit(value.get("geometry") or {})
        elif value.get("type") == "LineString":
            yield value.get("coordinates", [])
        elif value.get("type") == "MultiLineString":
            yield from value.get("coordinates", [])

    yield from visit(geojson)


def _route_preview_segments(route: dict[str, Any], epsg: int, x: np.ndarray, y: np.ndarray) -> list[list[list[float]]]:
    to_projected = Transformer.from_crs(4326, epsg, always_xy=True)
    dx, dy = float(x[1] - x[0]), float(y[1] - y[0])
    if dx == 0 or dy == 0:
        raise ValueError("GUNW coordinate grid has zero spacing.")
    result = []
    for line in _iter_lines(route):
        projected = [to_projected.transform(float(p[0]), float(p[1])) for p in line]
        pixels = [[(px - float(x[0])) / dx / FACTOR, (py - float(y[0])) / dy / FACTOR] for px, py in projected]
        if len(pixels) >= 2:
            result.append(pixels)
    return result


def get_evidence_info() -> dict[str, Any]:
    """Return verified local provenance and raster-grid presentation details."""
    metadata, context, route = _read_context()
    with h5py.File(PRODUCT, "r") as h5:
        x = h5[f"{BASE}/xCoordinates"][:]
        y = h5[f"{BASE}/yCoordinates"][:]
    sidecar_umm = context["umm"]
    collection = sidecar_umm.get("CollectionReference", {}).get("ShortName", "")
    maturity = "Provisional" if "PROVISIONAL" in collection.upper() else "Unverified"
    receipt = context["receipt"]
    asset = context["asset"]
    actual_bytes = PRODUCT.stat().st_size
    cmr_bytes = asset.get("SizeInBytes")
    qa = inspect_gunw_quality(PRODUCT, ROUTE)
    corridor_validity = qa["validity"]["common_valid_phase_coherence_cc_and_subswaths"]
    corridor_total = int(qa["corridor_raster_cells"])
    corridor_valid = int(corridor_validity["corridor_count"])
    return {
        "granule_id": metadata["granule_id"],
        "cmr_concept_id": context["record"]["id"],
        "collection": collection,
        "maturity": maturity,
        "reference_start": metadata["reference_start"],
        "reference_end": metadata["reference_end"],
        "secondary_start": metadata["secondary_start"],
        "secondary_end": metadata["secondary_end"],
        "polarization": metadata["polarization"],
        "radar_band": metadata["radar_band"],
        "frequency": "A",
        "orbit_pass_direction": metadata["orbit_pass_direction"],
        "absolute_orbit_number": metadata["absolute_orbit_number"],
        "track_number": metadata["track_number"],
        "frame_number": metadata["frame_number"],
        "look_direction": metadata["look_direction"],
        "projection_epsg": metadata["projection_epsg"],
        "grid_resolution_m": {"x": abs(float(metadata["x_spacing_m"])), "y": abs(float(metadata["y_spacing_m"]))},
        "shape": metadata["phase_shape"],
        "phase_units": metadata["phase_units"],
        "phase_dataset": metadata["phase_dataset"],
        "qa_identification_status": "FAIL",
        "qa_identification_message": "QA_SUMMARY reports an identification-group failure; the field-level QA log is not included in the CMR file manifest.",
        "phase_sign_status": "Unresolved: the physical toward/away LOS sign is not established.",
        "provenance": {
            "filename": PRODUCT.name,
            "actual_size_bytes": actual_bytes,
            "cmr_size_bytes": cmr_bytes,
            "size_matches_cmr": actual_bytes == cmr_bytes,
            "hdf5_readable": True,
            "granule_identity_matches": metadata["granule_id"] == GRANULE_ID,
            "cmr_md5": asset.get("Checksum", {}).get("Value"),
            "cmr_checksum_algorithm": asset.get("Checksum", {}).get("Algorithm"),
            "sha256_recorded": receipt.get("sha256"),
            "sha256_receipt_matches_phase4_record": receipt.get("sha256") == "459e67aaf84207f68a5b825c825c4d36952ac709168f636e06f3da95192bf9f2",
            "attribution": "NASA/ASF NISAR GUNW; railway geometry © OpenStreetMap contributors (OSM relation 331109).",
        },
        "preview": {"width": int(math.ceil(len(x) / FACTOR)), "height": int(math.ceil(len(y) / FACTOR)), "sample_factor": FACTOR},
        "route_segments": _route_preview_segments(route, int(metadata["projection_epsg"]), x, y),
        "route_coverage": {
            "method": "OSM centerline rasterized with all_touched=True against actual GUNW grid",
            "route_length_m": qa["route_length_m"],
            "cells_total": corridor_total,
            "cells_valid": corridor_valid,
            "cells_invalid": corridor_total - corridor_valid,
            "valid_percent": corridor_valid / corridor_total * 100 if corridor_total else 0.0,
        },
        "limitations": [
            "Displayed colors encode phase in radians, not displacement or toward/away motion.",
            "The physical LOS phase sign is unresolved; no phase-to-displacement conversion is performed.",
            "This is one provisional 12-day interferometric pair and cannot establish a trend.",
            "80 m grid spacing is not railway asset scale; the railway line is a geometry overlay, not a ground-motion measurement.",
            "QA identification-group failure remains unexplained; exact failed field and effect are unavailable in delivered QA files.",
            "The displayed SHA-256 is the recorded Phase 2 download receipt; this viewer does not re-hash the 2.3 GB file on every page load.",
            "Atmospheric, ionospheric, orbital, unwrapping, decorrelation, and reference-area effects remain relevant.",
            "No safe/unsafe, damage, or vertical-settlement conclusion is produced.",
        ],
    }


def _rgb_for_layer(layer: str, values: np.ndarray, phase_valid: np.ndarray | None = None) -> tuple[np.ndarray, float | None, float | None]:
    values = np.asarray(values)
    h, w = values.shape
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    low: float | None = None
    high: float | None = None
    if layer == "phase":
        valid = np.isfinite(values)
        if valid.any():
            low, high = (float(v) for v in np.nanpercentile(values[valid], [2, 98]))
            if high <= low:
                high = low + 1.0
            t = np.clip((np.nan_to_num(values, nan=low) - low) / (high - low), 0, 1)
            # Sequential, non-cyclic ramp: it displays numeric phase only and
            # intentionally does not imply a toward/away direction.
            stops = np.array([[24, 43, 74], [34, 113, 139], [108, 183, 143], [241, 208, 93]], dtype=float)
            scaled = t * (len(stops) - 1)
            left = np.floor(scaled).astype(int).clip(0, len(stops) - 2)
            frac = (scaled - left)[..., None]
            rgb = np.rint(stops[left] * (1 - frac) + stops[left + 1] * frac).astype(np.uint8)
            rgb[~valid] = (35, 39, 42)
    elif layer == "coherence":
        valid = np.isfinite(values) & (values >= 0) & (values <= 1)
        t = np.clip(np.nan_to_num(values, nan=0.0), 0, 1)
        stops = np.array([[36, 44, 78], [39, 123, 142], [115, 189, 129], [248, 224, 86]], dtype=float)
        scaled = t * (len(stops) - 1)
        left = np.floor(scaled).astype(int).clip(0, len(stops) - 2)
        frac = (scaled - left)[..., None]
        rgb = np.rint(stops[left] * (1 - frac) + stops[left + 1] * frac).astype(np.uint8)
        rgb[~valid] = (35, 39, 42)
        low, high = 0.0, 1.0
    elif layer == "components":
        fill = values == 65535
        valid = (values != 0) & ~fill
        rgb[~valid] = (47, 51, 57)
        rgb[valid] = (63, 167, 132)
        rgb[fill] = (196, 71, 127)
        if valid.any():
            low, high = float(np.min(values[valid])), float(np.max(values[valid]))
    elif layer == "validity":
        valid = np.asarray(values, dtype=bool)
        rgb[valid] = (62, 166, 131)
        rgb[~valid] = (53, 58, 63)
        low, high = 0.0, 1.0
    else:
        raise ValueError("Unsupported radar evidence layer.")
    return rgb, low, high


def _png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


def _encode_png(rgb: np.ndarray) -> bytes:
    height, width, _ = rgb.shape
    raw = b"".join(b"\x00" + rgb[row].tobytes() for row in range(height))
    header = struct.pack(">2I5B", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + _png_chunk(b"IHDR", header) + _png_chunk(b"IDAT", zlib.compress(raw, 6)) + _png_chunk(b"IEND", b"")


def render_preview(layer: str) -> tuple[bytes, dict[str, str]]:
    """Render a decimated false-color preview from real HDF5 cells."""
    if layer not in {"phase", "coherence", "components", "validity"}:
        raise ValueError("Choose phase, coherence, components, or validity.")
    product, _, _ = _required_paths()
    with h5py.File(product, "r") as h5:
        phase_ds = h5[LAYER_PATHS["phase"]]
        selection = (slice(None, None, FACTOR), slice(None, None, FACTOR))
        if layer == "validity":
            phase = phase_ds[selection]
            coherence = h5[LAYER_PATHS["coherence"]][selection]
            components = h5[LAYER_PATHS["components"]][selection]
            mask_ds = h5[LAYER_PATHS["mask"]]
            mask = mask_ds[selection].astype(np.uint32)
            decoded = decode_gunw_mask(mask, int(mask_ds.attrs.get("_FillValue", 255)))
            values = (
                np.isfinite(phase) & np.isfinite(coherence) & (coherence >= 0) & (coherence <= 1)
                & (components != 0) & (components != int(h5[LAYER_PATHS["components"]].attrs.get("_FillValue", 65535)))
                & decoded["both_subswaths_valid"] & decoded["reference_anomaly_clear"] & decoded["secondary_anomaly_clear"]
            )
        else:
            values = h5[LAYER_PATHS[layer]][selection]
    rgb, low, high = _rgb_for_layer(layer, values)
    headers = {"X-Radar-Layer": layer, "X-Sample-Factor": str(FACTOR), "X-Preview-Width": str(rgb.shape[1]), "X-Preview-Height": str(rgb.shape[0])}
    if low is not None and high is not None:
        headers["X-Value-Min"] = f"{low:.7g}"
        headers["X-Value-Max"] = f"{high:.7g}"
    return _encode_png(rgb), headers


def sample_cell(row: int, col: int) -> dict[str, Any]:
    """Read one actual source-grid cell; values are not displacement."""
    product, _, _ = _required_paths()
    with h5py.File(product, "r") as h5:
        phase_ds = h5[LAYER_PATHS["phase"]]
        height, width = phase_ds.shape
        if row < 0 or col < 0 or row >= height or col >= width:
            raise IndexError("The requested radar cell is outside the GUNW grid.")
        phase = float(phase_ds[row, col])
        coherence = float(h5[LAYER_PATHS["coherence"]][row, col])
        cc_ds = h5[LAYER_PATHS["components"]]
        component = int(cc_ds[row, col])
        mask_ds = h5[LAYER_PATHS["mask"]]
        mask = int(mask_ds[row, col])
        decoded = decode_gunw_mask(np.asarray([[mask]], dtype=np.uint32), int(mask_ds.attrs.get("_FillValue", 255)))
        valid = bool(
            math.isfinite(phase) and math.isfinite(coherence) and 0 <= coherence <= 1
            and component != 0 and component != int(cc_ds.attrs.get("_FillValue", 65535))
            and decoded["both_subswaths_valid"][0, 0]
            and decoded["reference_anomaly_clear"][0, 0]
            and decoded["secondary_anomaly_clear"][0, 0]
        )
        x = float(h5[f"{BASE}/xCoordinates"][col])
        y = float(h5[f"{BASE}/yCoordinates"][row])
        epsg = int(h5[f"{BASE}/{POLARIZATION}/projection"].attrs["epsg_code"])
    to_wgs84 = Transformer.from_crs(CRS.from_epsg(epsg), CRS.from_epsg(4326), always_xy=True)
    longitude, latitude = to_wgs84.transform(x, y)
    return {
        "row": row, "column": col, "x_m": x, "y_m": y,
        "projection_epsg": epsg,
        "longitude": float(longitude), "latitude": float(latitude),
        "phase_radians": phase if math.isfinite(phase) else None,
        "coherence": coherence if math.isfinite(coherence) else None,
        "connected_component": component,
        "raw_mask": mask,
        "validity_screen": valid,
        "interpretation": "Radar phase in radians and quality-layer values only; no displacement conversion.",
    }


def locate_route_cell(row: int, col: int) -> dict[str, Any]:
    """Inspect the clicked source cell and report its nearest OSM segment distance.

    Distance is local to one GeoJSON LineString because the relation is stored
    as 231 separate OSM way geometries; it is not an official railway km post.
    """
    sample = sample_cell(row, col)
    _, _, route = _read_context()
    epsg = int(sample["projection_epsg"]) if "projection_epsg" in sample else None
    if epsg is None:
        with h5py.File(PRODUCT, "r") as h5:
            epsg = int(h5[f"{BASE}/{POLARIZATION}/projection"].attrs["epsg_code"])
    px, py = sample["x_m"], sample["y_m"]
    best: tuple[float, int, float] | None = None
    to_projected = Transformer.from_crs(4326, epsg, always_xy=True)
    for segment_index, line in enumerate(_iter_lines(route), start=1):
        projected = [to_projected.transform(float(p[0]), float(p[1])) for p in line]
        cumulative = 0.0
        for a, b in zip(projected, projected[1:]):
            vx, vy = b[0] - a[0], b[1] - a[1]
            length_sq = vx * vx + vy * vy
            t = 0.0 if length_sq == 0 else max(0.0, min(1.0, ((px - a[0]) * vx + (py - a[1]) * vy) / length_sq))
            qx, qy = a[0] + t * vx, a[1] + t * vy
            distance = math.hypot(px - qx, py - qy)
            along = cumulative + t * math.sqrt(length_sq)
            if best is None or distance < best[0]:
                best = (distance, segment_index, along)
            cumulative += math.sqrt(length_sq)
    if best is None:
        raise ValueError("The saved railway geometry contains no line segments.")
    sample.update({
        "route_segment": best[1],
        "distance_along_segment_m": best[2],
        "distance_to_railway_m": best[0],
        "chainage_qualification": "Distance along the nearest mapped OSM way segment; not an official railway chainage.",
    })
    return sample
