"""StrainLine API for catalog search and Three-Lane investigation outputs."""
from __future__ import annotations

import csv
import io
import json
import os
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Literal
from dataclasses import replace
from urllib.parse import urlparse, urlunparse

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from shapely import wkt as shapely_wkt
from shapely.geometry import mapping
from pydantic import BaseModel, Field
import re

from backend.catalog import fetch_granule_by_concept_id, search_granules
from backend.case_generator import build_cases
from backend.control_lane_engine import LaneSample, evaluate_three_lane
from backend.dual_band_check import compare_band_summaries
from backend.footprint import umm_footprint, corridor_geometry
from backend.temporal_analysis import summarize_processed_history, summarize_series
from backend.terrain_matching import compare_control_covariates, summarize_lane_covariates
from backend.download import download_product
from backend.pdf_report import render_field_report
from backend.product_validation import validate_product_record
from backend.reference_robustness import evaluate_reference_robustness, evaluate_spatial_reference_robustness
from backend.gunw_metadata import inspect_gunw
from backend.radar_evidence import get_evidence_info, locate_route_cell, render_preview, sample_cell

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
PACKAGED_DEPLOYMENT = os.environ.get("STRAINLINE_PACKAGED_EVIDENCE", "").strip() == "1"
app = FastAPI(title="StrainLine Ground Context Intelligence", version="0.2.0")
app.mount("/static", StaticFiles(directory=FRONTEND), name="static")


class AnalysisRequest(BaseModel):
    corridor_name: str = "Imported corridor"
    granule_id: str = "not_selected"
    provenance: dict[str, Any] = Field(default_factory=dict)
    terrain_matches: list[dict[str, Any]] = Field(default_factory=list)
    matching_thresholds: dict[str, float] = Field(default_factory=lambda: {
        "max_elevation_difference_m": 100.0, "max_slope_difference_deg": 8.0,
        "max_aspect_difference_deg": 25.0, "max_radar_valid_fraction_difference": 0.2,
    })
    samples: list[LaneSample]
    context_by_chainage: list[dict[str, Any]] = Field(default_factory=list)
    lane_geojson: dict[str, Any] | None = None
    min_valid_pixels: int = Field(default=3, ge=1)
    max_control_disagreement_mm: float = Field(default=10, ge=0)
    candidate_threshold_mm: float = Field(default=10, ge=0)
    min_sections: int = Field(default=3, ge=1)


class ExportRequest(BaseModel):
    corridor_name: str
    granule_id: str
    provenance: dict[str, Any] = Field(default_factory=dict)
    result: dict[str, Any]
    corridor_geojson: dict[str, Any] | None = None


class DownloadRequest(BaseModel):
    url: str
    filename: str
    expected_sha256: str | None = None
    expected_granule_id: str | None = None
    cmr_record: dict[str, Any] | None = None


class CatalogRequest(BaseModel):
    west: float
    south: float
    east: float
    north: float
    start: date
    end: date
    collection: Literal["provisional", "validated"] = "provisional"
    corridor_geojson: dict[str, Any]


class RobustnessRequest(BaseModel):
    samples: list[LaneSample]
    terrain_matches: list[dict[str, Any]]
    min_valid_pixels: int = Field(default=3, ge=1)
    candidate_threshold_mm: float = Field(default=10, ge=0)
    material_change_mm: float = Field(default=5, ge=0)
    max_control_disagreement_mm: float = Field(default=10, ge=0)
    min_sections: int = Field(default=3, ge=1)
    lane_pixels: dict[str, list[dict[str, Any]]] = Field(default_factory=dict)
    matching_thresholds: dict[str, float] = Field(default_factory=dict)
    coherence_threshold: float | None = Field(default=None, ge=0, le=1)
    base_radius_m: float | None = Field(default=None, gt=0)
    radius_floor_fraction: float = Field(default=0.5, gt=0, lt=1)


class InspectGunwRequest(BaseModel):
    filename: str
    polarization: str = "HH"
    corridor_geojson: dict[str, Any] | None = None


class TemporalHistoryRequest(BaseModel):
    observations: list[dict[str, Any]]
    min_observations: int = Field(default=3, ge=3)
    candidate_threshold_mm: float = Field(default=10, ge=0)
    material_change_mm: float = Field(default=5, ge=0)


class TemporalExportRequest(BaseModel):
    history: dict[str, Any]


