"""NASA CMR NISAR GUNW catalog search. Metadata-only; never downloads data."""
from __future__ import annotations

import re

import httpx

CMR = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"
COLLECTIONS = {
    "provisional": "NISAR_L2_GUNW_PROVISIONAL_V1",
    "validated": "NISAR_L2_GUNW_V1",
}
DATA_LINK_REL = "http://esipfed.org/ns/fedsearch/1.1/data#"


def _normalise_item(item: dict, collection: str) -> dict:
    """Keep the complete UMM record and expose the fields the current UI needs."""
    umm = item.get("umm") or {}
    metadata = item.get("meta") or {}
    temporal = umm.get("TemporalExtent") or {}
    date_range = temporal.get("RangeDateTime") or {}
    if not date_range and temporal.get("SingleDateTime"):
        date_range = {
            "BeginningDateTime": temporal["SingleDateTime"],
            "EndingDateTime": temporal["SingleDateTime"],
        }

    links = []
    for related in umm.get("RelatedUrls") or []:
        url = related.get("URL")
        if related.get("Type") == "GET DATA" and isinstance(url, str) and url.startswith("https://"):
            links.append({"rel": DATA_LINK_REL, "href": url, "title": related.get("Description", "")})

    return {
        "id": metadata.get("concept-id", ""),
        "title": umm.get("GranuleUR", ""),
        "start": date_range.get("BeginningDateTime", ""),
        "end": date_range.get("EndingDateTime", ""),
        "links": links,
        "umm": umm,
        "collection_short_name": COLLECTIONS[collection],
        "collection_concept_id": metadata.get("collection-concept-id", ""),
    }


def fetch_granule_by_concept_id(concept_id: str) -> dict:
    """Fetch one authoritative UMM granule record from NASA CMR."""
    if not concept_id or not re.fullmatch(r"[A-Za-z0-9-]+", concept_id):
        raise ValueError("A valid NASA CMR granule concept ID is required.")
    response = httpx.get(
        CMR,
        params={"concept_id": concept_id},
        headers={"Accept": "application/json"},
        timeout=40,
    )
    response.raise_for_status()
    items = response.json().get("items", [])
    if len(items) != 1:
        raise ValueError("NASA CMR did not return exactly one granule for that concept ID.")
    item = items[0]
    short_name = (item.get("umm", {}).get("CollectionReference") or {}).get("ShortName")
    collection = next((key for key, name in COLLECTIONS.items() if name == short_name), None)
    if collection is None:
        raise ValueError("The CMR granule is not in a supported NISAR GUNW collection.")
    return _normalise_item(item, collection)


async def search_granules(
    bbox: str,
    start: str,
    end: str,
    collection: str = "provisional",
    limit: int = 100,
) -> list[dict]:
    """Search one maturity collection and return normalized UMM records."""
    if collection not in COLLECTIONS:
        raise ValueError("Collection must be 'provisional' or 'validated'.")
    params = {
        "short_name": COLLECTIONS[collection],
        "bounding_box": bbox,
        "temporal": f"{start}T00:00:00Z,{end}T23:59:59Z",
        "page_size": min(limit, 2000),
        "sort_key[]": "-start_date",
    }
    async with httpx.AsyncClient(timeout=40) as client:
        response = await client.get(CMR, params=params, headers={"Accept": "application/json"})
        response.raise_for_status()
        items = response.json().get("items", [])
    return [_normalise_item(item, collection) for item in items]
