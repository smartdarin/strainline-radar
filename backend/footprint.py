"""Exact vector footprint checks for corridor and CMR UMM granule metadata."""
from shapely.geometry import Polygon, shape
from shapely.ops import unary_union


def intersects_geojson(footprint: dict, corridor: dict) -> bool:
    return shape(footprint).intersects(shape(corridor))


def corridor_geometry(document: dict):
    geometries=[]
    def visit(item):
        if item.get("type")=="FeatureCollection":
            for feature in item.get("features",[]): visit(feature)
        elif item.get("type")=="Feature":
            if item.get("geometry"): visit(item["geometry"])
        elif item.get("type") in ("LineString","MultiLineString"):
            geometries.append(shape(item))
    visit(document)
    if not geometries: raise ValueError("Corridor GeoJSON has no supported line geometry.")
    return unary_union(geometries)


def umm_footprint(umm: dict):
    geometry = umm.get("SpatialExtent", {}).get("HorizontalSpatialDomain", {}).get("Geometry", {})
    polygons = geometry.get("GPolygons") or []
    shapes = []
    for item in polygons:
        boundary = item.get("Boundary", {})
        points = boundary.get("Points") or []
        coords = [(float(p["Longitude"]), float(p["Latitude"])) for p in points if "Longitude" in p and "Latitude" in p]
        if len(coords) >= 3:
            if coords[0] != coords[-1]: coords.append(coords[0])
            shapes.append(Polygon(coords))
    return shapes
