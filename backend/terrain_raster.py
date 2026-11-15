"""Sample traceable DEM and categorical land-cover rasters at GUNW support pixels."""
from __future__ import annotations

import math
import hashlib
from pathlib import Path
from typing import Any

import numpy as np
import rasterio
from pyproj import CRS, Transformer
from rasterio.windows import Window


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(4 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sample_dem(dem, x: float, y: float, elevation_to_m: float) -> tuple[float, float, float | None] | None:
    row, col = dem.index(x, y)
    if row < 0 or col < 0 or row >= dem.height or col >= dem.width:
        return None
    r0, c0 = max(0, row - 1), max(0, col - 1)
    r1, c1 = min(dem.height, row + 2), min(dem.width, col + 2)
    values = dem.read(1, window=Window(c0, r0, c1 - c0, r1 - r0), masked=True).astype("float64")
    if values.count() < 6 or np.ma.is_masked(values[row - r0, col - c0]):
        return None
    rows, cols = np.mgrid[r0:r1, c0:c1]
    xs, ys = rasterio.transform.xy(dem.transform, rows, cols, offset="center")
    z = np.asarray(values.filled(np.nan), dtype=float) * elevation_to_m
    valid = np.isfinite(z)
    x_grid = np.asarray(xs).reshape(z.shape)
    y_grid = np.asarray(ys).reshape(z.shape)
    design = np.column_stack((x_grid[valid], y_grid[valid], np.ones(int(valid.sum()))))
    coefficients, *_ = np.linalg.lstsq(design, z[valid], rcond=None)
    gx, gy, _ = (float(v) for v in coefficients)
    elevation = float(z[row - r0, col - c0])
    slope = math.degrees(math.atan(math.hypot(gx, gy)))
    aspect = math.degrees(math.atan2(-gx, -gy)) % 360.0 if math.hypot(gx, gy) > 1e-12 else None
    return elevation, slope, aspect


def _sample_land_cover(dataset, x: float, y: float) -> str | None:
    sample = next(dataset.sample([(x, y)], indexes=1, masked=True))
    if np.ma.is_masked(sample[0]):
        return None
    value = float(sample[0])
    if not math.isfinite(value):
        return None
    return str(int(value)) if value.is_integer() else str(value)


def enrich_lane_pixels(
    lane_pixels: dict[str, list[dict[str, Any]]],
    *,
    product_epsg: int,
    dem_path: Path,
    land_cover_path: Path,
    elevation_units: str,
) -> dict[str, list[dict[str, Any]]]:
    """Add DEM-derived elevation/slope/aspect and categorical cover to pixel records.

    DEM must use a projected metre CRS so local plane gradients have a metric
    horizontal basis. Land cover is sampled with nearest-pixel semantics.
    """
    factors = {"m": 1.0, "ft": 0.3048}
    if elevation_units not in factors:
        raise ValueError("DEM vertical units must be explicitly declared as m or ft.")
    with rasterio.open(dem_path) as dem, rasterio.open(land_cover_path) as land_cover:
        if dem.crs is None or land_cover.crs is None:
            raise ValueError("DEM and land-cover rasters must each declare a CRS.")
        dem_crs = CRS.from_user_input(dem.crs)
        if not dem_crs.is_projected or not dem_crs.axis_info or any(
            abs(float(axis.unit_conversion_factor or 0) - 1.0) > 1e-9 for axis in dem_crs.axis_info[:2]
        ):
            raise ValueError("DEM must use a projected CRS whose horizontal axes are in metres; reproject it before sampling.")
        if dem.count < 1 or land_cover.count < 1:
            raise ValueError("DEM and land-cover rasters must contain at least one band.")
        if not np.issubdtype(np.dtype(land_cover.dtypes[0]), np.integer):
            raise ValueError("Land-cover band must use integer category codes; continuous rasters are not valid land-cover classes.")
        source_crs = CRS.from_epsg(product_epsg)
        to_dem = Transformer.from_crs(source_crs, dem_crs, always_xy=True)
        to_land_cover = Transformer.from_crs(source_crs, CRS.from_user_input(land_cover.crs), always_xy=True)
        enriched: dict[str, list[dict[str, Any]]] = {}
        for lane, pixels in lane_pixels.items():
            rows = []
            for pixel in pixels:
                dem_x, dem_y = to_dem.transform(float(pixel["x"]), float(pixel["y"]))
                lc_x, lc_y = to_land_cover.transform(float(pixel["x"]), float(pixel["y"]))
                terrain = _sample_dem(dem, dem_x, dem_y, factors[elevation_units])
                land_cover_code = _sample_land_cover(land_cover, lc_x, lc_y)
                row = dict(pixel)
                if terrain is not None:
                    row["elevation_m"], row["slope_deg"], row["aspect_deg"] = terrain
                if land_cover_code is not None:
                    row["land_cover"] = land_cover_code
                rows.append(row)
            enriched[lane] = rows
        return enriched


def raster_provenance(dem_path: Path, land_cover_path: Path, elevation_units: str) -> dict[str, Any]:
    with rasterio.open(dem_path) as dem, rasterio.open(land_cover_path) as land_cover:
        return {
            "dem": {"source_file": str(dem_path.resolve()), "sha256": sha256_file(dem_path), "crs": str(dem.crs), "band": 1,
                    "horizontal_units": "metres", "vertical_units": elevation_units,
                    "slope_method": "Least-squares plane fitted to valid neighboring DEM cell centers (up to 3x3); slope is atan(horizontal gradient), aspect is downslope compass bearing."},
            "land_cover": {"source_file": str(land_cover_path.resolve()), "sha256": sha256_file(land_cover_path), "crs": str(land_cover.crs),
                           "band": 1, "sampling": "Nearest categorical raster cell; codes compared literally. Verify both lanes use the same classification scheme."},
        }
