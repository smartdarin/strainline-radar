import unittest

from backend.temporal_analysis import summarize_processed_history
from backend.main import (TemporalExportRequest, TemporalHistoryRequest,
                          export_temporal_history, temporal_processed)


def observation(index, relative=12.0, asset=None, status="usable"):
    date = ["2026-01-01T00:00:00Z", "2026-01-13T00:00:00Z", "2026-01-25T00:00:00Z"][index]
    provenance = {
        "cmr_granule_id": f"G-{index}",
        "cmr_metadata_url": f"https://cmr.example/granule/G-{index}",
        "collection_short_name": "NISAR_L2_GUNW_PROVISIONAL_V1",
        "processing_maturity": "PROVISIONAL",
        "hdf5_granule_id": f"G-{index}",
        "cmr_identity_matches_hdf5": True,
        "cmr_record_reviewed": True,
        "acquisition_start": "2026-01-01",
        "acquisition_end": "2026-01-25",
        "orbit_geometry_id": "track-22-desc-right",
        "geometry_id": "track-22-desc-right",
        "look_direction": "right",
        "polarization": "HH",
        "footprint_intersection": True,
        "phase_convention_reviewed": True,
        "reference_secondary_order": "common-master-to-secondary",
        "reference_start": "2025-12-20T00:00:00Z",
        "reference_end": "2025-12-20T00:01:00Z",
        "secondary_start": date,
        "secondary_end": date.replace("00:00:00Z", "00:01:00Z"),
        "phase_reference_id": "stable-point-001",
        "effective_support_m": 80,
    }
    section = {"chainage_m": 800.0, "status": status,
               "asset_los_mm": asset if asset is not None else 18.0 + index,
               "common_motion_mm": 6.0,
               "asset_relative_mm": relative,
               "control_disagreement_mm": 1.0}
    result = {"corridor_name": "Test railway", "granule_id": f"G-{index}",
              "provenance": provenance, "sections": [section]}
    return {"corridor_name": "Test railway", "granule_id": f"G-{index}",
            "provenance": provenance, "result": result}


class ProcessedTemporalTests(unittest.TestCase):
    def test_reconstructs_absolute_and_relative_history_on_common_reference(self):
        records = [observation(i, relative=12 + i, asset=18 + i) for i in range(3)]
        result = summarize_processed_history(records)
        self.assertEqual(result["status"], "screening_series")
        chain = result["histories"][0]
        self.assertEqual(chain["status"], "persistent")
        self.assertEqual(chain["asset_absolute_net_change_mm"], 2)
        self.assertEqual(chain["asset_relative_net_change_mm"], 2)
        self.assertEqual(len(chain["temporal_gaps_days"]), 2)

    def test_preserves_nocall_gaps_instead_of_interpolating(self):
        records = [observation(0), observation(1, status="no_call"), observation(2)]
        result = summarize_processed_history(records)
        self.assertEqual(result["status"], "insufficient_evidence")
        self.assertEqual(result["histories"][0]["status"], "unsupported")
        self.assertEqual(result["histories"][0]["missing_observations"][0]["reason"], "no_call")

    def test_incompatible_phase_reference_is_rejected(self):
        records = [observation(i) for i in range(3)]
        records[2]["provenance"]["phase_reference_id"] = "different-point"
        result = summarize_processed_history(records)
        self.assertEqual(result["status"], "not_comparable")

    def test_one_or_two_pairs_never_produce_a_temporal_trend(self):
        self.assertEqual(summarize_processed_history([observation(0), observation(1)])["status"], "unavailable")

    def test_api_accepts_exported_processed_results(self):
        result = temporal_processed(TemporalHistoryRequest(observations=[observation(i) for i in range(3)]))
        self.assertEqual(result["status"], "screening_series")
        self.assertEqual(result["compatibility"]["phase_reference_id"], "stable-point-001")

    def test_temporal_csv_export_keeps_each_actual_pair_measurement(self):
        history = summarize_processed_history([observation(i) for i in range(3)])
        response = export_temporal_history("csv", TemporalExportRequest(history=history))
        text = response.body.decode("utf-8")
        self.assertEqual(text.count("G-"), 3)
        self.assertIn("asset_relative_mm", text.splitlines()[0])

    def test_temporal_csv_export_retains_nocall_reason(self):
        history = summarize_processed_history([observation(0), observation(1, status="no_call"), observation(2)])
        response = export_temporal_history("csv", TemporalExportRequest(history=history))
        self.assertIn("no_call", response.body.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
