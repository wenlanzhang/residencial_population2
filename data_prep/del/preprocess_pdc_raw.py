#!/usr/bin/env python3
"""
Preprocess raw Meta PDC CSVs to standard format. Saves to CSV only.

For building the baseline GPKG directly from raw data, use build_fb_baseline_median.py
with -i pointing to the raw directory (it preprocesses in memory).

Usage:
  python Meta_base/preprocess_pdc_raw.py --region PHI
  python Meta_base/preprocess_pdc_raw.py -i /path/to/raw/PDC/folder -o outputs/PDC.csv
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
META_BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))
sys.path.insert(0, str(META_BASE))

# Reuse preprocess logic from build script
from build_fb_baseline_median import preprocess_raw_pdc


def main():
    import argparse
    p = argparse.ArgumentParser(description="Preprocess raw Meta PDC CSVs to standard format")
    p.add_argument("--region", type=str, default=None)
    p.add_argument("-i", "--input-dir", type=Path, default=None)
    p.add_argument("-o", "--output", type=Path, default=None)
    args = p.parse_args()

    if args.region:
        import region_config
        cfg = region_config.get_region_config(args.region)
        input_dir = args.input_dir or cfg.get("pdc_raw_dir")
        output_path = args.output or cfg.get("pdc_processed_csv")
        if not input_dir:
            raise ValueError(f"Region {args.region} has no pdc_raw_dir in config")
        if not output_path:
            output_path = PROJECT_ROOT / "outputs" / f"PDC_{args.region}.csv"
        print(f"Region: {args.region} ({cfg.get('name', args.region)})")
    else:
        input_dir = args.input_dir or Path(
            "/Users/wenlanzhang/Downloads/PhD_UCL/Data/Meta/Population During Crisis/OtherCountry/Tropical Storm Basyang Across Mindanao, Philippines"
        )
        output_path = args.output or (PROJECT_ROOT / "outputs" / "PDC_Philippines_Basyang.csv")

    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")

    df = preprocess_raw_pdc(input_dir)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_path, index=False)
    print(f"Saved: {output_path}")
    print(f"  Rows: {len(df)}, Quadkeys: {df['quadkey'].nunique()}")
    print(f"  Date range: {df['date_time'].min()} to {df['date_time'].max()}")


if __name__ == "__main__":
    main()
