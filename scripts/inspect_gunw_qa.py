"""Print read-only valid-pixel and railway support statistics for a GUNW."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from backend.gunw_qa import inspect_gunw_quality


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("product", type=Path, help="Path to the downloaded GUNW HDF5")
    parser.add_argument("route_geojson", type=Path, help="WGS84 railway GeoJSON")
    args = parser.parse_args()
    print(json.dumps(inspect_gunw_quality(args.product, args.route_geojson), indent=2))


if __name__ == "__main__":
    main()