@app.get("/api/health")
def health():
    from backend.radar_evidence import DEMO_DATA, PRODUCT
    packaged = (DEMO_DATA / "evidence.json").is_file() and (PACKAGED_DEPLOYMENT or not PRODUCT.is_file())
    return {"status": "ok", "real_nisar_loaded": PRODUCT.is_file() or packaged,
            "data_mode": "packaged_real_evidence" if packaged else "local_hdf5" if PRODUCT.is_file() else "no_product",
            "hdf5_local_only": packaged, "dual_band": "unavailable", "temporal": "unavailable"}


@app.get("/api/radar-evidence")
def radar_evidence_info():
    """Metadata and railway geometry for the read-only real-product explorer."""
    try:
        return get_evidence_info()
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HTTPException(422, f"Radar evidence is unavailable: {exc}") from exc


@app.get("/api/radar-evidence/preview/{layer}")
def radar_evidence_preview(layer: str):
    """Render a decimated false-color PNG directly from a documented HDF5 layer."""
    try:
        payload, headers = render_preview(layer)
        return Response(payload, media_type="image/png", headers=headers)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, KeyError) as exc:
        raise HTTPException(422, f"Radar preview is unavailable: {exc}") from exc


@app.get("/api/radar-evidence/sample")
def radar_evidence_sample(row: int, col: int):
    """Return raw values from one actual source-grid cell."""
    try:
        return sample_cell(row, col)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"Radar cell is unavailable: {exc}") from exc


@app.get("/api/radar-evidence/route-location")
def radar_evidence_route_location(row: int, col: int):
    """Inspect a clicked route cell and return local OSM segment distance."""
    try:
        return locate_route_cell(row, col)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc)) from exc
    except IndexError as exc:
        raise HTTPException(422, str(exc)) from exc
    except (OSError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"Railway cell is unavailable: {exc}") from exc


def _validate_catalog_bounds(west: float, south: float, east: float, north: float, start: date, end: date):
    if not (-180 <= west < east <= 180 and -90 <= south < north <= 90) or start > end:
        raise HTTPException(422, "Use valid WGS84 bounds and an ordered date interval.")


def _catalog_result(entries: list[dict], collection: str, corridor_geojson: dict[str, Any] | None = None) -> dict:
    collection_name = "NISAR_L2_GUNW_PROVISIONAL_V1" if collection == "provisional" else "NISAR_L2_GUNW_V1"
    results = [dict(entry) for entry in entries]
    if corridor_geojson is None:
        return {
            "collection": collection_name,
            "collection_maturity": collection,
            "metadata_only": True,
            "outcome": "no_products" if not results else "products_found",
            "results": results,
        }
    try:
        route_shape = corridor_geometry(corridor_geojson)
        intersection_count = 0
        unavailable_count = 0
        for result in results:
            polygons = umm_footprint(result.get("umm", {}))
            if not polygons:
                result["footprint_intersection"] = "unavailable"
                unavailable_count += 1
                continue
            intersects = any(poly.intersects(route_shape) for poly in polygons)
            result["footprint_intersection"] = "intersects" if intersects else "no_intersection"
            intersection_count += int(intersects)
    except Exception as exc:
        raise HTTPException(422, f"Could not check CMR footprints against the corridor: {exc}") from exc

    if not results:
        outcome = "no_products"
    elif intersection_count:
        outcome = "products_intersect"
    elif unavailable_count:
        outcome = "footprint_unavailable"
    else:
        outcome = "products_no_intersection"
    return {
        "collection": collection_name,
        "collection_maturity": collection,
        "metadata_only": True,
        "outcome": outcome,
        "result_count": len(results),
        "intersection_count": intersection_count,
        "footprint_unavailable_count": unavailable_count,
        "results": results,
    }


@app.get("/api/catalog")
async def catalog_get(
    west: float,
    south: float,
    east: float,
    north: float,
    start: date,
    end: date,
    collection: Literal["provisional", "validated"] = "provisional",
):
    _validate_catalog_bounds(west, south, east, north, start, end)
    try:
        entries = await search_granules(f"{west},{south},{east},{north}", start.isoformat(), end.isoformat(), collection)
        return _catalog_result(entries, collection)
    except Exception as exc:
        raise HTTPException(502, f"NASA CMR search failed: {exc}") from exc


@app.post("/api/catalog")
async def catalog_post(request: CatalogRequest):
    _validate_catalog_bounds(request.west, request.south, request.east, request.north, request.start, request.end)
    try:
        entries = await search_granules(
            f"{request.west},{request.south},{request.east},{request.north}",
            request.start.isoformat(), request.end.isoformat(), request.collection,
        )
        return _catalog_result(entries, request.collection, request.corridor_geojson)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, f"NASA CMR search failed: {exc}") from exc


