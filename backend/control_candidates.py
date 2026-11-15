"""Generate and terrain-screen candidate control lanes around a WGS84 route."""
from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from shapely.geometry import LineString, mapping, shape
from shapely.ops import transform as transform_geometry

from backend.terrain_raster import _sample_dem, _sample_land_cover


def load_route(path: Path) -> LineString:
    doc = json.loads(path.read_text(encoding="utf-8"))
    items = doc.get("features", []) if doc.get("type") == "FeatureCollection" else [doc]
    lines = []
    for item in items:
        geom = item.get("geometry") if item.get("type") == "Feature" else item
        if geom and geom.get("type") == "LineString":
            lines.append(shape(geom))
    if len(lines) != 1 or not isinstance(lines[0], LineString):
        raise ValueError("Provide exactly one WGS84 LineString as the asset alignment.")
    route = lines[0]
    if route.is_empty or not route.is_valid or len(route.coords) < 2 or route.length <= 0:
        raise ValueError("Asset centerline must contain at least two distinct valid coordinates.")
    if any(not (-180 <= lon <= 180 and -90 <= lat <= 90) for lon, lat, *_ in route.coords):
        raise ValueError("Asset centerline coordinates must be WGS84 longitude/latitude.")
    return route


def local_projected_crs(route: LineString) -> CRS:
    center_lon = sum(point[0] for point in route.coords) / len(route.coords)
    center_lat = sum(point[1] for point in route.coords) / len(route.coords)
    if center_lat >= 84:
        return CRS.from_epsg(32661)
    if center_lat <= -80:
        return CRS.from_epsg(32761)
    zone = max(1, min(60, int((center_lon + 180) // 6) + 1))
    return CRS.from_epsg((32600 if center_lat >= 0 else 32700) + zone)


def offset_candidate(route: LineString, offset_m: float, side: str, spacing_m: float) -> LineString:
    total = float(route.length)
    distances = list(np.arange(0.0, total, spacing_m, dtype=float))
    if not distances or total - distances[-1] > 1e-6:
        distances.append(total)
    delta = min(max(spacing_m * 0.25, 1.0), total / 4.0)
    sign = 1.0 if side == "left" else -1.0
    coords = []
    for distance in distances:
        point = route.interpolate(float(distance))
        before = route.interpolate(max(0.0, float(distance) - delta))
        after = route.interpolate(min(total, float(distance) + delta))
        dx, dy = float(after.x - before.x), float(after.y - before.y)
        length = math.hypot(dx, dy)
        if length <= 1e-9:
            raise ValueError(f"Cannot determine local route direction near chainage {distance:.1f} m.")
        nx, ny = -dy / length * sign, dx / length * sign
        coords.append((float(point.x + nx * offset_m), float(point.y + ny * offset_m)))
    candidate = LineString(coords)
    if not candidate.is_valid or not candidate.is_simple or candidate.length <= 0:
        raise ValueError(f"{side} {offset_m:g} m offset folds back or self-intersects; reject this candidate geometry.")
    return candidate


def _terrain_summary_at(point, radius_m, dem, land_cover, to_dem, to_cover, elevation_units):
    x, y = to_dem.transform(point.x, point.y)
    row, col = dem.index(x, y)
    if row < 0 or col < 0 or row >= dem.height or col >= dem.width:
        return None
    transform = dem.transform
    row_radius = max(1, math.ceil(radius_m / max(abs(transform.d), abs(transform.e))))
    col_radius = max(1, math.ceil(radius_m / max(abs(transform.a), abs(transform.b))))
    elevations, slopes, aspects, covers = [], [], [], []
    for r in range(max(0, row - row_radius), min(dem.height, row + row_radius + 1)):
        for c in range(max(0, col - col_radius), min(dem.width, col + col_radius + 1)):
            px, py = dem.xy(r, c, offset="center")
            if (px - x) ** 2 + (py - y) ** 2 > radius_m ** 2:
                continue
            terrain = _sample_dem(dem, px, py, 1.0 if elevation_units == "m" else 0.3048)
            if terrain is None:
                continue
            cover_x, cover_y = to_cover.transform(px, py)
            cover = _sample_land_cover(land_cover, cover_x, cover_y)
            if cover is None:
                continue
            elevation, slope, aspect = terrain
            elevations.append(elevation)
            slopes.append(slope)
            if aspect is not None and slope >= 0.1:
                aspects.append(aspect)
            covers.append(cover)
    if not elevations:
        return None
    aspect_mean = None
    if aspects:
        xmean = sum(math.cos(math.radians(a)) for a in aspects)
        ymean = sum(math.sin(math.radians(a)) for a in aspects)
        aspect_mean = math.degrees(math.atan2(ymean, xmean)) % 360
    return {"elevation_median_m": median(elevations), "slope_median_deg": median(slopes),
            "aspect_mean_deg": aspect_mean, "land_cover_mode": Counter(covers).most_common(1)[0][0],
            "terrain_pixel_count": len(elevations)}


def _terrain_match(asset: dict | None, candidate: dict | None, thresholds: dict) -> dict[str, Any]:
    if asset is None or candidate is None:
        return {"matched": False, "reason": "insufficient DEM/land-cover coverage", "checks": {}}
    elevation = abs(asset["elevation_median_m"] - candidate["elevation_median_m"])
    slope = abs(asset["slope_median_deg"] - candidate["slope_median_deg"])
    aspect_defined = (asset["aspect_mean_deg"] is not None and candidate["aspect_mean_deg"] is not None
                      and asset["slope_median_deg"] >= .1 and candidate["slope_median_deg"] >= .1)
    aspect = abs((asset["aspect_mean_deg"] - candidate["aspect_mean_deg"] + 180) % 360 - 180) if aspect_defined else None
    cover = asset["land_cover_mode"] == candidate["land_cover_mode"]
    checks = {"elevation": elevation <= thresholds["max_elevation_difference_m"],
              "slope": slope <= thresholds["max_slope_difference_deg"],
              "aspect": aspect <= thresholds["max_aspect_difference_deg"] if aspect_defined else True,
              "land_cover": cover}
    return {"matched": all(checks.values()), "checks": checks,
            "metrics": {"elevation_abs_difference_m": elevation, "slope_abs_difference_deg": slope,
                        "aspect_abs_difference_deg": aspect, "land_cover_match": cover,
                        "terrain_pixel_count": candidate["terrain_pixel_count"]},
            "asset_summary": asset, "candidate_summary": candidate,
            "note": "Radar coherence and valid-pixel coverage have not yet been evaluated; the GUNW sampler must check those before analysis."}


def screen_control_candidates(centerline_path: Path, dem_path: Path, land_cover_path: Path,
                              offsets_m: list[float], *, radius_m=80.0, spacing_m=160.0,
                              elevation_units="m", thresholds=None, min_matched_fraction=.8):
    if not offsets_m or any(not math.isfinite(float(v)) or float(v) <= 0 for v in offsets_m):
        raise ValueError("Provide one or more positive finite control offsets in metres.")
    if radius_m <= 0 or spacing_m <= 0 or not 0 < min_matched_fraction <= 1:
        raise ValueError("Radius and spacing must be positive; matched fraction must be in (0,1].")
    thresholds = thresholds or {"max_elevation_difference_m": 30.0, "max_slope_difference_deg": 5.0,
                                "max_aspect_difference_deg": 15.0}
    route_wgs84 = load_route(centerline_path)
    source_crs = local_projected_crs(route_wgs84)
    to_projected = Transformer.from_crs(CRS.from_epsg(4326), source_crs, always_xy=True)
    to_wgs84 = Transformer.from_crs(source_crs, CRS.from_epsg(4326), always_xy=True)
    route = transform_geometry(to_projected.transform, route_wgs84)
    if not route.is_simple:
        raise ValueError("Imported route self-intersects after projection; split or repair it before candidate generation.")
    distances = list(np.arange(0.0, route.length, spacing_m, dtype=float))
    if not distances or route.length - distances[-1] > 1e-6:
        distances.append(float(route.length))
    candidates, features = [], []
    with rasterio.open(dem_path) as dem, rasterio.open(land_cover_path) as land_cover:
        if dem.crs is None or land_cover.crs is None:
            raise ValueError("DEM and land-cover rasters must declare CRS metadata.")
        dem_crs = CRS.from_user_input(dem.crs)
        if not dem_crs.is_projected or not dem_crs.axis_info or any(
            abs(float(axis.unit_conversion_factor or 0) - 1.0) > 1e-9 for axis in dem_crs.axis_info[:2]
        ):
            raise ValueError("DEM must use a projected CRS whose horizontal axes are in metres before candidate screening.")
        if not land_cover.dtypes[0].startswith(("int", "uint")):
            raise ValueError("Land-cover raster must use integer category codes.")
        to_dem = Transformer.from_crs(source_crs, dem_crs, always_xy=True)
        to_cover = Transformer.from_crs(dem_crs, CRS.from_user_input(land_cover.crs), always_xy=True)
        asset_summaries = [_terrain_summary_at(route.interpolate(float(d)), radius_m, dem, land_cover,
                                                to_dem, to_cover, elevation_units) for d in distances]
        route_line = transform_geometry(to_wgs84.transform, route)
        features.append({"type": "Feature", "properties": {"lane": "asset", "candidate_id": "asset", "role": "infrastructure alignment"}, "geometry": mapping(route_line)})
        for side in ("left", "right"):
            for offset in sorted(set(float(value) for value in offsets_m)):
                candidate_id = f"{side}_{offset:g}m"
                try:
                    line = offset_candidate(route, offset, side, spacing_m)
                    line_wgs84 = transform_geometry(to_wgs84.transform, line)
                    candidate_coords = list(line.coords)
                    candidate_chainages = np.concatenate(([0.0], np.cumsum([
                        math.hypot(candidate_coords[i + 1][0] - candidate_coords[i][0],
                                   candidate_coords[i + 1][1] - candidate_coords[i][1])
                        for i in range(len(candidate_coords) - 1)
                    ])))
                    chainage_rows = []
                    for distance, asset_summary in zip(distances, asset_summaries):
                        candidate_distance = float(np.interp(float(distance), distances, candidate_chainages))
                        point = line.interpolate(candidate_distance)
                        summary = _terrain_summary_at(point, radius_m, dem, land_cover,
                                                      to_dem, to_cover, elevation_units)
                        chainage_rows.append({"chainage_m": float(distance),
                                              **_terrain_match(asset_summary, summary, thresholds)})
                    match_fraction = sum(row["matched"] for row in chainage_rows) / max(1, len(chainage_rows))
                    eligible = match_fraction >= min_matched_fraction
                    record = {"candidate_id": candidate_id, "side": side, "offset_m": offset,
                              "terrain_eligible": eligible, "matched_fraction": match_fraction,
                              "matched_sections": sum(row["matched"] for row in chainage_rows),
                              "section_count": len(chainage_rows), "sections": chainage_rows,
                              "length_m": float(line.length), "geometry_valid": True,
                              "radar_status": "not_evaluated_until_GUNW_sampling"}
                    candidates.append(record)
                    features.append({"type": "Feature", "properties": {"lane": "control_candidate",
                                     "candidate_id": candidate_id, "side": side, "offset_m": offset,
                                     "terrain_eligible": eligible, "matched_fraction": match_fraction,
                                     "radar_status": "not_evaluated"}, "geometry": mapping(line_wgs84)})
                except ValueError as exc:
                    candidates.append({"candidate_id": candidate_id, "side": side, "offset_m": offset,
                                       "terrain_eligible": False, "geometry_valid": False,
                                       "rejection_reason": str(exc), "radar_status": "not_evaluated_until_GUNW_sampling"})
    return {"corridor_name": centerline_path.stem, "projection_epsg": source_crs.to_epsg(),
            "source_centerline": str(centerline_path.resolve()), "source_dem": str(dem_path.resolve()),
            "source_land_cover": str(land_cover_path.resolve()), "zone_radius_m": radius_m,
            "station_spacing_m": spacing_m, "candidate_offsets_m": sorted(set(float(v) for v in offsets_m)),
            "matching_thresholds": thresholds, "minimum_matched_section_fraction": min_matched_fraction,
            "asset_length_m": float(route.length), "asset_station_count": len(distances),
            "asset_summaries": [{"chainage_m": float(distance), "summary": summary}
                                 for distance, summary in zip(distances, asset_summaries)],
            "candidates": candidates,
            "method": "Create parallel offset candidate centerlines at explicitly supplied distances, then compare DEM elevation, slope, aspect (when defined), and land-cover class to the asset support at shared chainage stations. Terrain eligibility is preliminary; radar coherence, connected-component, subswath, and valid-pixel gates run only in the subsequent GUNW sampler.",
            "geojson": {"type": "FeatureCollection", "features": features}}


def select_control_pair(result: dict[str, Any], control_a_id: str, control_b_id: str) -> dict[str, Any]:
    """Return sampler-ready aligned lane geometry for two analyst-selected candidates."""
    candidates = {item["candidate_id"]: item for item in result["candidates"]}
    if control_a_id == control_b_id:
        raise ValueError("Control A and Control B must be two distinct candidate lanes.")
    selected = []
    for candidate_id in (control_a_id, control_b_id):
        candidate = candidates.get(candidate_id)
        if candidate is None:
            raise ValueError(f"Unknown control candidate: {candidate_id}.")
        if not candidate.get("terrain_eligible"):
            raise ValueError(f"Candidate {candidate_id} did not pass the preliminary terrain eligibility screen.")
        selected.append(candidate_id)
    by_id = {feature["properties"].get("candidate_id"): feature
             for feature in result["geojson"]["features"]}
    asset = by_id.get("asset")
    if asset is None or any(candidate_id not in by_id for candidate_id in selected):
        raise ValueError("Candidate geometries are incomplete; regenerate the screening output.")
    lanes = []
    for lane_name, feature_id in (("asset", "asset"), ("control_a", selected[0]), ("control_b", selected[1])):
        original = by_id[feature_id]
        lanes.append({"type": "Feature", "properties": {"lane": lane_name,
                      "candidate_id": feature_id}, "geometry": original["geometry"]})
    return {"type": "FeatureCollection", "features": lanes}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--centerline", type=Path, required=True)
    parser.add_argument("--dem", type=Path, required=True)
    parser.add_argument("--land-cover", type=Path, required=True)
    parser.add_argument("--offsets-m", type=float, nargs="+", required=True)
    parser.add_argument("--radius-m", type=float, default=80)
    parser.add_argument("--spacing-m", type=float, default=160)
    parser.add_argument("--dem-units", choices=("m", "ft"), default="m")
    parser.add_argument("--min-matched-fraction", type=float, default=.8)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--geojson", type=Path, required=True)
    parser.add_argument("--select-a", help="Eligible candidate ID to use as Control A.")
    parser.add_argument("--select-b", help="Different eligible candidate ID to use as Control B.")
    parser.add_argument("--selected-lanes", type=Path,
                        help="Optional sampler-ready three-lane GeoJSON output; requires both --select-a and --select-b.")
    args = parser.parse_args()
    if bool(args.select_a) != bool(args.select_b):
        parser.error("--select-a and --select-b must be supplied together.")
    if args.selected_lanes and not args.select_a:
        parser.error("--selected-lanes requires both --select-a and --select-b.")
    result = screen_control_candidates(args.centerline, args.dem, args.land_cover, args.offsets_m,
                                       radius_m=args.radius_m, spacing_m=args.spacing_m,
                                       elevation_units=args.dem_units,
                                       min_matched_fraction=args.min_matched_fraction)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.geojson.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps({key: value for key, value in result.items() if key != "geojson"}, indent=2), encoding="utf-8")
    args.geojson.write_text(json.dumps(result["geojson"], indent=2), encoding="utf-8")
    if args.select_a:
        selected = select_control_pair(result, args.select_a, args.select_b)
        destination = args.selected_lanes or args.report.with_name("three-lanes-selected.geojson")
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(selected, indent=2), encoding="utf-8")
        print(f"Wrote analyst-selected sampler lanes to {destination}")
    print(f"Wrote {len(result['candidates'])} terrain-screened candidates; {sum(c['terrain_eligible'] for c in result['candidates'])} passed the preliminary terrain gate. Radar quality remains untested.")


if __name__ == "__main__":
    main()
