import unittest

from backend.control_lane_engine import LaneSample
from backend.reference_robustness import evaluate_reference_robustness
from backend.main import RobustnessRequest, reference_robustness


def setup_data(a=0.0, b=2.0):
    rows = [LaneSample(float(i), 25.0, a, b, 10, 10, 10) for i in range(4)]
    matches = [{"chainage_m": float(i), "controls": {
        "control_a": {"matched": True}, "control_b": {"matched": True}}}
        for i in range(4)]
    return rows, matches


class ReferenceRobustnessTests(unittest.TestCase):
    def test_consistent_when_reference_choices_preserve_candidate(self):
        rows, matches = setup_data()
        result = evaluate_reference_robustness(rows, matches)
        self.assertEqual(result["classification"], "consistent")
        self.assertEqual([s["status"] for s in result["scenarios"]], ["candidate"] * 3)

    def test_reference_sensitive_when_control_choice_changes_outcome(self):
        rows, matches = setup_data(0.0, 20.0)
        result = evaluate_reference_robustness(rows, matches, material_change_mm=2)
        self.assertEqual(result["classification"], "reference_sensitive")
        self.assertEqual(result["scenarios"][2]["status"], "ambiguous_controls")
        self.assertTrue(all(s["control_disagreement_sections"] == 4 for s in result["scenarios"][2:]))

    def test_low_support_is_insufficient_not_candidate(self):
        rows, matches = setup_data()
        result = evaluate_reference_robustness(rows[:2], matches[:2])
        self.assertEqual(result["classification"], "insufficient_evidence")
        self.assertTrue(all(s["status"] == "insufficient_evidence" for s in result["scenarios"]))

    def test_api_recomputes_from_submitted_samples_and_match_records(self):
        rows, matches = setup_data()
        result = reference_robustness(RobustnessRequest(samples=rows, terrain_matches=matches))
        self.assertEqual(result["classification"], "consistent")
        self.assertEqual(result["scenarios"][2]["usable_sections"], 4)

    def test_api_recomputes_real_pixel_support_at_three_zone_radii(self):
        lane_pixels={lane:[] for lane in ("asset","control_a","control_b")}
        for chainage in (0.0,80.0,160.0):
            for lane, center_x in (("asset",1000.0),("control_a",2000.0),("control_b",3000.0)):
                for dx in (0,20,40,60,80,100):
                    lane_pixels[lane].append({
                        "chainage_m":chainage,"center_x":center_x,"center_y":5000.0,
                        "x":center_x+dx,"y":5000.0,"coherence":.8,
                        "phase_valid":True,"product_mask_valid":True,"mask_valid":True,
                        "component_id":1,"reference_subswath":1,"secondary_subswath":1,
                        "los_range_change_proxy_mm":15.0 if lane=="asset" and dx<=40 else 0.0,
                        "elevation_m":100.0,"slope_deg":1.0,"aspect_deg":90.0,
                        "land_cover":"forest","longitude":76.0,"latitude":30.0})
        thresholds={"max_elevation_difference_m":10,"max_slope_difference_deg":5,
                    "max_aspect_difference_deg":10,"max_radar_valid_fraction_difference":.1}
        result=reference_robustness(RobustnessRequest(
            samples=setup_data()[0],terrain_matches=[],lane_pixels=lane_pixels,matching_thresholds=thresholds,
            coherence_threshold=.4,base_radius_m=100,radius_floor_fraction=.5,
            min_valid_pixels=3,min_sections=3,candidate_threshold_mm=10,material_change_mm=5))
        self.assertEqual(result["tested_radii_m"],[50.0,75.0,100.0])
        self.assertEqual(len(result["scenarios"]),9)
        self.assertEqual(result["classification"],"reference_sensitive")
        self.assertEqual(result["scenarios"][0]["radius_m"],50.0)
        self.assertEqual(result["scenarios"][6]["radius_m"],100.0)


if __name__ == "__main__":
    unittest.main()
