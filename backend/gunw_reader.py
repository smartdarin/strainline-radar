#!/usr/bin/env python3
"""Sample a NISAR L2 GUNW unwrapped-phase layer along one GeoJSON centerline.

This produces a quality-screened, phase-derived LOS range-change profile. It
does not correct atmospheric/tropospheric delays, validate the sign convention,
infer vertical settlement, estimate engineering risk, or certify asset safety.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import h5py
    import numpy as np
    from pyproj import CRS, Transformer
    from shapely.geometry import LineString, shape
    from shapely.ops import transform as transform_geometry
except ImportError as exc:  # pragma: no cover - runtime message only
    print(f"Missing dependency: {exc.name}. Install requirements.txt first.", file=sys.stderr)
    raise SystemExit(2)


@dataclass
class Sample:
    distance_m: float
    easting_m: float
    northing_m: float
    phase_rad: float | None
    coherence: float | None
    mask_value: int | None
    reference_subswath: int | None
    secondary_subswath: int | None
    connected_component: int | None
    los_range_change_proxy_mm: float | None
    ionosphere_phase_rad: float | None
    ionosphere_sigma_rad: float | None
    ionosphere_sigma_range_mm: float | None
    status: str
    window_end_distance_m: float | None = None
    differential_range_change_proxy_mm: float | None = None
    gradient_magnitude_mm_per_m: float | None = None
    ionosphere_only_95_lower_mm: float | None = None
    ionosphere_only_95_upper_mm: float | None = None
    window_status: str = "not_evaluated"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create an along-corridor profile from a NISAR L2 GUNW HDF5 granule."
    )
    parser.add_argument("--gunw", required=True, type=Path, help="NISAR L2 GUNW .h5/.he5 file")
    parser.add_argument("--centerline", required=True, type=Path, help="WGS84 GeoJSON LineString")
    parser.add_argument("--output", required=True, type=Path, help="Output profile CSV")
    parser.add_argument("--polarization", choices=("HH", "VV"), default="HH")
    parser.add_argument("--min-coherence", type=float, required=True, help="Explicit quality-screen threshold, 0–1")
    parser.add_argument("--spacing-m", type=float, default=80.0, help="Centerline sample interval in metres (default: 80)")
    parser.add_argument("--window-m", type=float, default=400.0, help="Differential window in metres (default: 400)")
    parser.add_argument("--metadata", type=Path, help="Provenance JSON path (default: CSV name plus .provenance.json)")
    args = parser.parse_args()
    if not 0 <= args.min_coherence <= 1:
        parser.error("--min-coherence must be between 0 and 1")
    if args.spacing_m <= 0 or args.window_m < 2 * args.spacing_m:
        parser.error("--spacing-m must be positive and --window-m must span at least two sample intervals")
    if not args.gunw.is_file():
        parser.error(f"GUNW file not found: {args.gunw}")
    if not args.centerline.is_file():
        parser.error(f"GeoJSON file not found: {args.centerline}")
    return args


def load_centerline(path: Path) -> LineString:
    document = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise ValueError("GeoJSON root must be a Feature, FeatureCollection, or LineString object.")
    if document.get("type") == "FeatureCollection":
        features = document.get("features", [])
        geometries = [feature.get("geometry") for feature in features if feature.get("geometry")]
    elif document.get("type") == "Feature":
        geometries = [document.get("geometry")]
    else:
        geometries = [document]
    lines = [shape(geometry) for geometry in geometries if geometry and geometry.get("type") == "LineString"]
    if len(lines) != 1 or not isinstance(lines[0], LineString):
        raise ValueError("Provide exactly one GeoJSON LineString in WGS84 longitude/latitude coordinates.")
    line = lines[0]
    if line.is_empty or len(line.coords) < 2 or not line.is_valid or line.length == 0:
        raise ValueError("The GeoJSON centerline must contain at least two valid, distinct coordinates.")
    for longitude, latitude, *_ in line.coords:
        if not (-180 <= longitude <= 180 and -90 <= latitude <= 90):
            raise ValueError("Centerline coordinates must be WGS84 longitude/latitude (EPSG:4326).")
    return line


def dataset_paths(h5: h5py.File, polarization: str) -> tuple[str, str, str]:
    candidates: list[str] = []

    def visit(name: str, obj: Any) -> None:
        if isinstance(obj, h5py.Dataset) and name.endswith("/unwrappedPhase"):
            candidates.append("/" + name)

    h5.visititems(visit)
    matches = [path for path in candidates if f"/{polarization}/unwrappedPhase" in path]
    if len(matches) != 1:
        raise ValueError(f"Expected one {polarization} unwrappedPhase dataset; found {len(matches)}.")
    phase_path = matches[0]
    group_path = phase_path.rsplit("/", 1)[0]
    mask_path = group_path.rsplit("/", 1)[0] + "/mask"
    required = [f"{group_path}/coherenceMagnitude", f"{group_path}/connectedComponents", f"{group_path}/xCoordinates", f"{group_path}/yCoordinates", f"{group_path}/projection", mask_path]
    missing = [path for path in required if path not in h5]
    if missing:
        raise ValueError("GUNW is missing required georeferencing or quality datasets: " + ", ".join(missing))
    return phase_path, group_path, mask_path


def scalar_value(dataset: h5py.Dataset) -> Any:
    value = dataset[()]
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if hasattr(value, "item"):
        return value.item()
    return value


def is_fill_value(dataset: h5py.Dataset, value: float | int) -> bool:
    """Compare a scalar sample with common HDF5/NetCDF fill-value attributes."""
    for key in ("_FillValue", "fillValue", "missing_value"):
        if key not in dataset.attrs:
            continue
        fill_values = np.asarray(dataset.attrs[key]).reshape(-1)
        for fill in fill_values:
            try:
                fill_number = float(fill)
            except (TypeError, ValueError):
                continue
            if math.isnan(fill_number):
                if math.isnan(float(value)):
                    return True
            elif float(value) == fill_number:
                return True
    return False


def get_epsg(projection: h5py.Dataset) -> int:
    for key in ("epsg_code", "epsg"):
        if key in projection.attrs:
            return int(np.asarray(projection.attrs[key]).item())
    return int(np.asarray(projection[()]).item())


def get_center_frequency(h5: h5py.File) -> tuple[str, float]:
    matches: list[str] = []

    def visit(name: str, obj: Any) -> None:
        if isinstance(obj, h5py.Dataset) and name.endswith("/frequencyA/centerFrequency") and "/GUNW/grids/" in name:
            matches.append("/" + name)

    h5.visititems(visit)
    if len(matches) != 1:
        raise ValueError(f"Expected one GUNW frequencyA centerFrequency dataset; found {len(matches)}.")
    path = matches[0]
    frequency = float(scalar_value(h5[path]))
    if not math.isfinite(frequency) or frequency <= 0:
        raise ValueError("GUNW center frequency is invalid.")
    return path, frequency


def phase_to_range_change_mm(phase_rad: float, center_frequency_hz: float) -> float:
    """Convert interferometric phase to a phase-derived LOS range proxy in mm."""
    if not math.isfinite(phase_rad) or not math.isfinite(center_frequency_hz) or center_frequency_hz <= 0:
        raise ValueError("Phase and center frequency must be finite; frequency must be positive.")
    wavelength_m = 299_792_458.0 / center_frequency_hz
    return phase_rad * wavelength_m * 1000.0 / (4.0 * math.pi)


def validate_phase_units(dataset: h5py.Dataset) -> str:
    """Require the GUNW phase layer to declare radians before conversion."""
    units = dataset.attrs.get("units")
    if isinstance(units, bytes):
        units = units.decode("utf-8", errors="replace")
    normalized = str(units or "").strip().lower()
    if normalized not in {"rad", "radian", "radians"}:
        raise ValueError(f"Unwrapped phase units must be declared in radians; found {normalized or 'missing'}.")
    return normalized


def nearest_axis_index(axis: np.ndarray, value: float) -> int | None:
    if axis.ndim != 1 or len(axis) < 2 or not np.all(np.isfinite(axis)):
        raise ValueError("GUNW x/y coordinate vectors must be finite 1D arrays with at least two values.")
    differences = np.diff(axis)
    ascending = bool(np.all(differences > 0))
    descending = bool(np.all(differences < 0))
    if not (ascending or descending):
        raise ValueError("GUNW coordinate vectors are not strictly monotonic.")
    ordered = axis if ascending else axis[::-1]
    index = int(np.searchsorted(ordered, value))
    choices = [candidate for candidate in (index - 1, index) if 0 <= candidate < len(ordered)]
    if not choices:
        return None
    best = min(choices, key=lambda candidate: abs(float(ordered[candidate]) - value))
    original = best if ascending else len(axis) - 1 - best
    if abs(float(axis[original]) - value) > max(abs(float(differences[0])) * 0.75, 1.0):
        return None
    return original


def main() -> int:
    args = parse_args()
    try:
        centerline = load_centerline(args.centerline)
        with h5py.File(args.gunw, "r") as h5:
            phase_path, group_path, mask_path = dataset_paths(h5, args.polarization)
            phase_ds = h5[phase_path]
            validate_phase_units(phase_ds)
            coherence_ds = h5[f"{group_path}/coherenceMagnitude"]
            components_ds = h5[f"{group_path}/connectedComponents"]
            mask_ds = h5[mask_path]
            ionosphere_path = f"{group_path}/ionospherePhaseScreen"
            ionosphere_sigma_path = f"{group_path}/ionospherePhaseScreenUncertainty"
            ionosphere_ds = h5[ionosphere_path] if ionosphere_path in h5 else None
            ionosphere_sigma_ds = h5[ionosphere_sigma_path] if ionosphere_sigma_path in h5 else None
            x_axis = np.asarray(h5[f"{group_path}/xCoordinates"][:], dtype=np.float64)
            y_axis = np.asarray(h5[f"{group_path}/yCoordinates"][:], dtype=np.float64)
            epsg = get_epsg(h5[f"{group_path}/projection"])
            frequency_path, center_frequency_hz = get_center_frequency(h5)
            if phase_ds.ndim != 2 or phase_ds.shape != (len(y_axis), len(x_axis)):
                raise ValueError("unwrappedPhase dimensions do not match the GUNW x/y coordinate vectors.")
            required_layers = [coherence_ds, components_ds, mask_ds]
            if any(layer.shape != phase_ds.shape for layer in required_layers):
                raise ValueError("Phase, coherence, mask, and connected-component layers do not have matching dimensions.")
            if (ionosphere_ds is None) != (ionosphere_sigma_ds is None):
                raise ValueError("GUNW contains only one of the ionospheric phase and uncertainty layers; inspect the product before processing.")
            if ionosphere_ds is not None and (ionosphere_ds.shape != phase_ds.shape or ionosphere_sigma_ds.shape != phase_ds.shape):
                raise ValueError("Ionospheric phase and uncertainty layers do not match the unwrapped phase grid.")

            product_crs = CRS.from_epsg(epsg)
            to_product = Transformer.from_crs(CRS.from_epsg(4326), product_crs, always_xy=True)
            projected_line = transform_geometry(to_product.transform, centerline)
            if projected_line.is_empty or projected_line.length <= 0:
                raise ValueError("Centerline could not be projected into the GUNW map grid.")
            total_distance = float(projected_line.length)
            distances = list(np.arange(0.0, total_distance, args.spacing_m, dtype=np.float64))
            if not distances or total_distance - distances[-1] > 1e-6:
                distances.append(total_distance)

            wavelength_m = 299_792_458.0 / center_frequency_hz
            phase_to_range_mm = wavelength_m * 1000.0 / (4.0 * math.pi)
            samples: list[Sample] = []
            for distance in distances:
                point = projected_line.interpolate(float(distance))
                x, y = float(point.x), float(point.y)
                ix, iy = nearest_axis_index(x_axis, x), nearest_axis_index(y_axis, y)
                if ix is None or iy is None:
                    samples.append(Sample(float(distance), x, y, None, None, None, None, None, None, None, None, None, None, "outside_gunw_grid"))
                    continue
                phase = float(phase_ds[iy, ix])
                coherence = float(coherence_ds[iy, ix])
                mask_value = int(mask_ds[iy, ix])
                reference_subswath = (mask_value // 10) % 10
                secondary_subswath = mask_value % 10
                component = int(components_ds[iy, ix])
                ionosphere_phase = float(ionosphere_ds[iy, ix]) if ionosphere_ds is not None else math.nan
                ionosphere_sigma = float(ionosphere_sigma_ds[iy, ix]) if ionosphere_sigma_ds is not None else math.nan
                if mask_value == 255 or is_fill_value(mask_ds, mask_value):
                    status = "outside_mask_extent"
                elif reference_subswath == 0 or secondary_subswath == 0:
                    status = "invalid_reference_or_secondary_subswath"
                elif mask_value // 100 != 0:
                    status = "water_mask"
                elif not math.isfinite(phase) or is_fill_value(phase_ds, phase):
                    status = "invalid_phase"
                elif not math.isfinite(coherence) or is_fill_value(coherence_ds, coherence):
                    status = "invalid_coherence"
                elif not 0.0 <= coherence <= 1.0:
                    status = "coherence_out_of_range"
                elif coherence < args.min_coherence:
                    status = "below_coherence_threshold"
                elif component <= 0 or is_fill_value(components_ds, component):
                    status = "disconnected_component"
                else:
                    status = "usable_screened_sample"
                proxy = phase * phase_to_range_mm if status == "usable_screened_sample" else None
                ionosphere_sigma_mm = (ionosphere_sigma * phase_to_range_mm
                    if math.isfinite(ionosphere_sigma) and ionosphere_sigma >= 0
                    and not is_fill_value(ionosphere_sigma_ds, ionosphere_sigma) else None)
                samples.append(Sample(float(distance), x, y, phase if math.isfinite(phase) else None,
                                      coherence if math.isfinite(coherence) else None, mask_value,
                                      reference_subswath, secondary_subswath, component, proxy,
                                      ionosphere_phase if math.isfinite(ionosphere_phase) else None,
                                      ionosphere_sigma if math.isfinite(ionosphere_sigma) and ionosphere_sigma_mm is not None else None,
                                      ionosphere_sigma_mm, status))

            window_steps = max(2, int(math.ceil(args.window_m / args.spacing_m)))
            for start in range(0, len(samples) - window_steps + 1):
                end = start + window_steps
                window = samples[start:end + 1]
                first = window[0]
                invalid_reasons = sorted({sample.status for sample in window if sample.status != "usable_screened_sample"})
                if invalid_reasons:
                    first.window_status = "window_no_call:" + "|".join(invalid_reasons)
                    continue
                components = {sample.connected_component for sample in window}
                swath_pairs = {(sample.reference_subswath, sample.secondary_subswath) for sample in window}
                if len(components) != 1:
                    first.window_status = "connected_component_transition"
                    continue
                if len(swath_pairs) != 1:
                    first.window_status = "subswath_transition"
                    continue
                last = window[-1]
                actual_length = last.distance_m - first.distance_m
                if actual_length <= 0:
                    first.window_status = "invalid_window_length"
                    continue
                differential = float(last.los_range_change_proxy_mm - first.los_range_change_proxy_mm)
                first.window_end_distance_m = last.distance_m
                first.differential_range_change_proxy_mm = differential
                first.gradient_magnitude_mm_per_m = abs(differential) / actual_length
                endpoint_sigmas = (first.ionosphere_sigma_range_mm, last.ionosphere_sigma_range_mm)
                if all(value is not None and math.isfinite(value) for value in endpoint_sigmas):
                    # Product-provided ionospheric phase-screen uncertainty only.
                    # The 1.96 multiplier treats each value as 1-sigma Gaussian;
                    # RSS assumes independent endpoints. Neither assumption is
                    # established by this layer alone; this is not total uncertainty.
                    sigma_delta = math.hypot(*endpoint_sigmas)
                    first.ionosphere_only_95_lower_mm = differential - 1.96 * sigma_delta
                    first.ionosphere_only_95_upper_mm = differential + 1.96 * sigma_delta
                first.window_status = "usable_window"

        args.output.parent.mkdir(parents=True, exist_ok=True)
        fields = list(Sample.__dataclass_fields__.keys())
        with args.output.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields)
            writer.writeheader()
            writer.writerows(asdict(sample) for sample in samples)

        metadata_path = args.metadata or args.output.with_suffix(".provenance.json")
        usable = sum(sample.status == "usable_screened_sample" for sample in samples)
        windows = sum(sample.gradient_magnitude_mm_per_m is not None for sample in samples)
        no_call_windows = sum(sample.window_status not in ("not_evaluated", "usable_window") for sample in samples)
        metadata = {
            "created_utc": datetime.now(timezone.utc).isoformat(),
            "source_file": str(args.gunw.resolve()),
            "centerline_file": str(args.centerline.resolve()),
            "output_csv": str(args.output.resolve()),
            "product": "NISAR L2 GUNW",
            "phase_dataset": phase_path,
            "coherence_dataset": f"{group_path}/coherenceMagnitude",
            "connected_components_dataset": f"{group_path}/connectedComponents",
            "mask_dataset": mask_path,
            "ionosphere_phase_dataset": ionosphere_path if ionosphere_ds is not None else None,
            "ionosphere_uncertainty_dataset": ionosphere_sigma_path if ionosphere_sigma_ds is not None else None,
            "mask_semantics": "WRS decimal code: hundreds digit is reference water flag; tens and units are reference and secondary subswaths; 255 is fill; zero in either subswath digit is invalid",
            "center_frequency_dataset": frequency_path,
            "center_frequency_hz": center_frequency_hz,
            "wavelength_m": wavelength_m,
            "projection_epsg": epsg,
            "polarization": args.polarization,
            "phase_units": "radians",
            "range_change_conversion": "phase_rad * wavelength_m / (4*pi), converted to mm; sign follows product interferogram ordering and must be interpreted from product metadata",
            "interferogram_phase_convention": "NISAR Science Users' Handbook defines raw interferometric phase as Arg(I_reference * conjugate(I_secondary)); confirm reference/secondary ordering and phase convention in the selected GUNW metadata before interpreting the signed proxy.",
            "output_interpretation": "phase-derived LOS range-change proxy; differential windows are relative differences; not vertical displacement",
            "ionosphere_uncertainty_interpretation": "Conditional approximate 95% interval from ionospheric phase-screen uncertainty only, converted to range-change and propagated between window endpoints using 1.96 times root-sum-square endpoint values. This assumes each product uncertainty value is a one-sigma Gaussian standard uncertainty and endpoint errors are independent; neither distribution nor covariance is established here. All other error sources are excluded. It is not a total measurement confidence interval.",
            "min_coherence_screen": args.min_coherence,
            "sample_spacing_requested_m": args.spacing_m,
            "differential_window_requested_m": args.window_m,
            "sample_count": len(samples),
            "usable_screened_sample_count": usable,
            "no_call_sample_count": len(samples) - usable,
            "valid_differential_window_count": windows,
            "no_call_differential_window_count": no_call_windows,
            "limitations": [
                "Unwrapped phase reference offset is arbitrary; only within-product differences are reported as differential values.",
                "No atmospheric, tropospheric, ionospheric, solid-Earth-tide, or reference-point correction is applied.",
                "The signed phase-derived range-change proxy depends on the reference/secondary interferogram convention; confirm it in product metadata before interpreting direction.",
                "The coherence threshold is user supplied and is not a universal reliability threshold; coherence screening is not an uncertainty estimate.",
                "Where present, the ionospheric phase-screen uncertainty is reported separately. The conditional 95% interval assumes the product uncertainty is one Gaussian standard deviation and endpoint errors are independent; the layer alone does not establish these assumptions. It omits covariance and all non-ionospheric errors and is not a total uncertainty interval. Missing product uncertainty remains unavailable rather than being imputed.",
                "Phase and coherence fill values are excluded when declared in common HDF5 fill-value attributes; product-specific validity rules still require review.",
                "Nearest-pixel sampling is used; requested spacing does not increase the product's spatial resolution.",
                "No independent GNSS/ground validation is performed.",
                "LOS range change is not vertical settlement, structural deformation, damage, or a safety finding.",
            ],
        }
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        print(f"Wrote {len(samples)} corridor samples ({usable} quality-screened, {len(samples) - usable} no-call).")
        print(f"Wrote {windows} usable and {no_call_windows} no-call differential windows to {args.output} and provenance to {metadata_path}.")
        print("Interpret as phase-derived LOS range-change only; inspect product ordering and limitations before use.")
        return 0
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        print(f"StrainLine processing error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
