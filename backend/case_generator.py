"""Turn processed Three-Lane results into traceable field investigation cases."""


def build_cases(result: dict, *, corridor_name: str, granule_id: str, provenance: dict) -> list[dict]:
    cases = []
    for section in result.get("sections", []):
        if section.get("status") not in ("ambiguous", "no_call") and abs(section.get("asset_relative_mm") or 0) <= result.get("settings", {}).get("candidate_threshold_mm", 0):
            continue
        chainage = section["chainage_m"]
        cases.append({
            "case_id": f"{corridor_name}:{chainage:.0f}m", "corridor": corridor_name,
            "chainage_m": chainage, "status": section["status"], "reason": section.get("reasons", []),
            "coordinates": [section["longitude"], section["latitude"]] if section.get("longitude") is not None and section.get("latitude") is not None else None,
            "longitude": section.get("longitude"), "latitude": section.get("latitude"),
            "asset_los_mm": section.get("asset_los_mm"), "control_a_los_mm": section.get("control_a_los_mm"),
            "control_b_los_mm": section.get("control_b_los_mm"), "asset_relative_mm": section.get("asset_relative_mm"),
            "terrain_match_metrics": section.get("terrain_match_metrics"),
            "context": section.get("context", []),
            "granule_id": granule_id, "provenance": provenance,
            "verification_plan": [
                {"location": "candidate railway chainage", "measure": "surveyed cross-section and repeat GNSS", "role": "asset",
                 "chainage_m": chainage, "longitude": section.get("longitude"), "latitude": section.get("latitude")},
                {"location": "Control A matched terrain", "measure": "repeat GNSS and terrain/land-cover check", "role": "background"},
                {"location": "Control B matched terrain", "measure": "repeat GNSS and terrain/land-cover check", "role": "background"},
                {"location": "stable reference outside candidate zone", "measure": "survey control check", "role": "reference"},
            ],
            "caveat": "Proposed investigation locations only. This case does not diagnose a defect or prescribe a repair.",
        })
    return cases
