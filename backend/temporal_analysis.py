"""Conservative pair-to-pair temporal summaries."""
from __future__ import annotations

from datetime import datetime
import math
from statistics import median
from backend.product_validation import validate_product_record


def summarize_series(observations: list[dict], min_pairs: int = 3) -> dict:
    rows = sorted(observations, key=lambda r: r.get("acquired", ""))
    if len(rows) < min_pairs:
        return {"status": "unavailable", "reason": f"At least {min_pairs} compatible observations are required.", "count": len(rows)}
    fields = ("geometry_id", "polarization", "support_m", "reference_id")
    if any(any(r.get(k) != rows[0].get(k) for k in fields) for r in rows[1:]):
        return {"status": "not_comparable", "reason": "Observation geometry, polarization, support, or reference differs.", "count": len(rows)}
    try:
        dates = [datetime.fromisoformat(r["acquired"].replace("Z", "+00:00")) for r in rows]
        values = [float(r["asset_relative_mm"]) for r in rows]
    except (KeyError, TypeError, ValueError):
        return {"status": "unavailable", "reason": "Missing valid dates or asset-relative measurements.", "count": len(rows)}
    elapsed = (dates[-1] - dates[0]).total_seconds() / 86400
    if elapsed <= 0:
        return {"status": "unavailable", "reason": "Observation dates must span a positive interval.", "count": len(rows)}
    return {"status": "screening_series", "count": len(rows), "elapsed_days": elapsed,
            "net_change_mm": values[-1] - values[0], "rate_mm_per_year": (values[-1] - values[0]) * 365.25 / elapsed,
            "note": "Descriptive rate only; assess temporal decorrelation, reference stability, seasonality, and uncertainty before interpretation."}


