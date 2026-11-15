"""Regression coverage for real CMR UMM records and railway intersections."""
import json
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from backend import catalog as catalog_module
from backend.main import CatalogRequest, catalog_post, footprint_check


ROOT = Path(__file__).resolve().parents[1]
ROUTE_PATH = ROOT / "StrainLine_Data" / "00_AOI" / "route" / "kalka_shimla_railway_osm_relation_331109.geojson"
G437_ID = "NISAR_L2_PR_GUNW_032_055_A_017_033_4000_SH_20261004T000450_20261004T000524_20261016T000450_20261016T000524_P05023_N_F_J_001"
G437_UMM = {
    "GranuleUR": G437_ID,
    "CollectionReference": {"ShortName": "NISAR_L2_GUNW_PROVISIONAL_V1"},
    "TemporalExtent": {"RangeDateTime": {
        "BeginningDateTime": "2026-10-04T00:04:50.000000Z",
        "EndingDateTime": "2026-10-16T00:05:24.999342Z",
    }},
    "SpatialExtent": {"HorizontalSpatialDomain": {"Geometry": {"GPolygons": [{
        "Boundary": {"Points": [
            {"Latitude": 29.98143, "Longitude": 79.76355},
            {"Latitude": 32.03529, "Longitude": 79.05525},
            {"Latitude": 31.39393, "Longitude": 76.49934},
            {"Latitude": 29.34422, "Longitude": 77.21309},
            {"Latitude": 29.98143, "Longitude": 79.76355},
        ]},
    }]}}},
    "RelatedUrls": [{"Type": "GET DATA", "URL": "https://nisar.asf.earthdatacloud.nasa.gov/example/G4375022208-ASF.h5"}],
}


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


class FakeAsyncClient:
    last_params = None
    last_headers = None

    def __init__(self, timeout):
        self.timeout = timeout

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return False

    async def get(self, _url, *, params, headers):
        type(self).last_params = params
        type(self).last_headers = headers
        return FakeResponse({"items": [{"meta": {"concept-id": "G4375022208-ASF", "collection-concept-id": "C-TEST"}, "umm": G437_UMM}]})


def run_immediately(awaitable):
    """Run test coroutines whose mocked awaits complete without an event loop."""
    try:
        awaitable.send(None)
    except StopIteration as completed:
        return completed.value
    raise AssertionError("A mocked catalog coroutine unexpectedly yielded control.")


class CatalogTests(unittest.TestCase):
    def test_cmr_umm_results_preserve_footprints_and_support_both_collections(self):
        for maturity, short_name in (
            ("provisional", "NISAR_L2_GUNW_PROVISIONAL_V1"),
            ("validated", "NISAR_L2_GUNW_V1"),
        ):
            with patch.object(catalog_module.httpx, "AsyncClient", FakeAsyncClient):
                records = run_immediately(catalog_module.search_granules(
                    "76.9,30.8,77.2,31.2", "2026-10-01", "2026-11-15", maturity
                ))
            self.assertEqual(FakeAsyncClient.last_params["short_name"], short_name)
            self.assertIn("umm_json", catalog_module.CMR)
            self.assertEqual(records[0]["id"], "G4375022208-ASF")
            self.assertEqual(records[0]["umm"], G437_UMM)
            self.assertEqual(records[0]["collection_concept_id"], "C-TEST")
            self.assertEqual(records[0]["links"][0]["href"], G437_UMM["RelatedUrls"][0]["URL"])

    def _request(self, route):
        return CatalogRequest(
            west=76.91, south=30.81, east=77.19, north=31.13,
            start=date(2026, 6, 17), end=date(2026, 11, 15),
            collection="provisional", corridor_geojson=route,
        )

    def test_audited_g437_cmr_footprint_intersects_saved_osm_railway(self):
        self.assertTrue(ROUTE_PATH.is_file(), "The attributed OSM route GeoJSON must exist.")
        route = json.loads(ROUTE_PATH.read_text(encoding="utf-8"))
        entry = {
            "id": "G4375022208-ASF", "title": G437_ID,
            "start": "2026-10-04T00:04:50.000000Z", "end": "2026-10-16T00:05:24.999342Z",
            "links": [], "umm": G437_UMM,
        }
        with patch("backend.main.search_granules", new=AsyncMock(return_value=[entry])):
            result = run_immediately(catalog_post(self._request(route)))
        self.assertEqual(result["outcome"], "products_intersect")
        self.assertEqual(result["intersection_count"], 1)
        self.assertEqual(result["results"][0]["footprint_intersection"], "intersects")
        self.assertEqual(result["results"][0]["umm"], G437_UMM)
        footprint = footprint_check({"corridor_geojson": route, "umm": result["results"][0]["umm"]})
        self.assertEqual(footprint["status"], "intersects")
        self.assertTrue(footprint["exact_vector_intersection"])

    def test_distinguishes_no_products_and_products_without_route_intersection(self):
        route = {"type": "Feature", "geometry": {"type": "LineString", "coordinates": [[70, 20], [70.1, 20.1]]}, "properties": {}}
        with patch("backend.main.search_granules", new=AsyncMock(return_value=[])):
            empty = run_immediately(catalog_post(self._request(route)))
        self.assertEqual(empty["outcome"], "no_products")

        entry = {"id": "G4375022208-ASF", "title": G437_ID, "links": [], "umm": G437_UMM}
        with patch("backend.main.search_granules", new=AsyncMock(return_value=[entry])):
            nonintersecting = run_immediately(catalog_post(self._request(route)))
        self.assertEqual(nonintersecting["outcome"], "products_no_intersection")
        self.assertEqual(nonintersecting["results"][0]["footprint_intersection"], "no_intersection")

    def test_cmr_errors_remain_api_errors(self):
        request = self._request({"type": "LineString", "coordinates": [[76.9, 30.8], [77, 31]]})
        with patch("backend.main.search_granules", new=AsyncMock(side_effect=OSError("network unavailable"))):
            with self.assertRaises(HTTPException) as raised:
                run_immediately(catalog_post(request))
        self.assertEqual(raised.exception.status_code, 502)
        self.assertIn("NASA CMR search failed", raised.exception.detail)


if __name__ == "__main__":
    unittest.main()