@app.post("/api/download")
def download(request: DownloadRequest):
    if PACKAGED_DEPLOYMENT:
        raise HTTPException(503, "Product downloads are disabled on the public ephemeral service. Use the local Windows workflow with your private Earthdata credentials and HDF5 storage.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", request.filename) or request.filename in (".", ".."):
        raise HTTPException(422, "Use a simple product filename without path components.")
    destination = ROOT / "data" / "raw" / request.filename
    try:
        cmr_record = request.cmr_record
        expected_md5 = None
        expected_size_bytes = None
        if request.expected_granule_id is not None:
            if not re.fullmatch(r"NISAR_L2_PR_GUNW_[A-Za-z0-9_]+", request.expected_granule_id):
                raise HTTPException(422, "Expected granule ID must be a NISAR L2 GUNW product ID.")
            if not cmr_record or not cmr_record.get("id"):
                raise HTTPException(422, "Selected-product downloads require a NASA CMR granule concept ID.")
            try:
                cmr_record = fetch_granule_by_concept_id(str(cmr_record["id"]))
            except Exception:
                raise HTTPException(502, "Could not verify the selected product against NASA CMR.") from None
            umm = cmr_record.get("umm", {})
            if umm.get("GranuleUR") != request.expected_granule_id:
                raise HTTPException(422, "The CMR record does not match the requested granule ID.")
            if request.filename != f"{request.expected_granule_id}.h5":
                raise HTTPException(422, "The selected product filename must match its CMR granule ID.")
            official_urls = [
                item.get("URL") for item in umm.get("RelatedUrls", [])
                if item.get("Type") == "GET DATA" and isinstance(item.get("URL"), str)
            ]
            if not any(_redact_url(url) == _redact_url(request.url) for url in official_urls):
                raise HTTPException(422, "The download URL is not the selected product's official CMR data URL.")
            data_granule = umm.get("DataGranule", {})
            distribution = data_granule.get("ArchiveAndDistributionInformation", [])
            hdf5_file = next((item for item in distribution
                              if item.get("Name") == f"{request.expected_granule_id}.h5"
                              and item.get("Format") == "HDF5"), None)
            if not hdf5_file:
                raise HTTPException(502, "NASA CMR has no HDF5 size/checksum metadata for the selected product.")
            try:
                expected_size_bytes = int(hdf5_file["SizeInBytes"])
            except (KeyError, TypeError, ValueError):
                raise HTTPException(502, "NASA CMR has no valid HDF5 file size for the selected product.") from None
            checksum = hdf5_file.get("Checksum", {})
            if checksum.get("Algorithm", "").upper() == "MD5":
                expected_md5 = checksum.get("Value")
            elif checksum.get("Algorithm", "").upper() == "SHA-256":
                request.expected_sha256 = checksum.get("Value")
            else:
                raise HTTPException(502, "NASA CMR has no supported HDF5 checksum for the selected product.")

        receipt = download_product(
            request.url,
            destination,
            request.expected_sha256,
            expected_md5=expected_md5,
            expected_size_bytes=expected_size_bytes,
            expected_granule_id=request.expected_granule_id,
        )
        if cmr_record is not None:
            sidecar = destination.with_name(destination.name + ".cmr.json")
            sidecar_temp = sidecar.with_name(sidecar.name + ".part")
            sidecar.parent.mkdir(parents=True, exist_ok=True)
            record = {"record_status": "Authoritative CMR UMM re-fetched and granule identity verified immediately before download",
                      "downloaded_utc": datetime.now(timezone.utc).isoformat(),
                      "download_filename": request.filename,
                      "download_url_without_query_or_fragment": _redact_url(request.url),
                      "download_receipt": receipt,
                      "cmr_record": _redact_cmr_links(cmr_record)}
            sidecar_temp.write_text(json.dumps(record, indent=2), encoding="utf-8")
            sidecar_temp.replace(sidecar)
            receipt["cmr_sidecar"] = sidecar.relative_to(ROOT).as_posix()
        return {"path": str(destination.relative_to(ROOT)), **receipt,
                "note": "Keep this receipt and the original CMR metadata with all derived products."}
    except HTTPException:
        raise
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception:
        raise HTTPException(502, "Download failed or was interrupted; any partial file is retained for a safe retry.") from None


