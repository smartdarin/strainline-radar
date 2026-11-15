"""Compute and gate ancillary terrain/radar matching evidence for control lanes."""
from __future__ import annotations
import math
from statistics import median


def circular_difference_degrees(a: float, b: float) -> float:
    return abs((a - b + 180) % 360 - 180)


def summarize_lane_covariates(pixels: list[dict], coherence_threshold: float) -> dict:
    """Summarize covariate samples collected over the same lane support."""
    if not 0 <= coherence_threshold <= 1:
        raise ValueError("Coherence threshold must be in [0, 1].")
    valid = []
    for p in pixels:
        try:
            nums=[float(p[k]) for k in ("elevation_m","slope_deg")]
            aspect=p.get("aspect_deg")
            if all(math.isfinite(v) for v in nums) and (aspect is None or math.isfinite(float(aspect))) and p.get("land_cover") is not None:
                valid.append(p)
        except (KeyError,TypeError,ValueError):
            continue
    if not valid:
        raise ValueError("No complete DEM/land-cover pixels are available for this lane.")
    aspects = [float(p["aspect_deg"]) % 360 for p in valid if p.get("aspect_deg") is not None and float(p["slope_deg"]) >= 0.1]
    angle = math.atan2(sum(math.sin(math.radians(v)) for v in aspects), sum(math.cos(math.radians(v)) for v in aspects)) if aspects else None
    classes = {}
    for p in valid: classes[str(p["land_cover"])] = classes.get(str(p["land_cover"]), 0) + 1
    coherence_pixels = [float(p["coherence"]) for p in pixels if p.get("coherence") is not None and math.isfinite(float(p["coherence"]))]
    usable = [p for p in pixels if p.get("coherence") is not None and math.isfinite(float(p["coherence"])) and coherence_threshold <= float(p["coherence"]) <= 1 and p.get("phase_valid", True) and p.get("mask_valid", True)]
    return {"pixel_count": len(valid), "elevation_median_m": median(float(p["elevation_m"]) for p in valid),
            "slope_median_deg": median(float(p["slope_deg"]) for p in valid),
            "aspect_mean_deg": math.degrees(angle) % 360 if angle is not None else None,
            "land_cover_mode": max(classes, key=classes.get),
            "radar_valid_fraction": len(usable) / max(1, len(coherence_pixels))}


def compare_control_covariates(asset: dict, control: dict, thresholds: dict) -> dict:
    keys=("max_elevation_difference_m","max_slope_difference_deg","max_aspect_difference_deg","max_radar_valid_fraction_difference")
    if any(k not in thresholds or not math.isfinite(float(thresholds[k])) or float(thresholds[k])<0 for k in keys):
        raise ValueError("All terrain/radar matching limits must be finite, explicit and non-negative.")
    for lane in (asset,control):
        if not 0<=float(lane["radar_valid_fraction"])<=1: raise ValueError("Radar valid fraction must be in [0, 1].")
    elevation = abs(asset["elevation_median_m"] - control["elevation_median_m"])
    slope = abs(asset["slope_median_deg"] - control["slope_median_deg"])
    aspect_defined = (asset["aspect_mean_deg"] is not None and control["aspect_mean_deg"] is not None
                      and float(asset["slope_median_deg"]) >= 0.1 and float(control["slope_median_deg"]) >= 0.1)
    aspect = circular_difference_degrees(asset["aspect_mean_deg"], control["aspect_mean_deg"]) if aspect_defined else None
    landcover = asset["land_cover_mode"] == control["land_cover_mode"]
    observability = abs(asset["radar_valid_fraction"] - control["radar_valid_fraction"])
    observed = {"elevation_abs_difference_m": elevation, "slope_abs_difference_deg": slope,
                "aspect_abs_difference_deg": aspect, "land_cover_match": landcover,
                "radar_valid_fraction_abs_difference": observability}
    checks = {"elevation": elevation <= thresholds["max_elevation_difference_m"],
              "slope": slope <= thresholds["max_slope_difference_deg"],
              "aspect": aspect <= thresholds["max_aspect_difference_deg"] if aspect_defined else True,
              "land_cover": landcover,
              "radar_observability": observability <= thresholds["max_radar_valid_fraction_difference"]}
    return {"matched": all(checks.values()), "checks": checks, "metrics": observed, "thresholds": thresholds}
