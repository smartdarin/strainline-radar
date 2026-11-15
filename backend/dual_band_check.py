"""Conservative L/S comparison gate; refuses incompatible acquisitions."""
from __future__ import annotations
import math


REQUIRED_MATCH_FIELDS = ("start_time", "end_time", "geometry_id", "polarization", "support_m")


def compare_band_summaries(l_band: dict | None, s_band: dict | None, tolerance_mm: float = 5.0) -> dict:
    if not math.isfinite(tolerance_mm) or tolerance_mm < 0:
        return {"status": "unavailable", "reason": "Consistency tolerance must be finite and non-negative."}
    if not l_band or not s_band:
        return {"status": "unavailable", "reason": "Both L-band and S-band summaries are required."}
    missing = [f for f in REQUIRED_MATCH_FIELDS if l_band.get(f) is None or s_band.get(f) is None]
    if missing:
        return {"status": "unavailable", "reason": "Missing comparison metadata: " + ", ".join(missing)}
    mismatched = [f for f in REQUIRED_MATCH_FIELDS if l_band[f] != s_band[f]]
    if mismatched:
        return {"status": "not_comparable", "reason": "Observation geometry, dates, polarization, or spatial support differ: " + ", ".join(mismatched)}
    if not isinstance(l_band.get("asset_relative_mm"), (int, float)) or not isinstance(s_band.get("asset_relative_mm"), (int, float)):
        return {"status": "unavailable", "reason": "Both valid asset-relative summaries are required."}
    difference = float(l_band["asset_relative_mm"]) - float(s_band["asset_relative_mm"])
    if not math.isfinite(difference): return {"status":"unavailable","reason":"Band summaries are not finite values."}
    return {"status": "consistent" if abs(difference) <= tolerance_mm else "disagree",
            "difference_mm": difference, "tolerance_mm": tolerance_mm,
            "note": "Cross-band consistency check only; band-specific scattering and errors remain."}
