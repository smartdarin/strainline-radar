"""Sample asset/control lanes from one NISAR L2 GUNW pair.

The three input lines must already be aligned by chainage and spatial support.
DEM and categorical land-cover covariates are sampled from user-supplied,
traceable rasters because GUNW does not contain those terrain layers.
"""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path
from statistics import median

import h5py
import numpy as np
from pyproj import CRS, Transformer
from shapely import wkt as shapely_wkt
from shapely.geometry import LineString, mapping, shape
from shapely.ops import transform as project_geometry, unary_union

from backend.gunw_reader import dataset_paths, get_center_frequency, get_epsg, is_fill_value, nearest_axis_index, phase_to_range_change_mm, validate_phase_units
from backend.gunw_metadata import inspect_gunw
from backend.terrain_raster import enrich_lane_pixels, raster_provenance, sha256_file


def load_lanes(path: Path) -> dict[str, LineString]:
    doc = json.loads(path.read_text(encoding="utf-8"))
    features = doc.get("features") if doc.get("type") == "FeatureCollection" else [doc]
    lanes = {}
    for f in features:
        geom = f.get("geometry") if f.get("type") == "Feature" else f
        name = f.get("properties", {}).get("lane") if f.get("type") == "Feature" else None
        if name in ("asset", "control_a", "control_b") and geom and geom.get("type") == "LineString":
            if name in lanes: raise ValueError(f"Duplicate lane named {name}.")
            line = shape(geom)
            if not isinstance(line, LineString) or line.is_empty or not line.is_valid or len(line.coords) < 2:
                raise ValueError(f"Invalid {name} LineString.")
            if any(not (-180 <= x <= 180 and -90 <= y <= 90) for x,y,*_ in line.coords):
                raise ValueError(f"{name} coordinates must be WGS84 lon/lat.")
            lanes[name] = line
    if set(lanes) != {"asset", "control_a", "control_b"}:
        raise ValueError("Provide exactly three LineString features with lane=asset, control_a, and control_b.")
    return lanes


