"""Three-Lane Test calculations for asset and matched-background observations.

Input samples must already share chainage, spatial support, acquisition pair,
and documented terrain-matching rules. This module never invents controls.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from statistics import median
from typing import Iterable


@dataclass(frozen=True)
class LaneSample:
    chainage_m: float
    asset_los_mm: float | None
    control_a_los_mm: float | None
    control_b_los_mm: float | None
    asset_valid_pixels: int = 0
    control_a_valid_pixels: int = 0
    control_b_valid_pixels: int = 0
    asset_quality: str = "ok"
    control_a_quality: str = "ok"
    control_b_quality: str = "ok"
    longitude: float | None = None
    latitude: float | None = None
    control_a_terrain_match: bool = False
    control_b_terrain_match: bool = False
    terrain_match_metrics: dict | None = None


def evaluate_three_lane(
    samples: Iterable[LaneSample], *, min_valid_pixels: int = 3,
    max_control_disagreement_mm: float = 10.0,
    candidate_threshold_mm: float = 10.0,
    min_sections: int = 3,
) -> dict:
    """Return common LOS movement, asset-relative residual, and honest no-calls.

    Control background is the median of the two controls. A candidate is only
    emitted when both controls pass quality/pixel gates and agree within the
    analyst-configured tolerance. Values/tolerances are screening settings,
    never safety thresholds.
    """
    if min_valid_pixels < 1 or max_control_disagreement_mm < 0 or candidate_threshold_mm < 0 or min_sections < 1:
        raise ValueError("Quality and control limits must be non-negative; counts must be positive.")
    ordered = sorted(samples, key=lambda row: row.chainage_m)
    if any(not math.isfinite(row.chainage_m) for row in ordered):
        raise ValueError("Chainage values must be finite.")
    if any(ordered[i].chainage_m == ordered[i - 1].chainage_m for i in range(1, len(ordered))):
        raise ValueError("Chainage values must be unique.")
    sections = []
    for row in ordered:
        reasons = []
        values = (row.asset_los_mm, row.control_a_los_mm, row.control_b_los_mm)
        counts = (row.asset_valid_pixels, row.control_a_valid_pixels, row.control_b_valid_pixels)
        qualities = (row.asset_quality, row.control_a_quality, row.control_b_quality)
        labels = ("asset", "control_a", "control_b")
        for label, value, count, quality in zip(labels, values, counts, qualities):
            if value is None or not math.isfinite(value) or count < min_valid_pixels or quality != "ok":
                reasons.append(f"{label}:{quality if quality != 'ok' else 'insufficient_valid_pixels'}")
        if reasons:
            sections.append({"chainage_m": row.chainage_m, "status": "no_call", "reasons": reasons,
                             "asset_los_mm": row.asset_los_mm, "control_a_los_mm": row.control_a_los_mm,
                             "control_b_los_mm": row.control_b_los_mm, "asset_relative_mm": None,
                             "common_motion_mm": None, "control_disagreement_mm": None,
                             "longitude": row.longitude, "latitude": row.latitude})
            continue
        a, c1, c2 = (float(v) for v in values)
        if not row.control_a_terrain_match or not row.control_b_terrain_match:
            failed=[]
            if not row.control_a_terrain_match: failed.append("control_a_terrain_or_radar_mismatch")
            if not row.control_b_terrain_match: failed.append("control_b_terrain_or_radar_mismatch")
            sections.append({"chainage_m": row.chainage_m, "status": "ambiguous", "reasons": failed,
                             "asset_los_mm": a, "control_a_los_mm": c1, "control_b_los_mm": c2,
                             "common_motion_mm": median((c1,c2)), "asset_relative_mm": None,
                             "control_disagreement_mm": abs(c1-c2), "longitude": row.longitude,
                             "latitude": row.latitude, "terrain_match_metrics": row.terrain_match_metrics})
            continue
        disagreement = abs(c1 - c2)
        if disagreement > max_control_disagreement_mm:
            sections.append({"chainage_m": row.chainage_m, "status": "ambiguous", "reasons": ["controls_disagree"],
                             "asset_los_mm": a, "control_a_los_mm": c1, "control_b_los_mm": c2,
                             "asset_relative_mm": None, "common_motion_mm": median((c1, c2)),
                             "control_disagreement_mm": disagreement,
                             "longitude": row.longitude, "latitude": row.latitude,
                             "terrain_match_metrics": row.terrain_match_metrics})
            continue
        background = median((c1, c2))
        sections.append({"chainage_m": row.chainage_m, "status": "usable", "reasons": [],
                         "asset_los_mm": a, "control_a_los_mm": c1, "control_b_los_mm": c2,
                         "common_motion_mm": background, "asset_relative_mm": a - background,
                         "control_disagreement_mm": disagreement,
                         "longitude": row.longitude, "latitude": row.latitude,
                         "terrain_match_metrics": row.terrain_match_metrics})
    usable = [s for s in sections if s["status"] == "usable"]
    anomalous = [s for s in usable if abs(s["asset_relative_mm"]) > candidate_threshold_mm]
    ambiguous = [s for s in sections if s["status"] == "ambiguous"]
    if len(ambiguous) >= min_sections:
        summary = "ambiguous_controls"
    elif len(usable) < min_sections:
        summary = "insufficient_evidence"
    elif len(anomalous) >= min_sections:
        summary = "candidate_asset_relative_difference"
    elif ambiguous:
        summary = "ambiguous_controls"
    else:
        summary = "shared_or_no_material_difference"
    return {
        "method": "three_lane_median_control_v1",
        "status": summary,
        "settings": {"min_valid_pixels_per_lane": min_valid_pixels,
                     "max_control_disagreement_mm": max_control_disagreement_mm,
                     "candidate_threshold_mm": candidate_threshold_mm,
                     "min_sections": min_sections},
        "section_count": len(sections), "usable_section_count": len(usable),
        "no_call_count": sum(s["status"] == "no_call" for s in sections),
        "ambiguous_count": len(ambiguous),
        "sections": sections,
        "interpretation": "LOS screening only; a candidate is not damage or a safety finding. Controls must be terrain- and radar-matched, and all lane statistics must use common spatial support.",
    }


def as_lane_sample(record: dict) -> LaneSample:
    """Validate and construct a lane sample from a JSON-compatible mapping."""
    return LaneSample(**record)
