import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import HTTPException

from backend import main, radar_evidence


class PublicDeploymentTests(unittest.TestCase):
    def setUp(self):
        self.product = radar_evidence.PRODUCT
        self.paths = patch.multiple(
            radar_evidence,
            PRODUCT=radar_evidence.DEMO_DATA / "source_hdf5_not_hosted.h5",
        )
        self.paths.start()
        self.mode = patch.object(main, "PACKAGED_DEPLOYMENT", True)
        self.mode.start()
        radar_evidence._packaged_evidence.cache_clear()

    def tearDown(self):
        self.mode.stop()
        self.paths.stop()
        radar_evidence._packaged_evidence.cache_clear()

    def test_fastapi_startup_serves_all_six_workspaces_and_packaged_real_product(self):
        page = Path(main.FRONTEND / "index.html").read_text(encoding="utf-8")
        for label in ("Corridor", "Ground context", "Robustness lab", "Field cases", "Data & provenance", "Radar evidence"):
            self.assertIn(label, page)
        route_paths = {route.path for route in main.app.routes}
        for path in ("/", "/static", "/api/health", "/api/radar-evidence", "/api/radar-evidence/preview/{layer}", "/api/radar-evidence/sample", "/api/radar-evidence/route-location"):
            self.assertIn(path, route_paths)
        health = main.health()
        self.assertEqual(health["data_mode"], "packaged_real_evidence")
        self.assertTrue(health["hdf5_local_only"])
        info = main.radar_evidence_info()
        self.assertEqual(info["cmr_concept_id"], "G4375022208-ASF")
        self.assertEqual(info["route_coverage"]["cells_total"], 1478)
        self.assertEqual(info["route_coverage"]["cells_valid"], 1471)
        self.assertTrue(info["provenance"]["evidence_package_verified"])
        self.assertFalse(info["provenance"]["hdf5_present_on_service"])

    def test_all_four_layers_are_served_from_the_verified_package(self):
        for layer in ("phase", "coherence", "components", "validity"):
            response = main.radar_evidence_preview(layer)
            self.assertEqual(response.media_type, "image/png")
            self.assertTrue(response.body.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(response.headers["X-Radar-Layer"], layer)

    def test_railway_source_cell_inspection_uses_actual_packaged_values(self):
        package = radar_evidence._packaged_evidence()
        cell = package["railway_cells"][250]
        sample = main.radar_evidence_sample(cell["row"], cell["column"])
        self.assertEqual(sample["phase_radians"], cell["phase_radians"])
        self.assertEqual(sample["coherence"], cell["coherence"])
        self.assertEqual(sample["connected_component"], cell["connected_component"])
        self.assertEqual(sample["raw_mask"], cell["raw_mask"])
        nearest = main.radar_evidence_route_location(cell["row"] + 4, cell["column"] + 4)
        self.assertIn("distance_along_segment_m", nearest)
        self.assertIn("not official railway chainage", nearest["chainage_qualification"])

    def test_unavailable_full_product_operations_are_explicit_and_credentials_are_not_needed(self):
        package = radar_evidence._packaged_evidence()
        route_keys = {(cell["row"], cell["column"]) for cell in package["railway_cells"]}
        outside = next((row, col) for row in range(package["grid_shape"][0])
                       for col in range(package["grid_shape"][1]) if (row, col) not in route_keys)
        with self.assertRaises(HTTPException) as unavailable:
            main.radar_evidence_sample(outside[0], outside[1])
        self.assertIn("original HDF5 locally", unavailable.exception.detail)
        with self.assertRaises(HTTPException) as download:
            main.download(main.DownloadRequest(url="https://example.org/product", filename="x.h5"))
        self.assertEqual(download.exception.status_code, 503)
        self.assertIn("public ephemeral service", download.exception.detail)
        with self.assertRaises(HTTPException) as inspect:
            main.inspect_local_gunw(main.InspectGunwRequest(filename="x.h5"))
        self.assertEqual(inspect.exception.status_code, 503)
        self.assertIn("local-only", inspect.exception.detail)


if __name__ == "__main__":
    unittest.main()
