#!/usr/bin/env python3
"""
Check quadkey extent for PDC data. Helps diagnose wrong-location issues.

Usage:
  python Meta_base/check_quadkeys.py --region MEX
  python Meta_base/check_quadkeys.py -i outputs/PDC_Mexico.csv
  python Meta_base/check_quadkeys.py -i /path/to/raw/PDC/folder
"""

import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))

try:
    import mercantile
except ImportError:
    print("Install mercantile: pip install mercantile")
    sys.exit(1)


def quadkey_to_lonlat(qk: str):
    """Return (lon_center, lat_center) for quadkey."""
    tile = mercantile.quadkey_to_tile(str(qk))
    bbox = mercantile.bounds(tile)
    lon = (bbox.west + bbox.east) / 2
    lat = (bbox.south + bbox.north) / 2
    return lon, lat


def main():
    import argparse
    p = argparse.ArgumentParser(description="Check quadkey extent in PDC data")
    p.add_argument("--region", type=str, help="Region code (PHI, KEN, MEX)")
    p.add_argument("-i", "--input", type=Path, help="PDC CSV file or raw folder")
    args = p.parse_args()

    if args.region:
        import region_config
        cfg = region_config.get_region_config(args.region)
        inp = args.input or Path(cfg.get("pdc_processed_csv") or cfg.get("pdc_raw_dir"))
        expected_lon = cfg.get("lon_range")
        expected_lat = cfg.get("lat_range")
        region_name = cfg.get("name", args.region)
    else:
        inp = args.input
        expected_lon = expected_lat = None
        region_name = "data"

    if not inp or not Path(inp).exists():
        print(f"Input not found: {inp}")
        sys.exit(1)

    inp = Path(inp)
    if inp.is_dir():
        from build_fb_baseline_median import preprocess_raw_pdc
        df = preprocess_raw_pdc(inp)
        print(f"Loaded from raw dir: {len(df)} rows, {df['quadkey'].nunique()} quadkeys")
    else:
        df = pd.read_csv(inp, dtype={"quadkey": str})
        df["quadkey"] = df["quadkey"].astype(str)
        print(f"Loaded from CSV: {len(df)} rows, {df['quadkey'].nunique()} quadkeys")

    # Sample quadkeys and decode
    quadkeys = df["quadkey"].unique()[:20]
    lons, lats = [], []
    for qk in quadkeys:
        try:
            lon, lat = quadkey_to_lonlat(qk)
            lons.append(lon)
            lats.append(lat)
        except Exception as e:
            print(f"  Quadkey {qk}: decode error {e}")

    if not lons:
        print("No valid quadkeys decoded.")
        sys.exit(1)

    lon_min, lon_max = min(lons), max(lons)
    lat_min, lat_max = min(lats), max(lats)
    print(f"\nQuadkey extent (from sample):")
    print(f"  Longitude: [{lon_min:.2f}, {lon_max:.2f}]")
    print(f"  Latitude:  [{lat_min:.2f}, {lat_max:.2f}]")

    if expected_lon and expected_lat:
        overlaps = not (lon_max < expected_lon[0] or lon_min > expected_lon[1] or
                        lat_max < expected_lat[0] or lat_min > expected_lat[1])
        print(f"\nExpected for {region_name}: lon {expected_lon}, lat {expected_lat}")
        if overlaps:
            print("  -> OK: quadkeys overlap expected region")
        else:
            print("  -> MISMATCH: quadkeys are NOT in expected region!")
            print("     The PDC data may be from a different event. Check pdc_raw_dir.")


if __name__ == "__main__":
    main()
