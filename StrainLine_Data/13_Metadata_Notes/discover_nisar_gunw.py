#!/usr/bin/env python3
"""Discover NISAR L-band GUNW granules intersecting the Kalka-Shimla railway.

Uses ASF Search (metadata only). It never downloads product files.
Route source: OSM relation 331109; route retrieval is explicit with --fetch-osm-route.
Earthdata auth: existing .netrc/_netrc, or secure username/password prompts.
"""
from __future__ import annotations
import argparse, csv, getpass, json, math, netrc, re, sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import URLError

BASE = Path(__file__).resolve().parents[1]
ROUTE = BASE / "00_AOI" / "route" / "kalka_shimla_railway_osm_relation_331109.geojson"
OUT = BASE / "13_Metadata_Notes"
CSV_PATH = OUT / "nisar_gunw_search_results.csv"
REPORT_PATH = OUT / "nisar_gunw_product_metadata_report.md"
OSM_URL = "https://api.openstreetmap.org/api/0.6/relation/331109/full.json"

FIELDS = ["product_id", "collection", "maturity_search", "maturity_metadata", "exact_centerline_intersection",
 "start_datetime", "stop_datetime", "reference_datetime", "secondary_datetime", "pair_dates_source",
 "polarization", "frequency_band", "orbit_direction", "relative_orbit", "absolute_orbit", "frame",
 "temporal_baseline_days", "file_size_bytes", "file_size_gib", "download_url", "metadata_url",
 "pair_compatibility_group", "pair_candidate", "compatibility_note"]

def fetch_osm_route(path: Path):
    req = Request(OSM_URL, headers={"User-Agent": "StrainLine-data-discovery/1.0 (route provenance; OSM attribution)"})
    with urlopen(req, timeout=40) as response:
        payload = json.load(response)
    from shapely.geometry import LineString, mapping
    ways = [e for e in payload.get("elements", []) if e.get("type") == "way" and e.get("tags", {}).get("railway") in {"rail", "narrow_gauge"}]
    lines = []
    way_ids = []
    for w in ways:
        coords = [(p["lon"], p["lat"]) for p in w.get("geometry", []) if "lon" in p and "lat" in p]
        if len(coords) >= 2:
            lines.append(LineString(coords)); way_ids.append(w["id"])
    if not lines:
        raise RuntimeError("OSM relation response had no railway-tagged way geometry.")
    # Keep track segments as a MultiLineString; this preserves sourced geometry without
    # inventing connectivity or silently filling small gaps.
    from shapely.geometry import MultiLineString
    geom = MultiLineString([list(line.coords) for line in lines])
    feature = {"type":"Feature", "properties":{"name":"Kalka–Shimla Railway", "source":"OpenStreetMap relation 331109", "source_url":OSM_URL, "relation_id":331109, "railway_way_ids":way_ids, "retrieved_utc":datetime.now(timezone.utc).isoformat(), "license":"OpenStreetMap contributors; ODbL 1.0", "geometry_note":"Railway-tagged relation member ways; segmented geometry retained as mapped."}, "geometry":mapping(geom)}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"type":"FeatureCollection","features":[feature]}, indent=2), encoding="utf-8")
    return geom, feature["properties"]

def load_route(path: Path):
    from shapely.geometry import shape
    fc=json.loads(path.read_text(encoding="utf-8"))
    from shapely.ops import unary_union
    geom=unary_union([shape(f["geometry"]) for f in fc.get("features",[])])
    props=fc.get("features", [{}])[0].get("properties", {})
    if geom.is_empty or geom.geom_type not in {"LineString","MultiLineString"}:
        raise ValueError("Route GeoJSON must contain LineString/MultiLineString geometry.")
    return geom, props

def auth_session(mode):
    import asf_search as asf
    session=asf.ASFSession()
    if mode == "netrc":
        creds=None
        for machine in ("urs.earthdata.nasa.gov", "earthdata.nasa.gov"):
            try:
                a=netrc.netrc().authenticators(machine)
                if a and a[0] and a[2]: creds=(a[0],a[2]); break
            except (FileNotFoundError, netrc.NetrcParseError):
                pass
        if creds:
            session.auth_with_creds(*creds)
            return session
        print("No Earthdata credentials found in .netrc/_netrc; enter credentials securely.", file=sys.stderr)
    username=input("NASA Earthdata username: ").strip()
    password=getpass.getpass("NASA Earthdata password (not echoed or saved): ")
    session.auth_with_creds(username, password)
    del password
    return session

def prop(p, *keys):
    for key in keys:
        v=p.get(key)
        if v not in (None, "", []): return v
    return ""

def deep_find(obj, keys):
    if isinstance(obj, dict):
        for k,v in obj.items():
            if k.lower() in keys and v not in (None, "", []):
                if isinstance(v, dict):
                    for x in ("Value", "value", "BeginningDateTime", "EndingDateTime"):
                        if x in v: return v[x]
                return v
        for v in obj.values():
            found=deep_find(v,keys)
            if found not in (None, "", []): return found
    elif isinstance(obj,list):
        for v in obj:
            found=deep_find(v,keys)
            if found not in (None, "", []): return found
    return ""

