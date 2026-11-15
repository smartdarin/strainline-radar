"""Evidence gate for product identity, maturity, geometry and phase interpretation."""

REQUIRED_PRODUCT_FIELDS = (
    "cmr_granule_id", "cmr_metadata_url", "collection_short_name", "processing_maturity",
    "acquisition_start", "acquisition_end", "orbit_geometry_id", "look_direction",
    "polarization", "hdf5_granule_id", "cmr_identity_matches_hdf5", "cmr_record_reviewed",
    "footprint_intersection", "phase_convention_reviewed",
    "reference_secondary_order",
)


def validate_product_record(record: dict, requested_granule_id: str) -> list[str]:
    missing = [key for key in REQUIRED_PRODUCT_FIELDS if record.get(key) in (None, "")]
    if record.get("footprint_intersection") is not True:
        missing.append("confirmed centerline/footprint intersection")
    if record.get("phase_convention_reviewed") is not True:
        missing.append("reviewed phase convention")
    if record.get("cmr_record_reviewed") is not True:
        missing.append("reviewed NASA CMR record")
    if record.get("hdf5_granule_id") != requested_granule_id:
        missing.append("HDF5 granule ID matches the selected product")
    if record.get("cmr_identity_matches_hdf5") is not True:
        missing.append("CMR GranuleUR matches HDF5 granule ID")
    if record.get("cmr_granule_id") and record["cmr_granule_id"] != requested_granule_id:
        missing.append("granule ID matches the supplied CMR metadata record")
    collection = str(record.get("collection_short_name", ""))
    if "GUNW" not in collection.upper():
        missing.append("confirmed GUNW collection")
    maturity = str(record.get("processing_maturity", "")).upper()
    if maturity not in ("PROVISIONAL", "VALIDATED"):
        missing.append("recognized product maturity (PROVISIONAL or VALIDATED)")
    return sorted(set(missing))
