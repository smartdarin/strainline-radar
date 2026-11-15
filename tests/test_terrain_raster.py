"""Synthetic GeoTIFF checks; these fixtures are not real terrain or NISAR evidence."""
import tempfile
import unittest
from pathlib import Path

import numpy as np
import rasterio
from rasterio.transform import from_origin

from backend.terrain_raster import enrich_lane_pixels


class TerrainRasterTests(unittest.TestCase):
    def build_rasters(self, root: Path, *, crs="EPSG:32643"):
        transform = from_origin(500000, 3400000, 10, 10)
        dem_values = (100 + np.tile(np.arange(20, dtype=np.float32), (20, 1)))
        dem = root / "synthetic-dem.tif"
        cover = root / "synthetic-land-cover.tif"
        with rasterio.open(dem, "w", driver="GTiff", height=20, width=20, count=1,
                           dtype="float32", crs=crs, transform=transform, nodata=-9999) as dst:
            dst.write(dem_values, 1)
        with rasterio.open(cover, "w", driver="GTiff", height=20, width=20, count=1,
                           dtype="uint8", crs=crs, transform=transform, nodata=0) as dst:
            dst.write(np.full((20, 20), 42, dtype=np.uint8), 1)
        return dem, cover

    def test_samples_elevation_slope_aspect_and_categorical_code(self):
        with tempfile.TemporaryDirectory() as directory:
            dem, cover = self.build_rasters(Path(directory))
            source = {"asset": [{"chainage_m": 0, "x": 500055, "y": 3399955,
                                  "coherence": .8, "phase_valid": True, "mask_valid": True}]}
            sampled = enrich_lane_pixels(source, product_epsg=32643, dem_path=dem,
                                         land_cover_path=cover, elevation_units="m")
            pixel = sampled["asset"][0]
            self.assertAlmostEqual(pixel["elevation_m"], 105)
            self.assertAlmostEqual(pixel["slope_deg"], np.degrees(np.arctan(.1)), places=4)
            self.assertAlmostEqual(pixel["aspect_deg"], 270, places=3)
            self.assertEqual(pixel["land_cover"], "42")
            self.assertEqual(pixel["coherence"], .8)

    def test_rejects_dem_without_projected_metre_crs(self):
        with tempfile.TemporaryDirectory() as directory:
            dem, cover = self.build_rasters(Path(directory), crs="EPSG:4326")
            with self.assertRaisesRegex(ValueError, "projected CRS"):
                enrich_lane_pixels({"asset": []}, product_epsg=32643, dem_path=dem,
                                   land_cover_path=cover, elevation_units="m")

    def test_requires_declared_dem_vertical_units(self):
        with tempfile.TemporaryDirectory() as directory:
            dem, cover = self.build_rasters(Path(directory))
            with self.assertRaisesRegex(ValueError, "explicitly declared"):
                enrich_lane_pixels({"asset": []}, product_epsg=32643, dem_path=dem,
                                   land_cover_path=cover, elevation_units="unknown")


if __name__ == "__main__":
    unittest.main()
