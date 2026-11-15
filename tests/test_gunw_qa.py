import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np

from backend.gunw_qa import decode_gunw_mask, inspect_gunw_quality


class GunwQualityTests(unittest.TestCase):
    def test_decodes_subswaths_anomaly_bytes_iono_bit_and_fill(self):
        values = np.array([12, 10, 0x0100000C, 255], dtype=np.uint32)
        decoded = decode_gunw_mask(values)
        self.assertEqual(decoded["reference_swath"].tolist(), [1, 1, 1, 5])
        self.assertEqual(decoded["secondary_swath"].tolist(), [2, 0, 2, 5])
        self.assertEqual(decoded["both_subswaths_valid"].tolist(), [True, False, True, False])
        self.assertEqual(decoded["ionosphere_phase_masked"].tolist(), [False, False, True, False])
        self.assertEqual(decoded["not_fill"].tolist(), [True, True, True, False])

    def test_reports_only_valid_layer_support_along_projected_route(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            product = root / "tiny.h5"
            route = root / "route.geojson"
            route.write_text(json.dumps({
                "type": "FeatureCollection",
                "features": [{"type": "Feature", "properties": {}, "geometry": {
                    "type": "LineString", "coordinates": [[0.0001, 0.0001], [0.001, 0.001]],
                }}],
            }), encoding="utf-8")
            with h5py.File(product, "w") as h5:
                base = h5.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram")
                grid = base.create_group("HH")
                grid.create_dataset("unwrappedPhase", data=np.ones((4, 4), dtype=np.float32))
                grid.create_dataset("coherenceMagnitude", data=np.full((4, 4), .8, dtype=np.float32))
                cc = grid.create_dataset("connectedComponents", data=np.ones((4, 4), dtype=np.uint16))
                cc.attrs["_FillValue"] = 65535
                mask = base.create_dataset("mask", data=np.full((4, 4), 12, dtype=np.uint32))
                mask.attrs["_FillValue"] = 255
                mask[0, 0] = 10
                base.create_dataset("xCoordinates", data=np.arange(4, dtype=float) * 80 + 166030)
                base.create_dataset("yCoordinates", data=np.arange(4, dtype=float) * -80 + 120)
                projection = base.create_dataset("projection", data=np.uint32(32631))
                projection.attrs["epsg_code"] = 32631
            result = inspect_gunw_quality(product, route)
            self.assertEqual(result["shape"], [4, 4])
            self.assertGreater(result["corridor_raster_cells"], 0)
            self.assertLess(result["validity"]["both_subswaths_valid"]["count"], 16)
            self.assertIn("common_valid_phase_coherence_cc_and_subswaths", result["validity"])


if __name__ == "__main__":
    unittest.main()