def _redact_cmr_links(value):
    if isinstance(value, dict):
        return {key: (_redact_url(item) if key.lower() in {"href", "url"} else _redact_cmr_links(item))
                for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_cmr_links(item) for item in value]
    return value


def _redact_url(value):
    if not isinstance(value, str):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in {"https", "http"} or not parsed.netloc:
        return value
    host = parsed.hostname or ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunparse((parsed.scheme, host, parsed.path, "", "", ""))


@app.post("/api/inspect-gunw")
def inspect_local_gunw(request: InspectGunwRequest):
    if PACKAGED_DEPLOYMENT:
        raise HTTPException(503, "Full-product HDF5 inspection is local-only. The public service includes the verified compact evidence package.")
    if not re.fullmatch(r"[A-Za-z0-9._-]{1,180}", request.filename) or request.filename in (".", ".."):
        raise HTTPException(422, "Use a simple product filename without path components.")
    source = ROOT / "data" / "raw" / request.filename
    try:
        result = inspect_gunw(source, request.polarization)
        sidecar = source.with_name(source.name + ".cmr.json")
        if sidecar.is_file():
            try:
                result["cmr_download_record"] = json.loads(sidecar.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ValueError("Saved CMR sidecar is not valid JSON; preserve and inspect the original file before analysis.") from exc
            result["cmr_download_record_path"] = sidecar.relative_to(ROOT).as_posix()
        footprint_wkt = result.get("bounding_polygon_wkt")
        if request.corridor_geojson is not None and footprint_wkt:
            footprint = shapely_wkt.loads(footprint_wkt)
            corridor = corridor_geometry(request.corridor_geojson)
            if footprint.is_empty or not footprint.is_valid:
                raise ValueError("Product boundingPolygon WKT is empty or invalid.")
            if not (-180 <= footprint.bounds[0] <= 180 and -180 <= footprint.bounds[2] <= 180
                    and -90 <= footprint.bounds[1] <= 90 and -90 <= footprint.bounds[3] <= 90):
                raise ValueError("Product boundingPolygon is outside WGS84 longitude/latitude bounds.")
            result["footprint_intersection"] = "intersects" if footprint.intersects(corridor) else "no_intersection"
            result["product_footprint_geojson"] = mapping(footprint)
            result["footprint_check_method"] = "Exact Shapely vector intersection of the HDF5 identification boundingPolygon and imported corridor GeoJSON; pixel-level radar support remains a separate check."
        elif request.corridor_geojson is not None:
            result["footprint_intersection"] = "unavailable"
            result["footprint_check_reason"] = "HDF5 product identification has no boundingPolygon WKT."
        return result
    except (ValueError, OSError, TypeError) as exc:
        raise HTTPException(422, str(exc)) from exc


@app.post("/api/three-lane")
def three_lane(request: AnalysisRequest):
    product_gaps = validate_product_record(request.provenance, request.granule_id)
    if product_gaps:
        raise HTTPException(422, {"status": "insufficient_evidence", "reason": "Product identity, footprint, maturity, acquisition geometry, or phase interpretation has not passed the evidence gate.", "required": product_gaps})
    match_by_chainage={round(float(record.get("chainage_m",-1)),3):record for record in request.terrain_matches}
    expected={round(sample.chainage_m,3) for sample in request.samples}
    if not match_by_chainage or set(match_by_chainage)!=expected:
        raise HTTPException(422,{"status":"insufficient_evidence","reason":"Terrain/radar matching must be evaluated at every shared chainage section.","missing_chainages":sorted(expected-set(match_by_chainage))})
    matched_samples=[]
    for sample in request.samples:
        match=match_by_chainage[round(sample.chainage_m,3)]
        controls=match.get("controls",{})
        if not all(name in controls and isinstance(controls[name].get("matched"),bool) for name in ("control_a","control_b")):
            raise HTTPException(422,"Terrain match records must include boolean matched results for both controls at every chainage.")
        matched_samples.append(replace(sample,control_a_terrain_match=controls["control_a"]["matched"],
                                       control_b_terrain_match=controls["control_b"]["matched"],terrain_match_metrics=controls))
    result = evaluate_three_lane(matched_samples, min_valid_pixels=request.min_valid_pixels,
                                 max_control_disagreement_mm=request.max_control_disagreement_mm,
                                 candidate_threshold_mm=request.candidate_threshold_mm,
                                 min_sections=request.min_sections)
    context_map={round(float(record.get("chainage_m",-1)),3):record.get("context",[]) for record in request.context_by_chainage}
    for section in result["sections"]:
        section["context"]=context_map.get(round(section["chainage_m"],3),[])
    result["cases"] = build_cases(result, corridor_name=request.corridor_name,
                                  granule_id=request.granule_id, provenance=request.provenance)
    result["terrain_matches"] = request.terrain_matches
    result["provenance"] = request.provenance
    result["granule_id"] = request.granule_id
    result["corridor_name"] = request.corridor_name
    result["lane_geojson"] = request.lane_geojson
    return result


@app.post("/api/reference-robustness")
def reference_robustness(request: RobustnessRequest):
    try:
        pixel_resampling_supported = all(
            request.lane_pixels.get(lane)
            and all(all(key in row for key in ("x", "y", "center_x", "center_y", "product_mask_valid",
                                                "component_id", "reference_subswath", "secondary_subswath",
                                                "los_range_change_proxy_mm")) for row in request.lane_pixels[lane])
            for lane in ("asset", "control_a", "control_b"))
        if pixel_resampling_supported:
            if request.coherence_threshold is None or request.base_radius_m is None or not request.matching_thresholds:
                raise ValueError("Pixel-level robustness requires the coherence screen, sampled radius, and matching thresholds.")
            return evaluate_spatial_reference_robustness(
                request.lane_pixels, base_radius_m=request.base_radius_m,
                radius_floor_fraction=request.radius_floor_fraction,
                coherence_threshold=request.coherence_threshold,
                matching_thresholds=request.matching_thresholds,
                min_valid_pixels=request.min_valid_pixels,
                candidate_threshold_mm=request.candidate_threshold_mm,
                material_change_mm=request.material_change_mm,
                max_control_disagreement_mm=request.max_control_disagreement_mm,
                min_sections=request.min_sections)
        return evaluate_reference_robustness(
            request.samples, request.terrain_matches,
            min_valid_pixels=request.min_valid_pixels,
            candidate_threshold_mm=request.candidate_threshold_mm,
            material_change_mm=request.material_change_mm,
            max_control_disagreement_mm=request.max_control_disagreement_mm,
            min_sections=request.min_sections)
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"Robustness analysis input is incomplete or invalid: {exc}") from exc


