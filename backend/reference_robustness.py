"""Reference sensitivity analysis over already processed Three-Lane samples.

This explores alternative use of the supplied matched controls. It cannot
create new spatial buffers or resample pixels; those require new source data.
"""
from __future__ import annotations

import math
from collections import Counter, defaultdict
from statistics import median

from backend.control_lane_engine import LaneSample
from backend.terrain_matching import compare_control_covariates, summarize_lane_covariates


def evaluate_reference_robustness(samples, terrain_matches, *, min_valid_pixels=3,
                                  candidate_threshold_mm=10.0,
                                  material_change_mm=5.0, max_control_disagreement_mm=10.0,
                                  min_sections=3):
    if min_valid_pixels < 1 or min_sections < 1 or candidate_threshold_mm < 0 or material_change_mm < 0 or max_control_disagreement_mm < 0:
        raise ValueError("Pixel and section counts must be positive; movement thresholds must be non-negative.")
    if not all(math.isfinite(float(x)) for x in (candidate_threshold_mm, material_change_mm, max_control_disagreement_mm)):
        raise ValueError("Thresholds must be finite.")
    matches = {round(float(m["chainage_m"]), 3): m.get("controls", {}) for m in terrain_matches}
    configurations = {
        "control_a_only": ("control_a",),
        "control_b_only": ("control_b",),
        "paired_controls_median": ("control_a", "control_b"),
    }
    scenarios = []
    for name, controls in configurations.items():
        values = []
        rejected = 0
        disagreements = 0
        for row in samples:
            match = matches.get(round(float(row.chainage_m), 3), {})
            counts = {"asset": row.asset_valid_pixels, "control_a": row.control_a_valid_pixels,
                      "control_b": row.control_b_valid_pixels}
            quality = {"asset": row.asset_quality, "control_a": row.control_a_quality,
                       "control_b": row.control_b_quality}
            valid = (row.asset_los_mm is not None and math.isfinite(row.asset_los_mm)
                     and counts["asset"] >= min_valid_pixels and quality["asset"] == "ok"
                     and all(getattr(row, f"{control}_los_mm") is not None
                             and math.isfinite(getattr(row, f"{control}_los_mm"))
                             and counts[control] >= min_valid_pixels and quality[control] == "ok"
                             and match.get(control, {}).get("matched") is True for control in controls))
            if not valid:
                rejected += 1
                continue
            if len(controls) == 2 and abs(float(row.control_a_los_mm) - float(row.control_b_los_mm)) > max_control_disagreement_mm:
                rejected += 1
                disagreements += 1
                continue
            reference = median([float(getattr(row, f"{control}_los_mm")) for control in controls])
            values.append({"chainage_m": row.chainage_m,
                           "asset_relative_mm": float(row.asset_los_mm) - reference,
                           "asset_los_mm": row.asset_los_mm, "reference_los_mm": reference})
        candidates = sum(abs(v["asset_relative_mm"]) > candidate_threshold_mm for v in values)
        status = ("ambiguous_controls" if disagreements >= min_sections else
                  "insufficient_evidence" if len(values) < min_sections else
                  "candidate" if candidates >= min_sections else "no_material_difference")
        scenarios.append({"configuration": name, "controls": list(controls), "status": status,
                          "usable_sections": len(values), "rejected_sections": rejected,
                          "control_disagreement_sections": disagreements,
                          "candidate_sections": candidates, "median_asset_relative_mm":
                          median([v["asset_relative_mm"] for v in values]) if values else None,
                          "sections": values})
    eligible = [s for s in scenarios if s["median_asset_relative_mm"] is not None]
    spread = (max(s["median_asset_relative_mm"] for s in eligible)
              - min(s["median_asset_relative_mm"] for s in eligible)) if eligible else None
    if len(eligible) < 2 or any(s["status"] == "insufficient_evidence" for s in scenarios):
        classification = "insufficient_evidence"
    elif spread > material_change_mm or len({s["status"] for s in scenarios}) > 1:
        classification = "reference_sensitive"
    else:
        classification = "consistent"
    return {"classification": classification, "material_change_mm": material_change_mm,
            "candidate_threshold_mm": candidate_threshold_mm,
            "max_control_disagreement_mm": max_control_disagreement_mm,
            "min_valid_pixels_per_lane": min_valid_pixels,
            "median_signal_spread_mm": spread, "scenarios": scenarios,
            "method": "For each eligible section, compare asset LOS against Control A, Control B, or their median. Reapply the supplied pixel-count, quality and terrain/radar-match gates. Compare scenario median asset-relative signals; classify as reference-sensitive if their spread exceeds the analyst-selected material-change threshold or candidate status changes. This is a sensitivity screen, not a probability or structural diagnosis.",
            "limitations": ["No new control polygons or zone widths are created.",
                            "No pixels are resampled; alternative spatial windows are unavailable from section summaries.",
                            "Only the controls supplied in the processed input are tested."]}


