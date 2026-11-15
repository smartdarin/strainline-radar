"""Synthetic terrain fixtures test candidate screening, never real terrain evidence."""
import json
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.control_candidates import screen_control_candidates, select_control_pair


class ControlCandidateTests(unittest.TestCase):
    def build_inputs(self, root: Path):
        centerline = root / "alignment.geojson"
        centerline.write_text(json.dumps({
            "type": "Feature", "properties": {"name": "Synthetic alignment"},
            "geometry": {"type": "LineString", "coordinates": [[75.0, 30.7], [75.005, 30.7]]},
        }), encoding="utf-8")
        dem = root / "dem.tif"
        cover = root / "cover.tif"
        transform = from_origin(498500, 3398500, 10, 10)
        with rasterio.open(dem, "w", driver="GTiff", width=300, height=300, count=1,
                           dtype="float32", crs="EPSG:32643", transform=transform, nodata=-9999) as dst:
            dst.write(np.full((300, 300), 120, dtype=np.float32), 1)
        with rasterio.open(cover, "w", driver="GTiff", width=300, height=300, count=1,
                           dtype="uint8", crs="EPSG:32643", transform=transform, nodata=0) as dst:
            dst.write(np.full((300, 300), 5, dtype=np.uint8), 1)
        return centerline, dem, cover

    def test_screens_candidates_and_selects_two_distinct_sampler_lanes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            centerline, dem, cover = self.build_inputs(root)
            result = screen_control_candidates(centerline, dem, cover, [150, 250],
                                               radius_m=30, spacing_m=100)
            self.assertEqual(len(result["candidates"]), 4)
            self.assertTrue(all(item["terrain_eligible"] for item in result["candidates"]))
            selected = select_control_pair(result, "left_150m", "right_150m")
            self.assertEqual([feature["properties"]["lane"] for feature in selected["features"]],
                             ["asset", "control_a", "control_b"])
            self.assertEqual([feature["properties"]["candidate_id"] for feature in selected["features"]],
                             ["asset", "left_150m", "right_150m"])
            self.assertTrue(all(feature["geometry"]["type"] == "LineString"
                                for feature in selected["features"]))

    def test_rejects_duplicate_or_terrain_ineligible_selection(self):
        with tempfile.TemporaryDirectory() as directory:
            centerline, dem, cover = self.build_inputs(Path(directory))
            result = screen_control_candidates(centerline, dem, cover, [150, 1000],
                                               radius_m=30, spacing_m=100)
            with self.assertRaisesRegex(ValueError, "two distinct"):
                select_control_pair(result, "left_150m", "left_150m")
            with self.assertRaisesRegex(ValueError, "did not pass"):
                select_control_pair(result, "left_150m", "right_1000m")

    def test_rejects_non_metric_dem_crs(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            centerline, dem, cover = self.build_inputs(root)
            transform = from_origin(74.99, 30.71, .0001, .0001)
            with rasterio.open(dem, "w", driver="GTiff", width=20, height=20, count=1,
                               dtype="float32", crs="EPSG:4326", transform=transform) as dst:
                dst.write(np.full((20, 20), 120, dtype=np.float32), 1)
            with self.assertRaisesRegex(ValueError, "projected CRS"):
                screen_control_candidates(centerline, dem, cover, [150], radius_m=30, spacing_m=100)


if __name__ == "__main__":
    unittest.main()