@app.post("/api/terrain-match")
def terrain_match(payload: dict):
    try:
        pixels=payload["lane_pixels"]
        thresholds=payload["matching_thresholds"]
        coherence_threshold=float(payload["coherence_threshold"])
        groups={}
        for lane in ("asset","control_a","control_b"):
            for pixel in pixels[lane]:
                if "chainage_m" not in pixel: raise ValueError(f"{lane} pixel lacks chainage_m; section-wise matching is required.")
                groups.setdefault(float(pixel["chainage_m"]),{}).setdefault(lane,[]).append(pixel)
        sections=[]
        for chainage,lanes in sorted(groups.items()):
            if set(lanes)!={"asset","control_a","control_b"}: raise ValueError(f"All three lane samples are required at chainage {chainage}.")
            summaries={name:summarize_lane_covariates(lanes[name],coherence_threshold) for name in ("asset","control_a","control_b")}
            checks={name:compare_control_covariates(summaries["asset"],summaries[name],thresholds) for name in ("control_a","control_b")}
            sections.append({"chainage_m":chainage,"controls":checks,"lane_summaries":summaries})
        return {"sections":sections,"matching_thresholds":thresholds,
                "matched_sections":sum(all(v["matched"] for v in s["controls"].values()) for s in sections),
                "status":"matched" if sections and all(all(v["matched"] for v in s["controls"].values()) for s in sections) else "partial_or_unmatched"}
    except (KeyError,TypeError,ValueError) as exc:
        raise HTTPException(422,f"Terrain/radar pixel sample is incomplete or invalid: {exc}") from exc