def evaluate_spatial_reference_robustness(lane_pixels, *, base_radius_m, radius_floor_fraction,
                                          coherence_threshold, matching_thresholds,
                                          min_valid_pixels=3, candidate_threshold_mm=10.0,
                                          material_change_mm=5.0, max_control_disagreement_mm=10.0,
                                          min_sections=3):
    """Recompute all three lanes at narrower radii from retained GUNW pixels."""
    if not math.isfinite(float(base_radius_m)) or base_radius_m <= 0:
        raise ValueError("Base sample radius must be positive and finite.")
    if not 0 < radius_floor_fraction < 1:
        raise ValueError("Radius floor fraction must be between zero and one.")
    if not 0 <= coherence_threshold <= 1:
        raise ValueError("Coherence threshold must be in [0,1].")
    required = {"asset", "control_a", "control_b"}
    if set(lane_pixels) != required:
        raise ValueError("Retained lane pixels must contain asset, control_a, and control_b groups.")
    by_lane_chainage = {lane: defaultdict(list) for lane in required}
    for lane in required:
        for pixel in lane_pixels[lane]:
            chainage = round(float(pixel["chainage_m"]), 3)
            by_lane_chainage[lane][chainage].append(pixel)
    chainages = sorted(set().union(*(set(by_lane_chainage[lane]) for lane in required)))
    fractions = (radius_floor_fraction, (radius_floor_fraction + 1.0) / 2.0, 1.0)
    all_scenarios = []
    radii = []

    for fraction in fractions:
        radius = float(base_radius_m) * fraction
        radii.append(radius)
        samples, terrain_matches = [], []
        for chainage in chainages:
            summaries, lane_values, lane_counts, lane_quality, lane_ids = {}, {}, {}, {}, {}
            lane_records = {}
            for lane in ("asset", "control_a", "control_b"):
                within = [pixel for pixel in by_lane_chainage[lane].get(chainage, [])
                          if (float(pixel["x"]) - float(pixel["center_x"])) ** 2
                          + (float(pixel["y"]) - float(pixel["center_y"])) ** 2 <= radius ** 2 + 1e-6]
                eligible = [pixel for pixel in within
                            if pixel.get("product_mask_valid") is True
                            and pixel.get("phase_valid") is True
                            and pixel.get("coherence") is not None
                            and math.isfinite(float(pixel["coherence"]))
                            and coherence_threshold <= float(pixel["coherence"]) <= 1
                            and pixel.get("los_range_change_proxy_mm") is not None
                            and math.isfinite(float(pixel["los_range_change_proxy_mm"]))]
                component_counts = Counter(int(pixel["component_id"]) for pixel in eligible
                                           if pixel.get("component_id") is not None)
                selected_component = component_counts.most_common(1)[0][0] if component_counts else None
                component_selected = [pixel for pixel in eligible
                                      if selected_component is not None and int(pixel["component_id"]) == selected_component]
                swath_counts = Counter((int(pixel["reference_subswath"]), int(pixel["secondary_subswath"]))
                                       for pixel in component_selected
                                       if pixel.get("reference_subswath") is not None and pixel.get("secondary_subswath") is not None)
                selected_swath = swath_counts.most_common(1)[0][0] if swath_counts else None
                selected = [pixel for pixel in within if pixel.get("product_mask_valid") is True
                            and pixel.get("phase_valid") is True and selected_component is not None
                            and int(pixel.get("component_id", -1)) == selected_component
                            and selected_swath is not None
                            and (int(pixel.get("reference_subswath", -1)), int(pixel.get("secondary_subswath", -1))) == selected_swath]
                usable = [pixel for pixel in selected
                          if pixel.get("coherence") is not None
                          and math.isfinite(float(pixel["coherence"]))
                          and coherence_threshold <= float(pixel["coherence"]) <= 1
                          and pixel.get("los_range_change_proxy_mm") is not None
                          and math.isfinite(float(pixel["los_range_change_proxy_mm"]))]
                lane_values[lane] = median(float(pixel["los_range_change_proxy_mm"]) for pixel in usable) if usable else None
                lane_counts[lane] = len(usable)
                lane_quality[lane] = "ok" if usable else "no_valid_pixels"
                lane_ids[lane] = (selected_component, selected_swath)
                lane_records[lane] = [{**pixel, "mask_valid": pixel in selected}
                                      for pixel in within]
                try:
                    summaries[lane] = summarize_lane_covariates(lane_records[lane], coherence_threshold)
                except (KeyError, TypeError, ValueError):
                    summaries[lane] = None

            passing_lanes = [lane for lane in required if lane_quality[lane] == "ok"]
            if len({lane_ids[lane] for lane in passing_lanes}) > 1:
                for lane in passing_lanes:
                    lane_quality[lane] = "cross_lane_component_or_swath_mismatch"

            controls = {}
            for control in ("control_a", "control_b"):
                if summaries["asset"] is None or summaries[control] is None:
                    controls[control] = {"matched": False, "reason": "incomplete terrain/land-cover support"}
                else:
                    controls[control] = compare_control_covariates(summaries["asset"], summaries[control], matching_thresholds)
            terrain_matches.append({"chainage_m": chainage, "controls": controls})
            asset_points = by_lane_chainage["asset"].get(chainage, [])
            longitude = asset_points[0].get("longitude") if asset_points else None
            latitude = asset_points[0].get("latitude") if asset_points else None
            samples.append(LaneSample(
                chainage_m=chainage, asset_los_mm=lane_values["asset"],
                control_a_los_mm=lane_values["control_a"], control_b_los_mm=lane_values["control_b"],
                asset_valid_pixels=lane_counts["asset"], control_a_valid_pixels=lane_counts["control_a"],
                control_b_valid_pixels=lane_counts["control_b"], asset_quality=lane_quality["asset"],
                control_a_quality=lane_quality["control_a"], control_b_quality=lane_quality["control_b"],
                longitude=longitude, latitude=latitude,
                control_a_terrain_match=controls["control_a"]["matched"],
                control_b_terrain_match=controls["control_b"]["matched"]))

        result = evaluate_reference_robustness(
            samples, terrain_matches, min_valid_pixels=min_valid_pixels,
            candidate_threshold_mm=candidate_threshold_mm, material_change_mm=material_change_mm,
            max_control_disagreement_mm=max_control_disagreement_mm, min_sections=min_sections)
        for scenario in result["scenarios"]:
            scenario["radius_m"] = radius
            scenario["radius_fraction_of_sampled_support"] = fraction
            scenario["configuration"] = f"{int(round(radius))}m_{scenario['configuration']}"
            all_scenarios.append(scenario)

    eligible = [scenario["median_asset_relative_mm"] for scenario in all_scenarios
                if scenario["median_asset_relative_mm"] is not None]
    spread = max(eligible) - min(eligible) if eligible else None
    statuses = {scenario["status"] for scenario in all_scenarios}
    if len(eligible) < 2 or "insufficient_evidence" in statuses:
        classification = "insufficient_evidence"
    elif (spread is not None and spread > material_change_mm) or len(statuses) > 1:
        classification = "reference_sensitive"
    else:
        classification = "consistent"
    return {"classification": classification, "material_change_mm": material_change_mm,
            "candidate_threshold_mm": candidate_threshold_mm,
            "max_control_disagreement_mm": max_control_disagreement_mm,
            "min_valid_pixels_per_lane": min_valid_pixels,
            "median_signal_spread_mm": spread, "scenarios": all_scenarios,
            "tested_radii_m": radii, "maximum_sampled_radius_m": float(base_radius_m),
            "method": "Recompute per-lane LOS medians and terrain/radar matches from retained GUNW-support pixel records at three radii, then compare Control A, Control B, and their median. Each radius reapplies coherence, phase/mask, connected-component, subswath, pixel-count, terrain-match, and control-disagreement gates. Classification spans all eligible radius/reference combinations; this is a sensitivity screen, not a damage probability.",
            "limitations": ["Only radii at or below the original sampled radius are tested.",
                            "The current source pixels do not support new non-concentric control zones or spatial extents outside the uploaded lane support.",
                            "Results retain the source product's native spatial support and are not independent observations."]}