def lane_window(h5, phase_ds, coherence_ds, components_ds, mask_ds, group_path, ionosphere_ds,
                sigma_ds, x_axis, y_axis, point, radius_m, min_coherence, factor_mm):
    ix, iy = nearest_axis_index(x_axis, point.x), nearest_axis_index(y_axis, point.y)
    if ix is None or iy is None: return {"value":None,"count":0,"quality":"outside_gunw_grid","component":None,"swath":None,"pixels":[]}
    dx = float(np.median(np.abs(np.diff(x_axis)))); dy = float(np.median(np.abs(np.diff(y_axis))))
    rx, ry = max(1, math.ceil(radius_m / dx)), max(1, math.ceil(radius_m / dy))
    xs = np.arange(max(0,ix-rx), min(len(x_axis),ix+rx+1)); ys=np.arange(max(0,iy-ry),min(len(y_axis),iy+ry+1))
    xx,yy=np.meshgrid(x_axis[xs],y_axis[ys]); disk=(xx-point.x)**2+(yy-point.y)**2<=radius_m**2
    if not np.any(disk): return {"value":None,"count":0,"quality":"no_pixels_in_support","component":None,"swath":None,"pixels":[]}
    sl=(slice(int(ys[0]),int(ys[-1])+1),slice(int(xs[0]),int(xs[-1])+1))
    phase=np.asarray(phase_ds[sl],dtype=float); coh=np.asarray(coherence_ds[sl],dtype=float)
    comp=np.asarray(components_ds[sl]); mask=np.asarray(mask_ds[sl])
    ref=(mask//10)%10; sec=mask%10
    valid=disk & np.isfinite(phase) & np.isfinite(coh) & (coh>=min_coherence) & (coh<=1) & (comp>0) & (ref>0) & (sec>0) & (mask//100==0) & (mask!=255)
    valid &= np.vectorize(lambda v: not is_fill_value(phase_ds,v))(phase)
    valid &= np.vectorize(lambda v: not is_fill_value(coherence_ds,v))(coh)
    valid &= np.vectorize(lambda v: not is_fill_value(components_ds,v))(comp)
    valid &= np.vectorize(lambda v: not is_fill_value(mask_ds,v))(mask)
    component = None; pair = None
    if np.any(valid):
        component_ids, counts=np.unique(comp[valid],return_counts=True); component=int(component_ids[np.argmax(counts)])
        selected=valid & (comp==component)
        swath_pairs=np.stack((ref[selected],sec[selected]),axis=1)
        pairs,pair_counts=np.unique(swath_pairs,axis=0,return_counts=True); pair=pairs[np.argmax(pair_counts)]
        selected &= (ref==pair[0]) & (sec==pair[1])
    else:
        selected=np.zeros_like(valid,dtype=bool)
    product_mask_valid = disk & (comp>0) & (ref>0) & (sec>0) & (mask//100==0) & (mask!=255)
    product_mask_valid &= np.vectorize(lambda v: not is_fill_value(components_ds,v))(comp)
    product_mask_valid &= np.vectorize(lambda v: not is_fill_value(mask_ds,v))(mask)
    component_support = product_mask_valid & np.isfinite(phase)
    component_support &= np.vectorize(lambda v: not is_fill_value(phase_ds,v))(phase)
    if component is not None:
        component_support &= comp == component
    if pair is not None:
        component_support &= (ref==pair[0]) & (sec==pair[1])
    coherence_present = np.isfinite(coh) & (coh>=0) & (coh<=1)
    coherence_present &= np.vectorize(lambda v: not is_fill_value(coherence_ds,v))(coh)
    phase_present = np.isfinite(phase) & np.vectorize(lambda v: not is_fill_value(phase_ds,v))(phase)
    pixel_rows=[]
    for local_y, local_x in zip(*np.nonzero(disk)):
        pixel_rows.append({"x":float(xx[local_y,local_x]),"y":float(yy[local_y,local_x]),
                           "coherence":float(coh[local_y,local_x]) if coherence_present[local_y,local_x] else None,
                           "component_id":int(comp[local_y,local_x]) if product_mask_valid[local_y,local_x] else None,
                           "reference_subswath":int(ref[local_y,local_x]) if product_mask_valid[local_y,local_x] else None,
                           "secondary_subswath":int(sec[local_y,local_x]) if product_mask_valid[local_y,local_x] else None,
                           "product_mask_valid":bool(product_mask_valid[local_y,local_x]),
                           "phase_valid":bool(phase_present[local_y,local_x]),
                           "mask_valid":bool(component_support[local_y,local_x]),
                           "los_range_change_proxy_mm":float(phase[local_y,local_x]*factor_mm) if phase_present[local_y,local_x] else None})
    if not np.any(selected):
        return {"value":None,"count":0,"quality":"no_valid_pixels","component":component,"swath":pair.tolist() if pair is not None else None,"pixels":pixel_rows}
    values=(phase[selected]*factor_mm).astype(float)
    if len(values)==0: return {"value":None,"count":0,"quality":"no_valid_pixels","component":component,"swath":pair.tolist(),"pixels":pixel_rows}
    iono = float(np.median(ionosphere_ds[sl][selected])) if ionosphere_ds is not None else None
    sig = float(np.median(sigma_ds[sl][selected])) if sigma_ds is not None else None
    return {"value":float(np.median(values)),"count":int(len(values)),"quality":"ok" if len(values)>=3 else "insufficient_valid_pixels",
            "component":component,"swath":[int(pair[0]),int(pair[1])],"coherence_median":float(np.median(coh[selected])),
            "ionosphere_phase_median_rad":iono,"ionosphere_sigma_median_rad":sig,"pixels":pixel_rows}


def sample_three_lanes(gunw: Path, lanes_path: Path, out: Path, *, polarization="HH", spacing_m=80.0,
                       radius_m=80.0, min_coherence=0.4, terrain_match_path: Path|None=None,
                       dem_path: Path|None=None, land_cover_path: Path|None=None, dem_units="m"):
    if spacing_m<=0 or radius_m<=0 or not 0<=min_coherence<=1: raise ValueError("Spacing/radius must be positive and coherence in [0,1].")
    if (dem_path is None)!=(land_cover_path is None): raise ValueError("Provide both --dem and --land-cover, or neither.")
    lanes=load_lanes(lanes_path)
    hdf5_identity=inspect_gunw(gunw,polarization)
    cmr_sidecar_path=Path(gunw).with_name(Path(gunw).name+".cmr.json")
    cmr_record={}
    if cmr_sidecar_path.is_file():
        sidecar=json.loads(cmr_sidecar_path.read_text(encoding="utf-8"))
        if not isinstance(sidecar,dict) or not isinstance(sidecar.get("cmr_record"),dict):
            raise ValueError("Saved CMR sidecar is malformed; preserve and inspect it before sampling.")
        cmr_record=sidecar["cmr_record"]
    cmr_umm=cmr_record.get("umm",{}) if isinstance(cmr_record.get("umm",{}),dict) else {}
    cmr_granule_id=cmr_umm.get("GranuleUR")
    granule_id=str(hdf5_identity.get("granule_id") or "REVIEW_AND_SET")
    cmr_matches_hdf5=bool(cmr_granule_id and granule_id != "REVIEW_AND_SET" and cmr_granule_id == granule_id)
    collection_short_name=cmr_record.get("collection_short_name", "")
    maturity=("PROVISIONAL" if "PROVISIONAL" in str(collection_short_name).upper()
              else "VALIDATED" if "VALIDATED" in str(collection_short_name).upper() else "REVIEW_AND_SET")
    cmr_concept_id=cmr_record.get("id")
    cmr_metadata_url=(f"https://cmr.earthdata.nasa.gov/search/concepts/{cmr_concept_id}"
                      if isinstance(cmr_concept_id,str) and cmr_concept_id else "")
    footprint_intersection=False
    footprint_wkt=hdf5_identity.get("bounding_polygon_wkt")
    if footprint_wkt:
        product_footprint=shapely_wkt.loads(footprint_wkt)
        if product_footprint.is_empty or not product_footprint.is_valid:
            raise ValueError("GUNW identification boundingPolygon is invalid; exact footprint check cannot pass.")
        footprint_intersection=bool(product_footprint.intersects(lanes["asset"]))
    reference_start=hdf5_identity.get("reference_start") or ""
    reference_end=hdf5_identity.get("reference_end") or ""
    secondary_start=hdf5_identity.get("secondary_start") or ""
    secondary_end=hdf5_identity.get("secondary_end") or ""
    track=hdf5_identity.get("track_number")
    frame=hdf5_identity.get("frame_number")
    pass_direction=hdf5_identity.get("orbit_pass_direction")
    look_direction=hdf5_identity.get("look_direction")
    geometry_parts=[f"track={track}" if track is not None else None,
                    f"frame={frame}" if frame is not None else None,
                    f"pass={pass_direction}" if pass_direction else None,
                    f"look={look_direction}" if look_direction else None]
    orbit_geometry_id=";".join(value for value in geometry_parts if value) or "REVIEW_AND_SET"
    with h5py.File(gunw,"r") as h5:
        phase_path, group, mask_path=dataset_paths(h5,polarization)
        phase_ds=h5[phase_path]; coh_ds=h5[f"{group}/coherenceMagnitude"]; comp_ds=h5[f"{group}/connectedComponents"]; mask_ds=h5[mask_path]
        validate_phase_units(phase_ds)
        iono_ds=h5[f"{group}/ionospherePhaseScreen"] if f"{group}/ionospherePhaseScreen" in h5 else None
        sigma_ds=h5[f"{group}/ionospherePhaseScreenUncertainty"] if f"{group}/ionospherePhaseScreenUncertainty" in h5 else None
        for layer in (coh_ds,comp_ds,mask_ds):
            if layer.shape!=phase_ds.shape: raise ValueError("Phase, coherence, components and mask layers must have identical dimensions.")
        if (iono_ds is None)!=(sigma_ds is None): raise ValueError("Only one ionospheric phase/uncertainty layer exists; inspect this product before sampling.")
        if iono_ds is not None and (iono_ds.shape!=phase_ds.shape or sigma_ds.shape!=phase_ds.shape): raise ValueError("Ionospheric layers must share the GUNW raster dimensions.")
        x_axis=np.asarray(h5[f"{group}/xCoordinates"],dtype=float); y_axis=np.asarray(h5[f"{group}/yCoordinates"],dtype=float)
        epsg=get_epsg(h5[f"{group}/projection"]); freq_path,freq=get_center_frequency(h5)
        factor=phase_to_range_change_mm(1.0,freq)
        to_grid=Transformer.from_crs(CRS.from_epsg(4326),CRS.from_epsg(epsg),always_xy=True)
        projected={name:project_geometry(to_grid.transform,line) for name,line in lanes.items()}
        lengths={name:float(line.length) for name,line in projected.items()}
        if max(lengths.values())-min(lengths.values())>max(spacing_m, 1):
            raise ValueError("Asset and control lines must be chainage-aligned and have comparable lengths.")
        total=min(lengths.values()); distances=list(np.arange(0,total,spacing_m));
        if not distances or total-distances[-1]>1e-6: distances.append(total)
        samples=[]; sampled_lane_pixels={"asset":[],"control_a":[],"control_b":[]}
        to_wgs84=Transformer.from_crs(CRS.from_epsg(epsg),CRS.from_epsg(4326),always_xy=True)
        support_by_lane={name:unary_union([line.interpolate(float(distance)).buffer(radius_m) for distance in distances]) for name,line in projected.items()}
        for chainage in distances:
            records={name:lane_window(h5,phase_ds,coh_ds,comp_ds,mask_ds,group,iono_ds,sigma_ds,x_axis,y_axis,
                                      line.interpolate(chainage),radius_m,min_coherence,factor) for name,line in projected.items()}
            for name, record in records.items():
                lane_center=projected[name].interpolate(float(chainage))
                lane_lon,lane_lat=to_wgs84.transform(lane_center.x,lane_center.y)
                for pixel in record["pixels"]:
                    sampled_lane_pixels[name].append({"chainage_m":float(chainage),"center_x":float(lane_center.x),"center_y":float(lane_center.y),"longitude":float(lane_lon),"latitude":float(lane_lat),**pixel})
            comps={r["component"] for r in records.values() if r["quality"]=="ok"}
            swaths={tuple(r["swath"] or []) for r in records.values() if r["quality"]=="ok"}
            if len(comps)>1 or len(swaths)>1:
                for record in records.values():
                    if record["quality"]=="ok": record["quality"]="cross_lane_component_or_swath_mismatch"
            asset_point=projected["asset"].interpolate(chainage)
            lon,lat=Transformer.from_crs(CRS.from_epsg(epsg),CRS.from_epsg(4326),always_xy=True).transform(asset_point.x,asset_point.y)
            samples.append({"chainage_m":float(chainage),"asset_los_mm":records["asset"]["value"],
                            "control_a_los_mm":records["control_a"]["value"],"control_b_los_mm":records["control_b"]["value"],
                            "asset_valid_pixels":records["asset"]["count"],"control_a_valid_pixels":records["control_a"]["count"],
                            "control_b_valid_pixels":records["control_b"]["count"],"asset_quality":records["asset"]["quality"],
                            "control_a_quality":records["control_a"]["quality"],"control_b_quality":records["control_b"]["quality"],
                            "longitude":float(lon),"latitude":float(lat),
                            "lane_support":{name:{key:value for key,value in record.items() if key!="pixels"} for name,record in records.items()}})
        metadata={"product":"NISAR L2 GUNW","source_file":str(gunw.resolve()),"source_file_sha256":sha256_file(gunw),
                  "centerline_file":str(lanes_path.resolve()),"centerline_sha256":sha256_file(lanes_path),
                  "phase_dataset":phase_path,"coherence_dataset":f"{group}/coherenceMagnitude","mask_dataset":mask_path,
                  "center_frequency_hz":freq,"center_frequency_dataset":freq_path,"projection_epsg":epsg,"polarization":polarization,
                  "phase_to_range_change_proxy_mm":"phase_rad * wavelength_m / (4*pi) * 1000",
                  "sample_spacing_m":spacing_m,"lane_radius_m":radius_m,"min_coherence_screen":min_coherence,
                  "hdf5_granule_id":granule_id,"cmr_granule_id":cmr_granule_id or "",
                  "cmr_identity_matches_hdf5":cmr_matches_hdf5,"cmr_metadata_url":cmr_metadata_url,
                  "cmr_record_reviewed":False,"cmr_record_status":sidecar.get("record_status", "CMR metadata sidecar not found") if cmr_sidecar_path.is_file() else "CMR metadata sidecar not found",
                  "collection_short_name":collection_short_name,"processing_maturity":maturity,
                  "acquisition_start":reference_start,"acquisition_end":secondary_start,
                  "reference_start":reference_start,"reference_end":reference_end,
                  "secondary_start":secondary_start,"secondary_end":secondary_end,
                  "orbit_geometry_id":orbit_geometry_id,"absolute_orbit_number":hdf5_identity.get("absolute_orbit_number"),
                  "look_direction":look_direction or "REVIEW_AND_SET",
                  "footprint_intersection":footprint_intersection,"phase_convention_reviewed":False,
                  "reference_secondary_order":f"reference {reference_start} -> secondary {secondary_start}; signed phase convention review still required",
                  "limitation":"Relative LOS proxies from one interferogram pair. No atmospheric/reference correction, vertical motion inference, external validation, or safety status."}
    terrain=json.loads(terrain_match_path.read_text(encoding="utf-8")) if terrain_match_path else {}
    lane_pixels={}
    ancillary_provenance={}
    if dem_path is not None and land_cover_path is not None:
        lane_pixels=enrich_lane_pixels(sampled_lane_pixels,product_epsg=epsg,dem_path=dem_path,
                                        land_cover_path=land_cover_path,elevation_units=dem_units)
        ancillary_provenance=raster_provenance(dem_path,land_cover_path,dem_units)
    elif terrain.get("lane_pixels"):
        lane_pixels=terrain["lane_pixels"]
        ancillary_provenance=terrain.get("terrain_provenance",{})
    metadata["terrain_raster_provenance"]=ancillary_provenance
    lane_features=[]
    for name in ("asset","control_a","control_b"):
        support_wgs84=project_geometry(to_wgs84.transform,support_by_lane[name])
        line_wgs84=project_geometry(to_wgs84.transform,projected[name])
        lane_features.append({"type":"Feature","properties":{"lane":name,"geometry_role":"nominal_sample_support","radius_m":radius_m,"sample_spacing_m":spacing_m,"interpretation":"Union of nominal circular windows centered at GUNW sample stations; not a valid-pixel footprint."},"geometry":mapping(support_wgs84)})
        lane_features.append({"type":"Feature","properties":{"lane":name,"geometry_role":"centerline"},"geometry":mapping(line_wgs84)})
    request={"corridor_name":lanes_path.stem,"granule_id":granule_id,
             "provenance":metadata,"samples":samples,
             "lane_geojson":{"type":"FeatureCollection","features":lane_features},
             "lane_pixels":lane_pixels,
             "matching_thresholds":terrain.get("matching_thresholds",{
                 "max_elevation_difference_m":100,"max_slope_difference_deg":8,"max_aspect_difference_deg":25,
                 "max_radar_valid_fraction_difference":0.2}),
             "min_valid_pixels":3,"max_control_disagreement_mm":10,"candidate_threshold_mm":10,"min_sections":3}
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(request,indent=2),encoding="utf-8")
    return len(samples)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--gunw",type=Path,required=True);p.add_argument("--lanes",type=Path,required=True,help="GeoJSON FeatureCollection with asset/control_a/control_b LineStrings")
    p.add_argument("--output",type=Path,required=True);p.add_argument("--polarization",choices=("HH","VV"),default="HH");p.add_argument("--spacing-m",type=float,default=80);p.add_argument("--radius-m",type=float,default=80);p.add_argument("--min-coherence",type=float,required=True);p.add_argument("--terrain-match",type=Path,help="Optional previously sampled per-chainage terrain JSON")
    p.add_argument("--dem",type=Path,help="Traceable DEM GeoTIFF in a projected metre CRS")
    p.add_argument("--dem-units",choices=("m","ft"),default="m",help="DEM vertical units, explicitly declared")
    p.add_argument("--land-cover",type=Path,help="Categorical land-cover GeoTIFF; codes compared literally")
    a=p.parse_args()
    try:
        n=sample_three_lanes(a.gunw,a.lanes,a.output,polarization=a.polarization,spacing_m=a.spacing_m,radius_m=a.radius_m,min_coherence=a.min_coherence,terrain_match_path=a.terrain_match,dem_path=a.dem,land_cover_path=a.land_cover,dem_units=a.dem_units)
        print(f"Wrote {n} chainage-aligned Three-Lane samples to {a.output}; terrain matching remains required before API analysis.")
    except (OSError,ValueError,KeyError,json.JSONDecodeError) as exc:
        p.error(str(exc))


if __name__=="__main__": main()
