import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
from unittest.mock import patch
from fastapi import HTTPException

from backend.gunw_metadata import inspect_gunw
from backend.main import InspectGunwRequest, inspect_local_gunw


def make_product(path):
    with h5py.File(path, "w") as h5:
        ident = h5.create_group("science/LSAR/identification")
        fields = {
            "granuleId": "NISAR_L2_PR_GUNW_TEST",
            "productType": "GUNW",
            "productVersion": "1.0.0",
            "productSpecificationVersion": "1.1.0",
            "trackNumber": 22,
            "frameNumber": 3,
            "absoluteOrbitNumber": 42,
            "lookDirection": "Right",
            "orbitPassDirection": "Ascending",
            "radarBand": "L",
            "processingDateTime": "2026-08-01T00:00:00",
            "boundingPolygon": "POLYGON ((0 0, 1 0, 1 1, 0 1, 0 0))",
            "referenceZeroDopplerStartTime": "2026-07-01T00:00:00",
            "referenceZeroDopplerEndTime": "2026-07-01T00:01:00",
            "secondaryZeroDopplerStartTime": "2026-07-13T00:00:00",
            "secondaryZeroDopplerEndTime": "2026-07-13T00:01:00",
            "isUrgentObservation": "False",
            "isMixedMode": "False",
        }
        for key, value in fields.items():
            ident.create_dataset(key, data=value)
        grid = h5.create_group("science/LSAR/GUNW/grids/frequencyA")
        grid.create_dataset("centerFrequency", data=1.25e9)
        layer = h5.create_group("science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH")
        phase = layer.create_dataset("unwrappedPhase", data=np.zeros((2, 3), dtype="f4"))
        phase.attrs["units"] = "radians"
        layer.create_dataset("coherenceMagnitude", data=np.ones((2, 3), dtype="f4"))
        layer.create_dataset("connectedComponents", data=np.ones((2, 3), dtype="u2"))
        grid.create_dataset("unwrappedInterferogram/mask", data=np.ones((2, 3), dtype="u1"))
        layer.create_dataset("xCoordinateSpacing", data=80.0)
        layer.create_dataset("yCoordinateSpacing", data=-80.0)
        projection = layer.create_dataset("projection", data=np.uint32(32643))
        projection.attrs["epsg_code"] = 32643


class GunwMetadataTests(unittest.TestCase):
    def test_extracts_documented_identity_pair_and_grid_without_inventing_maturity_or_sign(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.h5"
            make_product(path)
            result = inspect_gunw(path, "HH")
        self.assertEqual(result["granule_id"], "NISAR_L2_PR_GUNW_TEST")
        self.assertEqual(result["reference_start"], "2026-07-01T00:00:00")
        self.assertEqual(result["secondary_start"], "2026-07-13T00:00:00")
        self.assertEqual(result["phase_shape"], [2, 3])
        self.assertEqual(result["projection_epsg"], 32643)
        self.assertIn("verify", result["phase_sign_status"])
        self.assertIn("not_in_hdf5", result["maturity_status"])

    def test_rejects_missing_quality_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "incomplete.h5"
            make_product(path)
            with h5py.File(path, "a") as h5:
                del h5["science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/mask"]
            with self.assertRaisesRegex(ValueError, "mask"):
                inspect_gunw(path)

    def test_rejects_phase_layer_without_radian_units(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "degrees.h5"
            make_product(path)
            with h5py.File(path, "a") as h5:
                h5["science/LSAR/GUNW/grids/frequencyA/unwrappedInterferogram/HH/unwrappedPhase"].attrs["units"] = "degrees"
            with self.assertRaisesRegex(ValueError, "declared in radians"):
                inspect_gunw(path)

    def test_api_inspects_only_a_named_file_under_raw_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "data" / "raw"
            raw.mkdir(parents=True)
            make_product(raw / "test.h5")
            with patch("backend.main.ROOT", Path(tmp)):
                route = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[0.2, 0.5], [0.8, 0.5]]}, "properties": {}}
                result = inspect_local_gunw(InspectGunwRequest(filename="test.h5", corridor_geojson=route))
                self.assertEqual(result["granule_id"], "NISAR_L2_PR_GUNW_TEST")
                self.assertEqual(result["footprint_intersection"], "intersects")
                with self.assertRaises(HTTPException):
                    inspect_local_gunw(InspectGunwRequest(filename="..\\README.md"))


if __name__ == "__main__":
    unittest.main()
