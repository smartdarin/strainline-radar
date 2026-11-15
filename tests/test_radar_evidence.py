import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import h5py
import numpy as np
from pyproj import Transformer

from backend import radar_evidence as evidence


class RadarEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.product = root / f"{evidence.GRANULE_ID}.h5"
        self.sidecar = root / f"{evidence.GRANULE_ID}.h5.cmr.json"
        self.route = root / "railway.geojson"
        with h5py.File(self.product, "w") as h5:
            ident = h5.create_group("science/LSAR/identification")
            fields = {
                "granuleId": evidence.GRANULE_ID, "productType": "GUNW", "productVersion": "1.0.11",
                "productSpecificationVersion": "1.5.0", "trackNumber": 55, "frameNumber": 17,
                "absoluteOrbitNumber": 6209, "lookDirection": "Left", "orbitPassDirection": "Ascending",
                "radarBand": "L", "processingDateTime": "2026-10-18T06:53:21",
                "boundingPolygon": "POLYGON ((76 30, 78 30, 78 32, 76 32, 76 30))",
                "referenceZeroDopplerStartTime": "2026-10-04T00:04:50.000000000",
                "referenceZeroDopplerEndTime": "2026-10-04T00:05:24.999342105",
                "secondaryZeroDopplerStartTime": "2026-10-16T00:04:50.000000000",
                "secondaryZeroDopplerEndTime": "2026-10-16T00:05:24.999342105",
                "isUrgentObservation": "False", "isMixedMode": "False",
            }
            for name, value in fields.items():
                ident.create_dataset(name, data=value)
            base = h5.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram")
            layer = base.create_group("HH")
            phase = layer.create_dataset("unwrappedPhase", data=np.arange(16, dtype=np.float32).reshape(4, 4))
            phase.attrs["units"] = "radians"
            layer.create_dataset("coherenceMagnitude", data=np.full((4, 4), 0.8, dtype=np.float32))
            layer.create_dataset("connectedComponents", data=np.ones((4, 4), dtype=np.uint16))
            mask = base.create_dataset("mask", data=np.full((4, 4), 11, dtype=np.uint32))
            mask.attrs["_FillValue"] = 255
            layer.create_dataset("xCoordinateSpacing", data=80.0)
            layer.create_dataset("yCoordinateSpacing", data=-80.0)
            projection = layer.create_dataset("projection", data=np.uint32(32644))
            projection.attrs["epsg_code"] = 32644
            route_projection = base.create_dataset("projection", data=np.uint32(32644))
            route_projection.attrs["epsg_code"] = 32644
            base.create_dataset("xCoordinates", data=np.arange(4, dtype=np.float64) * 80 + 400000)
            base.create_dataset("yCoordinates", data=np.arange(4, dtype=np.float64) * -80 + 3500000)
            h5["science/LSAR/GUNW/grids/frequencyA"].create_dataset("centerFrequency", data=1.239e9)
        to_wgs84 = Transformer.from_crs(32644, 4326, always_xy=True)
        p0 = to_wgs84.transform(400000, 3500000)
        p1 = to_wgs84.transform(400240, 3499760)
        self.route.write_text(json.dumps({"type": "FeatureCollection", "features": [{
            "type": "Feature", "properties": {"name": "Kalka–Shimla railway"},
            "geometry": {"type": "LineString", "coordinates": [p0, p1]},
        }]}), encoding="utf-8")
        self.sidecar.write_text(json.dumps({
            "download_receipt": {"sha256": "459e67aaf84207f68a5b825c825c4d36952ac709168f636e06f3da95192bf9f2"},
            "cmr_record": {
                "id": "G4375022208-ASF",
                "umm": {
                    "CollectionReference": {"ShortName": "NISAR_L2_GUNW_PROVISIONAL_V1"},
                    "DataGranule": {"ArchiveAndDistributionInformation": [{
                        "Name": self.product.name, "SizeInBytes": self.product.stat().st_size,
                        "Checksum": {"Value": "f6995d15ad0bc7e958ceacb04b5b4bd1", "Algorithm": "MD5"},
                    }]},
                },
            },
        }), encoding="utf-8")
        self.paths = patch.multiple(evidence, PRODUCT=self.product, SIDECAR=self.sidecar, ROUTE=self.route)
        self.paths.start()

    def tearDown(self):
        self.paths.stop()
        self.tmp.cleanup()

    def test_info_reports_real_file_identity_provenance_and_railway_overlay(self):
        info = evidence.get_evidence_info()
        self.assertEqual(info["granule_id"], evidence.GRANULE_ID)
        self.assertEqual(info["maturity"], "Provisional")
        self.assertEqual(info["qa_identification_status"], "FAIL")
        self.assertTrue(info["provenance"]["size_matches_cmr"])
        self.assertEqual(len(info["route_segments"]), 1)
        self.assertIn("phase sign is unresolved", " ".join(info["limitations"]).lower())
        coverage = info["route_coverage"]
        self.assertEqual(coverage["cells_valid"] + coverage["cells_invalid"], coverage["cells_total"])
        self.assertIn("all_touched", coverage["method"])

    def test_preview_is_png_from_supported_layers(self):
        for layer in ("phase", "coherence", "components", "validity"):
            png, headers = evidence.render_preview(layer)
            self.assertTrue(png.startswith(b"\x89PNG\r\n\x1a\n"))
            self.assertEqual(headers["X-Radar-Layer"], layer)
            self.assertEqual(headers["X-Sample-Factor"], "4")

    def test_sample_returns_actual_cell_phase_quality_values_without_displacement(self):
        sample = evidence.sample_cell(2, 1)
        self.assertEqual(sample["phase_radians"], 9.0)
        self.assertEqual(sample["connected_component"], 1)
        self.assertEqual(sample["raw_mask"], 11)
        self.assertTrue(sample["validity_screen"])
        self.assertNotIn("displacement", sample)

    def test_route_cell_adds_segment_distance_and_keeps_actual_radar_values_synchronized(self):
        sample = evidence.locate_route_cell(2, 1)
        self.assertEqual(sample["row"], 2)
        self.assertEqual(sample["column"], 1)
        self.assertEqual(sample["phase_radians"], 9.0)
        self.assertEqual(sample["route_segment"], 1)
        self.assertGreaterEqual(sample["distance_along_segment_m"], 0)
        self.assertIn("not an official railway chainage", sample["chainage_qualification"])
        self.assertNotIn("displacement", sample)


if __name__ == "__main__":
    unittest.main()
