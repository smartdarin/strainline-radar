"""Read documented NISAR L2 GUNW identification and grid metadata."""
from __future__ import annotations

from pathlib import Path
import math

import h5py
from backend.gunw_reader import validate_phase_units


ROOT = "/science/LSAR"
IDENT = f"{ROOT}/identification"
GRID = f"{ROOT}/GUNW/grids/frequencyA"


def _value(h5: h5py.File, path: str):
    if path not in h5:
        return None
    value = h5[path][()]
    if hasattr(value, "tolist"):
        value = value.tolist()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").rstrip("\x00")
    if isinstance(value, list):
        return [_value_scalar(v) for v in value]
    return _value_scalar(value)


def _value_scalar(value):
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace").rstrip("\x00")
    if hasattr(value, "item"):
        value = value.item()
    return value


def inspect_gunw(path: str | Path, polarization: str = "HH") -> dict:
    """Inspect a real product without interpreting phase sign or maturity."""
    if polarization not in {"HH", "VV"}:
        raise ValueError("Polarization must be HH or VV for this processor.")
    file_path = Path(path)
    if not file_path.is_file():
        raise ValueError("GUNW file does not exist.")
    with h5py.File(file_path, "r") as h5:
        phase_path = f"{GRID}/unwrappedInterferogram/{polarization}/unwrappedPhase"
        layer_group = f"{GRID}/unwrappedInterferogram/{polarization}"
        mask_path = f"{GRID}/unwrappedInterferogram/mask"
        required_layers = {"unwrapped_phase": phase_path,
                           "coherence": f"{layer_group}/coherenceMagnitude",
                           "connected_components": f"{layer_group}/connectedComponents",
                           "mask": mask_path,
                           "projection": f"{layer_group}/projection"}
        missing_layers = [key for key, dataset in required_layers.items() if dataset not in h5]
        if missing_layers:
            raise ValueError("HDF5 is missing required documented GUNW layers: " + ", ".join(missing_layers))
        phase = h5[phase_path]
        phase_units = validate_phase_units(phase)
        for key in ("coherence", "connected_components", "mask"):
            if h5[required_layers[key]].shape != phase.shape:
                raise ValueError(f"GUNW {key} layer dimensions do not match unwrapped phase.")
        projection = h5[required_layers["projection"]]
        epsg = projection.attrs.get("epsg_code")
        if epsg is None:
            raise ValueError("GUNW projection dataset has no documented epsg_code attribute.")
        epsg = int(_value_scalar(epsg))
        frequency = _value(h5, f"{GRID}/centerFrequency")
        if frequency is None or not math.isfinite(float(frequency)) or float(frequency) <= 0:
            raise ValueError("GUNW centerFrequency is missing or invalid.")
        try:
            phase_units = _value_scalar(phase_units)
        except Exception:
            phase_units = "unknown"
        identification = {
            "granule_id": "granuleId", "product_type": "productType",
            "product_version": "productVersion", "product_specification_version": "productSpecificationVersion",
            "track_number": "trackNumber", "frame_number": "frameNumber",
            "absolute_orbit_number": "absoluteOrbitNumber", "look_direction": "lookDirection",
            "orbit_pass_direction": "orbitPassDirection", "radar_band": "radarBand",
            "processing_datetime": "processingDateTime", "bounding_polygon_wkt": "boundingPolygon",
            "reference_start": "referenceZeroDopplerStartTime", "reference_end": "referenceZeroDopplerEndTime",
            "secondary_start": "secondaryZeroDopplerStartTime", "secondary_end": "secondaryZeroDopplerEndTime",
            "is_urgent_observation": "isUrgentObservation", "is_mixed_mode": "isMixedMode",
        }
        metadata = {key: _value(h5, f"{IDENT}/{dataset}") for key, dataset in identification.items()}
        metadata.update({
            "source_file_name": file_path.name,
            "source_file_size_bytes": file_path.stat().st_size,
            "polarization": polarization,
            "center_frequency_hz": float(frequency),
            "phase_dataset": phase_path,
            "phase_units": str(phase_units),
            "phase_shape": list(phase.shape),
            "projection_epsg": epsg,
            "x_spacing_m": _value(h5, f"{layer_group}/xCoordinateSpacing"),
            "y_spacing_m": _value(h5, f"{layer_group}/yCoordinateSpacing"),
            "coherence_dataset": required_layers["coherence"],
            "connected_components_dataset": required_layers["connected_components"],
            "mask_dataset": required_layers["mask"],
            "maturity_status": "not_in_hdf5; verify against the NASA CMR collection record",
            "phase_sign_status": "not_decided_by_inspector; verify the official phase/reference-secondary convention before interpreting signed movement",
            "status": "HDF5 structure inspected; site footprint and CMR identity match still required",
        })
        return metadata