def summarize_processed_history(records: list[dict], *, min_observations: int = 3,
                                candidate_threshold_mm: float = 10.0,
                                material_change_mm: float = 5.0) -> dict:
    """Reconstruct chainage histories from saved Three-Lane API results.

    Every record must be an exported processed result with explicit common
    acquisition reference, spatial phase reference, geometry, native support,
    polarization, signed-phase review, and a dated secondary acquisition.
    Missing/no-call sections are retained in each chainage history.
    """
    if min_observations < 3:
        raise ValueError("Temporal reconstruction requires at least three observations.")
    if (not math.isfinite(candidate_threshold_mm) or candidate_threshold_mm < 0
            or not math.isfinite(material_change_mm) or material_change_mm < 0):
        raise ValueError("Temporal thresholds must be finite and non-negative.")
    if len(records) < min_observations:
        return {"status": "unavailable", "reason": f"At least {min_observations} processed observations are required.",
                "count": len(records), "histories": []}

    observations = []
    for source in records:
        record = source.get("result", source)
        if not isinstance(record, dict):
            return {"status": "unavailable", "reason": "Each input must be a processed Three-Lane result export.",
                    "count": len(records), "histories": []}
        provenance = source.get("provenance", record.get("provenance", {})) or {}
        if not isinstance(provenance, dict):
            return {"status": "unavailable", "reason": "Processed result provenance must be an object.",
                    "count": len(records), "histories": []}
        corridor = source.get("corridor_name") or record.get("corridor_name")
        granule_id = source.get("granule_id") or record.get("granule_id")
        sections = record.get("sections")
        # The common-master interpretation uses each product's secondary date.
        acquired = provenance.get("secondary_start") or provenance.get("acquired") or provenance.get("measurement_date")
        required = {
            "corridor_name": corridor,
            "granule_id": granule_id,
            "reference_start": provenance.get("reference_start"),
            "reference_end": provenance.get("reference_end"),
            "phase_reference_id": provenance.get("phase_reference_id"),
            "geometry_id": provenance.get("geometry_id") or provenance.get("orbit_geometry_id"),
            "polarization": provenance.get("polarization"),
            "effective_support_m": provenance.get("effective_support_m") or provenance.get("native_resolution_m"),
            "reference_secondary_order": provenance.get("reference_secondary_order"),
            "acquired": acquired,
            "secondary_end": provenance.get("secondary_end"),
        }
        missing = [key for key, value in required.items() if value in (None, "")]
        if not granule_id:
            missing.append("granule_id")
        elif (product_gaps := validate_product_record(provenance, str(granule_id))):
            return {"status": "unavailable", "reason": f"Product evidence gate failed for {granule_id}: " + ", ".join(product_gaps),
                    "count": len(records), "histories": []}
        if provenance.get("phase_convention_reviewed") is not True:
            missing.append("reviewed_phase_convention")
        if not isinstance(sections, list) or not sections:
            missing.append("processed_sections")
        if missing:
            return {"status": "unavailable", "reason": "A processed observation is missing compatibility/provenance fields: " + ", ".join(sorted(set(missing))),
                    "count": len(records), "histories": []}
        try:
            acquired_dt = datetime.fromisoformat(str(acquired).replace("Z", "+00:00"))
            reference_end_dt = datetime.fromisoformat(str(required["reference_end"]).replace("Z", "+00:00"))
            secondary_end_dt = datetime.fromisoformat(str(required["secondary_end"]).replace("Z", "+00:00"))
            if acquired_dt.tzinfo is None:
                raise ValueError
            if reference_end_dt.tzinfo is None or secondary_end_dt.tzinfo is None:
                raise ValueError
            reference_start_dt = datetime.fromisoformat(str(required["reference_start"]).replace("Z", "+00:00"))
            if reference_start_dt >= reference_end_dt or acquired_dt >= secondary_end_dt:
                raise ValueError
            support = float(required["effective_support_m"])
            if not math.isfinite(support) or support <= 0:
                raise ValueError
        except (ValueError, TypeError):
            return {"status": "unavailable", "reason": "Observation dates or native support values are invalid.",
                    "count": len(records), "histories": []}
        observations.append({**required, "acquired_dt": acquired_dt,
                             "support_m": support, "sections": sections,
                             "provenance": provenance})

    compatibility_fields = ("corridor_name", "reference_start", "reference_end", "phase_reference_id",
                            "geometry_id", "polarization", "reference_secondary_order")
    base = observations[0]
    differences = [f for f in compatibility_fields if any(o[f] != base[f] for o in observations[1:])]
    support_values = [o["support_m"] for o in observations]
    if max(support_values) - min(support_values) > 0.001:
        differences.append("effective_support_m")
    if differences:
        return {"status": "not_comparable", "reason": "Observations differ in required shared-reference geometry or measurement support: " + ", ".join(differences),
                "count": len(records), "histories": [], "granules": [o["granule_id"] for o in observations]}
    observations.sort(key=lambda o: o["acquired_dt"])
    if len({o["acquired_dt"] for o in observations}) != len(observations):
        return {"status": "not_comparable", "reason": "Duplicate observation dates cannot form a time history.",
                "count": len(observations), "histories": []}
    chainages = sorted({round(float(s["chainage_m"]), 3)
                        for o in observations for s in o["sections"]})
    histories = []
    for chainage in chainages:
        series = []
        missing = []
        for observation in observations:
            matches = [s for s in observation["sections"]
                       if round(float(s.get("chainage_m", float("nan"))), 3) == chainage]
            section = matches[0] if len(matches) == 1 else None
            try:
                values_are_finite = section is not None and all(
                    section.get(key) is not None and math.isfinite(float(section[key]))
                    for key in ("asset_los_mm", "common_motion_mm", "asset_relative_mm"))
            except (TypeError, ValueError):
                values_are_finite = False
            if section is None or section.get("status") != "usable" or not values_are_finite:
                missing.append({"granule_id": observation["granule_id"],
                                "date": observation["acquired_dt"].isoformat(),
                                "reason": "missing_section" if section is None else section.get("status", "no_call")})
                continue
            series.append({"granule_id": observation["granule_id"],
                           "date": observation["acquired_dt"].isoformat(),
                           "asset_los_mm": float(section["asset_los_mm"]),
                           "background_los_mm": float(section["common_motion_mm"]),
                           "asset_relative_mm": float(section["asset_relative_mm"]),
                           "control_disagreement_mm": section.get("control_disagreement_mm")})
        if len(series) < min_observations:
            histories.append({"chainage_m": chainage, "status": "unsupported",
                              "valid_observations": len(series), "observations": series,
                              "missing_observations": missing,
                              "reason": f"Fewer than {min_observations} usable observations at this chainage."})
            continue
        absolute = [v["asset_los_mm"] for v in series]
        relative = [v["asset_relative_mm"] for v in series]
        flags = [abs(v) > candidate_threshold_mm for v in relative]
        signal_range = max(relative) - min(relative)
        if signal_range > material_change_mm:
            pattern = "changing"
        elif all(flags):
            pattern = "persistent"
        elif any(flags):
            pattern = "intermittent"
        else:
            pattern = "no_persistent_candidate"
        spans = [(datetime.fromisoformat(series[i]["date"]), datetime.fromisoformat(series[i + 1]["date"]))
                 for i in range(len(series) - 1)]
        gap_days = [(right - left).total_seconds() / 86400 for left, right in spans]
        elapsed_days = (datetime.fromisoformat(series[-1]["date"]) - datetime.fromisoformat(series[0]["date"])).total_seconds() / 86400
        histories.append({"chainage_m": chainage, "status": pattern,
                          "valid_observations": len(series), "missing_observations": missing,
                          "asset_absolute_net_change_mm": absolute[-1] - absolute[0],
                          "asset_relative_net_change_mm": relative[-1] - relative[0],
                          "asset_relative_median_mm": median(relative),
                          "asset_relative_range_mm": signal_range,
                          "elapsed_days": elapsed_days,
                          "asset_relative_descriptive_rate_mm_per_year": (relative[-1] - relative[0]) * 365.25 / elapsed_days if elapsed_days > 0 else None,
                          "temporal_gaps_days": gap_days, "observations": series})
    status = "screening_series" if any(h["status"] != "unsupported" for h in histories) else "insufficient_evidence"
    return {"status": status, "count": len(observations),
            "corridor_name": base["corridor_name"],
            "granules": [{"granule_id": o["granule_id"], "reference_start": o["reference_start"],
                          "reference_end": o["reference_end"],
                          "secondary_start": o["acquired_dt"].isoformat(),
                          "secondary_end": o["secondary_end"]} for o in observations],
            "compatibility": {key: base[key] for key in compatibility_fields},
            "effective_support_m": base["support_m"],
            "settings": {"candidate_threshold_mm": candidate_threshold_mm,
                         "material_change_mm": material_change_mm,
                         "minimum_usable_observations_per_chainage": min_observations},
            "histories": histories,
            "method": "Chainage-aligned absolute asset LOS and asset-relative LOS are summarized only from usable sections. All products must share one reference acquisition, one spatial phase reference, geometry, polarization, phase convention, and native measurement support. No-call or missing sections remain explicit; no missing value is interpolated. A single interferogram pair is not a trend.",
            "limitations": ["Descriptive rates are not forecasts.",
                            "Atmospheric, seasonal, unwrapping, reference, and decorrelation effects are not removed by this compatibility gate.",
                            "Persistent/changing/intermittent are screening descriptions, not damage probabilities."],
            "provenance_authentication": "Required source fields are completeness-checked from the supplied processed exports; their authenticity is not independently authenticated."}
