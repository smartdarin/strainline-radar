import unittest
import json
from shapely.geometry import shape

from backend.control_lane_engine import LaneSample, evaluate_three_lane
from backend.dual_band_check import compare_band_summaries
from backend.temporal_analysis import summarize_series
from backend.footprint import intersects_geojson, corridor_geometry
from backend.terrain_matching import compare_control_covariates, circular_difference_degrees
from backend.main import AnalysisRequest, ExportRequest, three_lane, export_result, terrain_match
from backend.gunw_reader import phase_to_range_change_mm
from backend.product_validation import validate_product_record
from fastapi import HTTPException


def sample(chainage, asset, a, b, count=12, aq="ok", cq1="ok", cq2="ok"):
    return LaneSample(chainage, asset, a, b, count, count, count, aq, cq1, cq2,
                      control_a_terrain_match=True, control_b_terrain_match=True)


class ThreeLaneTests(unittest.TestCase):
  def test_phase_conversion_uses_wavelength_and_rejects_invalid_inputs(self):
    expected=(299_792_458.0/1.2e9)*1000/(4*3.141592653589793)
    self.assertAlmostEqual(phase_to_range_change_mm(1.0,1.2e9),expected,places=10)
    self.assertEqual(phase_to_range_change_mm(0.0,1.2e9),0.0)
    with self.assertRaises(ValueError): phase_to_range_change_mm(1.0,0)

  def test_terrain_match_summarizes_same_support_and_reports_mismatch(self):
    pixels={}
    for lane,offset,cover in (("asset",0,"forest"),("control_a",2,"forest"),("control_b",4,"forest")):
      pixels[lane]=[{"chainage_m":chain,"elevation_m":100+offset,"slope_deg":20,"aspect_deg":359 if lane=="asset" else 1,"land_cover":cover,"coherence":.8,"phase_valid":True,"mask_valid":True} for chain in (0,80) for _ in range(4)]
    limits={"max_elevation_difference_m":10,"max_slope_difference_deg":5,"max_aspect_difference_deg":10,"max_radar_valid_fraction_difference":.1}
    matched=terrain_match({"lane_pixels":pixels,"matching_thresholds":limits,"coherence_threshold":.4})
    self.assertEqual(matched["status"],"matched")
    self.assertEqual(len(matched["sections"]),2)
    for pixel in pixels["control_b"]: pixel["land_cover"]="urban"
    unmatched=terrain_match({"lane_pixels":pixels,"matching_thresholds":limits,"coherence_threshold":.4})
    self.assertEqual(unmatched["status"],"partial_or_unmatched")

  def test_common_regional_motion_is_retained_and_relative_signal_is_zero(self):
    result = evaluate_three_lane([sample(i * 80, 18, 17, 19) for i in range(4)], min_sections=3)
    self.assertEqual(result["status"], "shared_or_no_material_difference")
    self.assertTrue(all(row["common_motion_mm"] == 18 for row in result["sections"]))
    self.assertTrue(all(row["asset_relative_mm"] == 0 for row in result["sections"]))

  def test_asset_relative_difference_creates_candidate(self):
    result = evaluate_three_lane([sample(i * 80, 25, 2, 3) for i in range(3)],
                                 candidate_threshold_mm=10, min_sections=3)
    self.assertEqual(result["status"], "candidate_asset_relative_difference")
    self.assertTrue(all(row["asset_relative_mm"] == 22.5 for row in result["sections"]))

  def test_controls_that_disagree_are_ambiguous_and_low_pixel_count_is_no_call(self):
    result = evaluate_three_lane([
        sample(0, 10, 0, 40), sample(80, 10, 0, 35), sample(160, 10, 0, 30),
        sample(240, 10, 10, 11, count=1),
    ], max_control_disagreement_mm=10, min_sections=3)
    self.assertEqual(result["status"], "ambiguous_controls")
    self.assertEqual(result["ambiguous_count"], 3)
    self.assertEqual(result["no_call_count"], 1)
    self.assertIn("insufficient_valid_pixels", result["sections"][-1]["reasons"][0])

  def test_one_terrain_mismatch_is_ambiguous_only_at_that_chainage(self):
    rows=[sample(i*80,18,17,19) for i in range(4)]
    rows[2]=LaneSample(160,18,17,19,12,12,12,control_a_terrain_match=False,control_b_terrain_match=True)
    result=evaluate_three_lane(rows,min_sections=3)
    self.assertEqual(result["sections"][2]["status"],"ambiguous")
    self.assertEqual(result["sections"][2]["reasons"],["control_a_terrain_or_radar_mismatch"])
    self.assertEqual(result["usable_section_count"],3)

  def test_invalid_settings_and_duplicate_chainage_are_rejected(self):
    with self.assertRaises(ValueError):
        evaluate_three_lane([sample(0, 1, 1, 1)], min_valid_pixels=0)
    with self.assertRaises(ValueError):
        evaluate_three_lane([sample(0, 1, 1, 1), sample(0, 2, 2, 2)])
    with self.assertRaises(ValueError):
        evaluate_three_lane([sample(float("nan"),1,1,1)])

  def test_dual_band_is_unavailable_until_compatible_products_exist(self):
    self.assertEqual(compare_band_summaries(None, None)["status"], "unavailable")
    left = {"start_time":"2026-01-01", "end_time":"2026-01-13", "geometry_id":"A", "polarization":"HH", "support_m":80, "asset_relative_mm":3}
    right = {**left, "geometry_id":"B", "asset_relative_mm":4}
    self.assertEqual(compare_band_summaries(left, right)["status"], "not_comparable")

  def test_temporal_series_does_not_infer_trend_from_one_pair(self):
    self.assertEqual(summarize_series([{"acquired":"2026-01-01", "asset_relative_mm":1}])["status"], "unavailable")

  def test_aspect_difference_wraps_at_north_and_terrain_mismatch_is_rejected(self):
    self.assertEqual(circular_difference_degrees(359, 1), 2)
    asset={"elevation_median_m":100,"slope_median_deg":25,"aspect_mean_deg":359,"land_cover_mode":"forest","radar_valid_fraction":.8}
    good={"elevation_median_m":110,"slope_median_deg":27,"aspect_mean_deg":1,"land_cover_mode":"forest","radar_valid_fraction":.75}
    limits={"max_elevation_difference_m":30,"max_slope_difference_deg":5,"max_aspect_difference_deg":10,"max_radar_valid_fraction_difference":.2}
    self.assertTrue(compare_control_covariates(asset,good,limits)["matched"])
    bad={**good,"land_cover_mode":"urban"}
    self.assertFalse(compare_control_covariates(asset,bad,limits)["matched"])

  def test_flat_terrain_aspect_is_not_fabricated_or_used_as_a_mismatch(self):
    from backend.terrain_matching import summarize_lane_covariates
    flat=[{"elevation_m":100,"slope_deg":0,"aspect_deg":None,"land_cover":"forest","coherence":.8}]
    summary=summarize_lane_covariates(flat,.4)
    self.assertIsNone(summary["aspect_mean_deg"])
    limits={"max_elevation_difference_m":10,"max_slope_difference_deg":2,"max_aspect_difference_deg":10,"max_radar_valid_fraction_difference":.2}
    check=compare_control_covariates(summary,summary,limits)
    self.assertTrue(check["matched"])
    self.assertIsNone(check["metrics"]["aspect_abs_difference_deg"])

  def test_api_requires_measured_control_matching_and_pdf_export_is_valid(self):
    with self.assertRaises(HTTPException) as error:
      three_lane(AnalysisRequest(samples=[sample(i*80,25,2,3) for i in range(3)]))
    self.assertEqual(error.exception.status_code,422)
    provenance={"cmr_granule_id":"TEST-GRANULE","cmr_metadata_url":"https://example.test/granule","collection_short_name":"NISAR_L2_GUNW_PROVISIONAL_V1","processing_maturity":"PROVISIONAL","acquisition_start":"2026-01-01","acquisition_end":"2026-01-13","orbit_geometry_id":"SYNTHETIC-TEST","look_direction":"right","polarization":"HH","hdf5_granule_id":"TEST-GRANULE","cmr_identity_matches_hdf5":True,"cmr_record_reviewed":True,"footprint_intersection":True,"phase_convention_reviewed":True,"reference_secondary_order":"synthetic test fixture"}
    self.assertFalse(validate_product_record(provenance,"TEST-GRANULE"))
    matches=[{"chainage_m":i*80,"controls":{"control_a":{"matched":True},"control_b":{"matched":True}}} for i in range(3)]
    lane_geojson={"type":"FeatureCollection","features":[{"type":"Feature","properties":{"lane":"asset","geometry_role":"nominal_sample_support"},"geometry":{"type":"Polygon","coordinates":[[[0,0],[1,0],[1,1],[0,1],[0,0]]]}}]}
    request=AnalysisRequest(corridor_name="Test",granule_id="TEST-GRANULE",provenance=provenance,terrain_matches=matches,
                            samples=[sample(i*80,25,2,3) for i in range(3)],lane_geojson=lane_geojson)
    result=three_lane(request)
    self.assertEqual(result["lane_geojson"],lane_geojson)
    result["cases"][0]["temporal_history"]={"status":"persistent","valid_observations":3,
      "asset_absolute_net_change_mm":4.5,"asset_relative_net_change_mm":2.5,"asset_relative_range_mm":1.0,
      "observations":[{"date":"2026-01-13","granule_id":"TEST-PAIR-3","asset_los_mm":25.0,"background_los_mm":2.5,"asset_relative_mm":22.5}],
      "missing_observations":[{"date":"2026-01-25","granule_id":"TEST-PAIR-4","reason":"no_call"}]}
    result["cases"][0]["reference_robustness"]={"classification":"reference_sensitive","median_signal_spread_mm":6.0,
      "scenarios":[{"configuration":"control_a_only","status":"evaluated","asset_relative_mm":23.0}],
      "method":"Alternative references recalculated from matched supplied controls."}
    response=export_result("report",ExportRequest(corridor_name="Test",granule_id="TEST-GRANULE",result=result,provenance=provenance))
    self.assertEqual(response.media_type,"application/pdf")
    self.assertTrue(response.body.startswith(b"%PDF-1.4"))
    self.assertIn(b"Observation history",response.body)
    self.assertIn(b"TEST-PAIR-3",response.body)
    self.assertIn(b"TEST-PAIR-4",response.body)
    self.assertIn(b"Reference robustness: reference_sensitive",response.body)
    self.assertIn(b"control_a_only",response.body)
    geojson_response=export_result("geojson",ExportRequest(corridor_name="Test",granule_id="TEST-GRANULE",result=result,provenance=provenance))
    geojson=json.loads(geojson_response.body)
    self.assertEqual(geojson["features"][0]["properties"]["geometry_role"],"nominal_sample_support")
    self.assertIn("nominal sampled-window unions",geojson["note"])

  def test_product_validation_catches_unverified_footprint_and_phase_order(self):
    record={"cmr_granule_id":"A","cmr_metadata_url":"url","collection_short_name":"NISAR_L2_GUNW_PROVISIONAL_V1","processing_maturity":"PROVISIONAL","acquisition_start":"x","acquisition_end":"y","orbit_geometry_id":"o","look_direction":"right","polarization":"HH","hdf5_granule_id":"A","cmr_identity_matches_hdf5":True,"cmr_record_reviewed":False,"footprint_intersection":False,"phase_convention_reviewed":False,"reference_secondary_order":""}
    gaps=validate_product_record(record,"A")
    self.assertIn("confirmed centerline/footprint intersection",gaps)
    self.assertIn("reviewed phase convention",gaps)
    self.assertIn("reference_secondary_order",gaps)

  def test_exact_footprint_intersection_not_bbox_overlap(self):
    footprint = {"type":"Polygon", "coordinates":[[[0,0],[2,0],[2,2],[0,2],[0,0]]]}
    route_hit = {"type":"LineString", "coordinates":[[1,0.2],[1,1.8]]}
    route_miss = {"type":"LineString", "coordinates":[[3,0],[3,2]]}
    self.assertTrue(intersects_geojson(footprint, route_hit))
    self.assertFalse(intersects_geojson(footprint, route_miss))
    feature_collection={"type":"FeatureCollection","features":[{"type":"Feature","properties":{},"geometry":route_hit}]}
    self.assertTrue(shape(footprint).intersects(corridor_geometry(feature_collection)))