@app.post("/api/export/{kind}")
def export_result(kind: str, request: ExportRequest):
    if kind == "json":
        payload = {"corridor_name": request.corridor_name, "granule_id": request.granule_id,
                   "provenance": request.provenance, "result": request.result}
        return Response(json.dumps(payload, indent=2), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=strainline-provenance.json"})
    if kind == "csv":
        stream = io.StringIO()
        fields = ["chainage_m", "status", "asset_los_mm", "control_a_los_mm", "control_b_los_mm", "common_motion_mm", "asset_relative_mm", "control_disagreement_mm", "reasons", "terrain_match_metrics"]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in request.result.get("sections", []):
            writer.writerow({**row, "reasons": "|".join(row.get("reasons", [])),"terrain_match_metrics":json.dumps(row.get("terrain_match_metrics"))})
        return Response(stream.getvalue(), media_type="text/csv", headers={"Content-Disposition": "attachment; filename=strainline-three-lane.csv"})
    if kind == "geojson":
        features = list((request.result.get("lane_geojson") or {}).get("features", []))
        for case in request.result.get("cases", []):
            coords = case.get("coordinates")
            geometry = {"type": "Point", "coordinates": coords} if coords and len(coords) == 2 else None
            features.append({"type": "Feature", "geometry": geometry, "properties": case})
        payload = {"type": "FeatureCollection", "name": "StrainLine lane support and proposed field cases", "features": features,
                   "note": "Lane polygons are nominal sampled-window unions, not valid-pixel footprints. Null case geometries require a verified chainage-to-location transform before field navigation."}
        return Response(json.dumps(payload, indent=2), media_type="application/geo+json",
                        headers={"Content-Disposition": "attachment; filename=strainline-field-cases.geojson"})
    if kind == "report":
        payload=render_field_report(request.corridor_name,request.granule_id,request.result,request.provenance)
        return Response(payload,media_type="application/pdf",headers={"Content-Disposition":"attachment; filename=strainline-field-cases.pdf"})
    raise HTTPException(404, "Supported exports: json, csv, geojson, report")


@app.post("/api/dual-band")
def dual_band(payload: dict):
    return compare_band_summaries(payload.get("l_band"), payload.get("s_band"), float(payload.get("tolerance_mm", 5)))


@app.post("/api/footprint-check")
def footprint_check(payload: dict):
    try:
        route = payload["corridor_geojson"]
        shapes = umm_footprint(payload.get("umm", {}))
        if not shapes:
            return {"status": "unavailable", "reason": "CMR UMM granule record contains no supported GPolygon footprint."}
        route_shape = corridor_geometry(route)
        matches = [poly.intersects(route_shape) for poly in shapes]
        return {"status": "intersects" if any(matches) else "no_intersection", "exact_vector_intersection": True,
                "polygon_count": len(shapes), "note": "Footprint intersection is a geometric coverage check, not proof of valid radar pixels or scientific suitability."}
    except Exception as exc:
        raise HTTPException(422, f"Could not compare corridor and product footprint: {exc}") from exc


@app.post("/api/temporal")
def temporal(payload: dict):
    return summarize_series(payload.get("observations", []), int(payload.get("min_pairs", 3)))


@app.post("/api/temporal-processed")
def temporal_processed(request: TemporalHistoryRequest):
    try:
        return summarize_processed_history(request.observations,
                                           min_observations=request.min_observations,
                                           candidate_threshold_mm=request.candidate_threshold_mm,
                                           material_change_mm=request.material_change_mm)
    except (TypeError, ValueError, KeyError) as exc:
        raise HTTPException(422, f"Processed temporal history input is invalid: {exc}") from exc


@app.post("/api/temporal-export/{kind}")
def export_temporal_history(kind: str, request: TemporalExportRequest):
    history = request.history
    if kind == "json":
        return Response(json.dumps(history, indent=2), media_type="application/json",
                        headers={"Content-Disposition": "attachment; filename=strainline-temporal-history.json"})
    if kind == "csv":
        stream = io.StringIO()
        columns = ("corridor_name", "chainage_m", "history_status", "valid_observations",
                   "granule_id", "date", "asset_los_mm", "background_los_mm",
                   "asset_relative_mm", "control_disagreement_mm", "missing_reason")
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for item in history.get("histories", []):
            for observation in item.get("observations", []):
                writer.writerow({"corridor_name": history.get("corridor_name"),
                                 "chainage_m": item.get("chainage_m"),
                                 "history_status": item.get("status"),
                                 "valid_observations": item.get("valid_observations"),
                                 **observation})
            for missing in item.get("missing_observations", []):
                writer.writerow({"corridor_name": history.get("corridor_name"),
                                 "chainage_m": item.get("chainage_m"),
                                 "history_status": item.get("status"),
                                 "valid_observations": item.get("valid_observations"),
                                 "granule_id": missing.get("granule_id"),
                                 "date": missing.get("date"),
                                 "missing_reason": missing.get("reason")})
        return Response(stream.getvalue(), media_type="text/csv",
                        headers={"Content-Disposition": "attachment; filename=strainline-temporal-history.csv"})
    raise HTTPException(404, "Supported temporal exports: csv, json")


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(FRONTEND / "index.html")
