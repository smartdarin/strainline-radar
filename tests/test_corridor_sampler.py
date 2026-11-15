import json
import tempfile
import unittest
from pathlib import Path

import h5py
import numpy as np
from pyproj import Transformer
import rasterio
from rasterio.transform import from_origin

from backend.corridor_sampler import sample_three_lanes
from backend.main import terrain_match
from backend.main import RobustnessRequest, reference_robustness


class CorridorSamplerTests(unittest.TestCase):
    def build_fixture(self, root: Path, *, split_component=False, low_coherence=False, phase_units="radians"):
        h5path=root/"synthetic.h5"; geo_path=root/"lanes.geojson"; out=root/"request.json"
        base="/science/LSAR/GUNW/grids/frequencyA"
        layer=base+"/unwrappedInterferogram/HH"
        x=np.arange(500000,508000,80,dtype=float); y=np.arange(3400000,3392000,-80,dtype=float)
        phase=np.full((len(y),len(x)),.5,dtype=np.float32)
        phase[48:53,:]=2.0; phase[43:48,:]=1.0; phase[53:58,:]=3.0
        coherence=np.full_like(phase,.8); components=np.ones_like(phase,dtype=np.int16); mask=np.full_like(phase,11,dtype=np.uint8)
        if low_coherence: coherence[:]=.1
        if split_component: components[53:58,:]=2
        with h5py.File(h5path,"w") as h5:
            ident=h5.create_group("/science/LSAR/identification")
            ident.create_dataset("granuleId",data="NISAR_L2_PR_GUNW_SYNTHETIC")
            ident.create_dataset("referenceZeroDopplerStartTime",data="2026-07-01T00:00:00Z")
            ident.create_dataset("referenceZeroDopplerEndTime",data="2026-07-01T00:01:00Z")
            ident.create_dataset("secondaryZeroDopplerStartTime",data="2026-07-13T00:00:00Z")
            ident.create_dataset("secondaryZeroDopplerEndTime",data="2026-07-13T00:01:00Z")
            ident.create_dataset("trackNumber",data=22)
            ident.create_dataset("frameNumber",data=3)
            ident.create_dataset("absoluteOrbitNumber",data=42)
            ident.create_dataset("lookDirection",data="Right")
            ident.create_dataset("orbitPassDirection",data="Ascending")
            ident.create_dataset("boundingPolygon",data="POLYGON ((74 30, 76 30, 76 31, 74 31, 74 30))")
            phase_ds=h5.create_dataset(layer+"/unwrappedPhase",data=phase);phase_ds.attrs["units"]=phase_units
            h5.create_dataset(layer+"/coherenceMagnitude",data=coherence)
            h5.create_dataset(layer+"/connectedComponents",data=components)
            h5.create_dataset(layer+"/xCoordinates",data=x)
            h5.create_dataset(layer+"/yCoordinates",data=y)
            projection=h5.create_dataset(layer+"/projection",data=np.int32(32643));projection.attrs["epsg_code"]=32643
            h5.create_dataset(base+"/unwrappedInterferogram/mask",data=mask)
            h5.create_dataset(base+"/centerFrequency",data=np.float64(1.2575e9))
        to_geo=Transformer.from_crs(32643,4326,always_xy=True)
        lanes=[]
        for lane,yc in (("asset",3396000),("control_a",3396400),("control_b",3395600)):
            start=to_geo.transform(501000,yc);end=to_geo.transform(503000,yc)
            lanes.append({"type":"Feature","properties":{"lane":lane},"geometry":{"type":"LineString","coordinates":[start,end]}})
        geo_path.write_text(json.dumps({"type":"FeatureCollection","features":lanes}),encoding="utf-8")
        return h5path,geo_path,out

    def test_samples_three_lines_on_shared_chainage_and_records_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            h5,geo,out=self.build_fixture(Path(tmp))
            count=sample_three_lanes(h5,geo,out,spacing_m=400,radius_m=160,min_coherence=.4)
            result=json.loads(out.read_text())
            self.assertEqual(count,len(result["samples"]))
            self.assertGreaterEqual(count,5)
            row=result["samples"][2]
            self.assertEqual(row["asset_quality"],"ok")
            self.assertEqual(row["control_a_quality"],"ok")
            self.assertEqual(row["control_b_quality"],"ok")
            self.assertGreaterEqual(row["asset_valid_pixels"],3)
            self.assertIsNotNone(row["longitude"])

    def test_coherence_failure_is_explicit_no_call_input(self):
        with tempfile.TemporaryDirectory() as tmp:
            h5,geo,out=self.build_fixture(Path(tmp),low_coherence=True)
            sample_three_lanes(h5,geo,out,spacing_m=400,radius_m=160,min_coherence=.4)
            result=json.loads(out.read_text())
            self.assertTrue(all(s["asset_quality"]=="no_valid_pixels" for s in result["samples"]))

    def test_disconnected_lane_components_withhold_cross_lane_comparison(self):
        with tempfile.TemporaryDirectory() as tmp:
            h5,geo,out=self.build_fixture(Path(tmp),split_component=True)
            sample_three_lanes(h5,geo,out,spacing_m=400,radius_m=160,min_coherence=.4)
            result=json.loads(out.read_text())
            self.assertTrue(all(s["control_b_quality"]=="cross_lane_component_or_swath_mismatch" for s in result["samples"]))

    def test_sampler_rejects_phase_not_declared_in_radians(self):
        with tempfile.TemporaryDirectory() as tmp:
            h5,geo,out=self.build_fixture(Path(tmp),phase_units="degrees")
            with self.assertRaisesRegex(ValueError,"declared in radians"):
                sample_three_lanes(h5,geo,out,spacing_m=400,radius_m=160,min_coherence=.4)

    def test_sampler_extracts_terrain_rasters_at_same_gunw_support(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h5,geo,out=self.build_fixture(root)
            dem=root/"synthetic-dem.tif";cover=root/"synthetic-cover.tif"
            transform=from_origin(500000,3400000,80,80)
            values=(100+np.tile(np.arange(100,dtype=np.float32),(100,1)))
            with rasterio.open(dem,"w",driver="GTiff",height=100,width=100,count=1,dtype="float32",crs="EPSG:32643",transform=transform,nodata=-9999) as dst: dst.write(values,1)
            with rasterio.open(cover,"w",driver="GTiff",height=100,width=100,count=1,dtype="uint8",crs="EPSG:32643",transform=transform,nodata=0) as dst: dst.write(np.full((100,100),7,dtype=np.uint8),1)
            sample_three_lanes(h5,geo,out,spacing_m=400,radius_m=160,min_coherence=.4,dem_path=dem,land_cover_path=cover)
            request=json.loads(out.read_text())
            self.assertTrue(request["lane_pixels"]["asset"])
            self.assertEqual(len(request["lane_geojson"]["features"]),6)
            self.assertEqual(request["lane_geojson"]["features"][0]["properties"]["geometry_role"],"nominal_sample_support")
            record=request["lane_pixels"]["asset"][0]
            self.assertIn("elevation_m",record);self.assertIn("slope_deg",record);self.assertIn("aspect_deg",record)
            self.assertEqual(record["land_cover"],"7")
            self.assertTrue(request["provenance"]["terrain_raster_provenance"]["dem"]["source_file"].endswith("synthetic-dem.tif"))
            self.assertEqual(len(request["provenance"]["source_file_sha256"]),64)
            self.assertEqual(len(request["provenance"]["terrain_raster_provenance"]["land_cover"]["sha256"]),64)
            matching=terrain_match({"lane_pixels":request["lane_pixels"],"matching_thresholds":request["matching_thresholds"],"coherence_threshold":request["provenance"]["min_coherence_screen"]})
            self.assertEqual(matching["matched_sections"],len(request["samples"]))
            robustness=reference_robustness(RobustnessRequest(samples=request["samples"],terrain_matches=matching["sections"],
                lane_pixels=request["lane_pixels"],matching_thresholds=request["matching_thresholds"],
                coherence_threshold=request["provenance"]["min_coherence_screen"],base_radius_m=160,radius_floor_fraction=.5))
            self.assertEqual(robustness["tested_radii_m"],[80,120,160])
            self.assertEqual(len(robustness["scenarios"]),9)

    def test_sampler_populates_hdf5_identity_and_exact_footprint_but_keeps_review_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);h5,geo,out=self.build_fixture(root)
            sidecar={"record_status":"CMR response retained", "cmr_record":{
                "id":"G123-ASF", "collection_short_name":"NISAR_L2_GUNW_PROVISIONAL_V1",
                "umm":{"GranuleUR":"NISAR_L2_PR_GUNW_SYNTHETIC"}}}
            (root/(h5.name+".cmr.json")).write_text(json.dumps(sidecar),encoding="utf-8")
            sample_three_lanes(h5,geo,out,spacing_m=400,radius_m=160,min_coherence=.4)
            request=json.loads(out.read_text())
            provenance=request["provenance"]
            self.assertEqual(request["granule_id"],"NISAR_L2_PR_GUNW_SYNTHETIC")
            self.assertEqual(provenance["cmr_granule_id"],request["granule_id"])
            self.assertTrue(provenance["cmr_identity_matches_hdf5"])
            self.assertEqual(provenance["processing_maturity"],"PROVISIONAL")
            self.assertTrue(provenance["footprint_intersection"])
            self.assertFalse(provenance["cmr_record_reviewed"])
            self.assertFalse(provenance["phase_convention_reviewed"])


if __name__=="__main__": unittest.main()