def record_row(result, maturity, centerline):
    p=getattr(result,"properties",{}) or {}
    umm=getattr(result,"umm",{}) or {}
    geom=getattr(result,"geometry",None)
    intersects=False
    try:
        from shapely.geometry import shape
        intersects=centerline.intersects(shape(geom)) if geom else False
    except Exception: pass
    pid=str(prop(p,"sceneName","fileID","granuleName","granule_ur","productName"))
    if not pid: pid=str(getattr(result,"__dict__",{}).get("sceneName", ""))
    start=prop(p,"startTime","startDate","beginningDateTime") or deep_find(umm,{"beginningdatetime","starttime"})
    stop=prop(p,"stopTime","endTime","endingDateTime") or deep_find(umm,{"endingdatetime","stoptime"})
    ref=deep_find(umm,{"referencestartdatetime","referenceacquisitiondatetime","reference_datetime"})
    sec=deep_find(umm,{"secondarystartdatetime","secondaryacquisitiondatetime","secondary_datetime"})
    pol=prop(p,"polarization","polarizations","polarizationChannels") or deep_find(umm,{"polarization","polarizations"})
    direction=prop(p,"flightDirection","orbitDirection","flight_direction") or deep_find(umm,{"flightdirection","orbitdirection"})
    size=prop(p,"bytes","fileSize","size") or deep_find(umm,{"filesize","sizeinbytes"})
    try: size=int(size)
    except (ValueError,TypeError): size=""
    url=prop(p,"url","downloadUrl","downloadURL")
    metadata=prop(p,"browse","metadataURL","metaUrl") or prop(p,"url")
    rel=prop(p,"relativeOrbit","relativeOrbitNumber") or deep_find(umm,{"relativeorbit","relativeorbitnumber"})
    absolute=prop(p,"absoluteOrbit","absoluteOrbitNumber") or deep_find(umm,{"absoluteorbit","absoluteorbitnumber"})
    frame=prop(p,"frame","asfFrame","frameNumber") or deep_find(umm,{"frame","framenumber"})
    baseline=prop(p,"temporalBaselineDays","temporalBaseline") or deep_find(umm,{"temporalbaselinedays","temporalbaseline"})
    band=prop(p,"frequencyBand","band") or "L (requested collection)"
    return {"product_id":pid,"collection":prop(p,"collectionName","shortName","collection") or deep_find(umm,{"shortname"}),
      "maturity_search":maturity,"maturity_metadata":prop(p,"dataMaturity","maturity") or deep_find(umm,{"datamaturity","maturity"}),
      "exact_centerline_intersection":str(bool(intersects)).lower(),"start_datetime":start,"stop_datetime":stop,
      "reference_datetime":ref,"secondary_datetime":sec,"pair_dates_source":"ASF metadata" if ref or sec else "not exposed by search metadata; inspect HDF5",
      "polarization":json.dumps(pol) if isinstance(pol,(dict,list)) else pol,"frequency_band":band,"orbit_direction":direction,
      "relative_orbit":rel,"absolute_orbit":absolute,"frame":frame,"temporal_baseline_days":baseline,
      "file_size_bytes":size,"file_size_gib":round(size/(1024**3),3) if size else "","download_url":url,"metadata_url":metadata,
      "pair_compatibility_group":"","pair_candidate":"no","compatibility_note":"Requires exact overlap and matching orbit/frame/polarization with a distinct compatible acquisition pair; HDF5 review still required."}

def write_report(text): REPORT_PATH.parent.mkdir(parents=True,exist_ok=True); REPORT_PATH.write_text(text,encoding="utf-8")
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--route",type=Path,default=ROUTE)
    ap.add_argument("--fetch-osm-route",action="store_true",help="Fetch relation 331109 and save its attributed GeoJSON")
    ap.add_argument("--auth",choices=["netrc","prompt"],default="netrc")
    ap.add_argument("--max-results",type=int,default=250)
    args=ap.parse_args(); OUT.mkdir(parents=True,exist_ok=True)
    now=datetime.now(timezone.utc).isoformat()
    try:
        if args.fetch_osm_route: center,route_props=fetch_osm_route(args.route)
        else: center,route_props=load_route(args.route)
    except Exception as e:
        CSV_PATH.write_text(",".join(FIELDS)+"\n",encoding="utf-8")
        write_report(f"# NISAR GUNW discovery report\n\n- Run UTC: {now}\n- Status: **NOT SEARCHED**\n- Route: `{args.route}`\n- Reason: {type(e).__name__}: {e}\n\nNo products were queried or verified. No results have been fabricated. Check network access, then run with `--fetch-osm-route` or provide a WGS84 railway GeoJSON using `--route`. No HDF5 files were downloaded.\n")
        print(f"Route unavailable; wrote empty report artifacts. Details: {e}",file=sys.stderr); return 2
    try:
        import asf_search as asf
        from shapely.geometry import mapping
        from shapely.ops import transform
        from pyproj import Transformer
        # Search polygon is a 1 km corridor envelope; final acceptance checks the unsimplified route.
        lon,lat=center.representative_point().x,center.representative_point().y
        zone=int((lon+180)//6)+1; epsg=(32600+zone) if lat>=0 else (32700+zone)
        fwd=Transformer.from_crs("EPSG:4326",f"EPSG:{epsg}",always_xy=True).transform
        back=Transformer.from_crs(f"EPSG:{epsg}","EPSG:4326",always_xy=True).transform
        envelope=transform(back,transform(fwd,center).buffer(1000))
        wkt=envelope.wkt
        session=auth_session(args.auth)
        rows=[]; errors=[]
        for maturity, short in (("VALIDATED","NISAR_L2_GUNW_V1"),("PROVISIONAL","NISAR_L2_GUNW_PROVISIONAL_V1")):
            try:
                options=asf.ASFSearchOptions(dataset=["NISAR"],shortName=[short],dataMaturity=[maturity],intersectsWith=wkt,maxResults=args.max_results,session=session)
                results=asf.search(opts=options)
                for result in results: rows.append(record_row(result,maturity,center))
            except Exception as e: errors.append(f"{maturity}: {type(e).__name__}: {e}")
        # Candidate groups require same orbit direction, relative orbit, frame and pol.
        groups={}
        for r in rows:
            if r["exact_centerline_intersection"]!="true": continue
            k=tuple(str(r[x]) for x in ("orbit_direction","relative_orbit","frame","polarization"))
            if all(k): groups.setdefault(k,[]).append(r)
        for k,items in groups.items():
            starts=sorted(set(str(i["start_datetime"]) for i in items if i["start_datetime"]))
            if len(items)>=2 and len(starts)>=2:
                for i in items:
                    i["pair_compatibility_group"]="|".join(k)
                    i["pair_candidate"]="catalog-compatible; review HDF5" if i["reference_datetime"] or i["secondary_datetime"] else "possible; pair dates unavailable"
                    i["compatibility_note"]="Same catalog orbit/frame/polarization group with multiple acquisition times; confirm reference/secondary ordering, temporal baseline, burst overlap, QA and phase support in HDF5."
        with CSV_PATH.open("w",newline="",encoding="utf-8-sig") as f:
            writer=csv.DictWriter(f,fieldnames=FIELDS); writer.writeheader(); writer.writerows(rows)
        nvalid=sum(r["maturity_search"]=="VALIDATED" and r["exact_centerline_intersection"]=="true" for r in rows)
        nprov=sum(r["maturity_search"]=="PROVISIONAL" and r["exact_centerline_intersection"]=="true" for r in rows)
        route_m=transform(fwd,center).length
        report=f"""# NISAR L-band GUNW discovery report

- Run UTC: {now}
- Method: official `asf_search` package, authenticated Earthdata ASF search; validated and provisional searched as separate collection/maturity queries.
- Route source: {route_props.get('source','user-supplied GeoJSON')}; {route_props.get('source_url','')}
- Route geometry length: {route_m/1000:.2f} km (sum of mapped line segments; not a surveyed alignment).
- Spatial method: 1 km projected buffer used only for catalog discovery; each result was then tested against the original route centerline geometry.
- Search records returned: {len(rows)}; exact centerline intersections: validated {nvalid}, provisional {nprov}.
- Products downloaded: **0**.

## Results

See [`nisar_gunw_search_results.csv`](nisar_gunw_search_results.csv). A catalog-compatible pair is only a candidate. Confirm reference/secondary acquisition dates, exact common support, burst/subswath coverage, polarization, orbit direction, processing maturity, QA masks, and phase conventions from product metadata and HDF5 before analysis.

## Search errors

{chr(10).join('- '+e for e in errors) if errors else '- None reported.'}

## Interpretation

A row is considered a spatial match only when the ASF result geometry intersects the route centerline. Product availability or a catalog intersection does not establish usable phase pixels or a validated deformation measurement. File sizes and acquisition-pair fields are reported only when exposed by ASF search metadata; blank fields are not inferred. No HDF5 files are downloaded by this script.
"""
        write_report(report)
        print(f"Wrote {len(rows)} records; exact intersections: validated={nvalid}, provisional={nprov}")
        if errors: print("Search errors: " + " | ".join(errors),file=sys.stderr)
        return 0
    except Exception as e:
        CSV_PATH.write_text(",".join(FIELDS)+"\n",encoding="utf-8")
        write_report(f"# NISAR GUNW discovery report\n\n- Run UTC: {now}\n- Route loaded: `{args.route}`\n- Status: **SEARCH FAILED**\n- Error: {type(e).__name__}: {e}\n\nNo archive results are reported. No HDF5 files were downloaded.\n")
        print(f"Search failed: {type(e).__name__}: {e}",file=sys.stderr); return 3
if __name__=="__main__": raise SystemExit(main())
