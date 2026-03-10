#!/usr/bin/env python3
"""
Build fb_baseline_median_XXX.gpkg from Meta PDC (Population During Crisis) data.

Accepts either:
  - Raw PDC directory: preprocesses CSVs in memory, then builds baseline
  - Preprocessed CSV: builds baseline directly

Data source: Meta Data for Good
  - Population Maps: https://dataforgood.facebook.com/dfg/tools/facebook-population-maps
  - Movement Maps: https://dataforgood.facebook.com/dfg/tools/movement-maps

Methodology:
  1. Load PDC data (from raw dir or CSV)
  2. Baseline = 7-day shift or Meta's n_baseline
  3. Filter to event week (auto-detected) and reference hour (per-region via pdc_ref_hour in config)
  4. Median baseline per quadkey → GeoPackage

Usage:
  python data_prep/build_fb_baseline_median.py --region PHI
  python data_prep/build_fb_baseline_median.py -i /path/to/raw/PDC/folder -o outputs/fb_baseline_median_PHI.gpkg
  python data_prep/build_fb_baseline_median.py -i outputs/PDC_Philippines_Basyang.csv -o outputs/fb_baseline_median_PHI.gpkg

| City                   | Best residential proxy |
| ---------------------- | ---------------------- |
| Nairobi                | 08:00 PT               |
| Davao                  | 08:00 PT               |
| Mexico City            | 00:00 PT               |
| Cagayan de Oro (UTC+8) | 08:00 PT               |

"""

import argparse
import sys
from pathlib import Path

import pandas as pd
import geopandas as gpd
from shapely.geometry import box

try:
    import mercantile
except ImportError:
    raise ImportError("mercantile required: pip install mercantile")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))


def quadkey_to_geometry(quadkey: str):
    """Convert quadkey to polygon (WGS84 bbox)."""
    tile = mercantile.quadkey_to_tile(str(quadkey))
    bbox = mercantile.bounds(tile)
    return box(bbox.west, bbox.south, bbox.east, bbox.north)


def preprocess_raw_pdc(input_dir: Path) -> pd.DataFrame:
    """Load and preprocess raw PDC CSVs from a directory. Returns standardised DataFrame."""
    csv_files = sorted(input_dir.glob("*.csv"))
    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {input_dir}")
    print(f"Preprocessing {len(csv_files)} raw PDC files from {input_dir}...")
    dfs = []
    for f in csv_files:
        try:
            df = pd.read_csv(f, dtype={"quadkey": str})
        except Exception as e:
            print(f"  Warning: Could not read {f.name}: {e}")
            continue
        df.columns = df.columns.str.strip()
        required = ["quadkey", "date_time", "n_crisis"]
        if any(c not in df.columns for c in required):
            continue
        cols = ["quadkey", "date_time", "n_crisis"]
        if "n_baseline" in df.columns:
            cols.append("n_baseline")
        dfs.append(df[cols].copy())
    if not dfs:
        raise ValueError("No valid data loaded from any CSV file")
    combined = pd.concat(dfs, ignore_index=True)
    combined["quadkey"] = combined["quadkey"].astype(str)
    combined["date_time"] = pd.to_datetime(combined["date_time"])
    combined["n_crisis"] = pd.to_numeric(combined["n_crisis"], errors="coerce")
    combined = combined.dropna(subset=["n_crisis"])
    combined = combined.drop_duplicates(subset=["quadkey", "date_time"], keep="first")
    combined = combined.sort_values(["quadkey", "date_time"]).reset_index(drop=True)
    print(f"  Preprocessed: {len(combined)} rows, {combined['quadkey'].nunique()} quadkeys")
    return combined


def parse_args():
    p = argparse.ArgumentParser(
        description="Build fb_baseline_median_XXX.gpkg from Meta PDC data"
    )
    p.add_argument(
        "--region",
        type=str,
        default=None,
        help="Region code from config/regions.json (e.g. PHI_CagayandeOroCity, KEN_Nairobi, KEN_Mombasa, MEX). Sets input, output, dates.",
    )
    p.add_argument(
        "-i", "--input",
        type=Path,
        default=None,
        help="PDC CSV file or directory of raw PDC CSVs (preprocesses in memory if dir)",
    )
    p.add_argument(
        "--save-csv",
        type=Path,
        default=None,
        help="Save preprocessed CSV when using raw dir (optional)",
    )
    p.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Override: output GeoPackage path",
    )
    p.add_argument(
        "--ref-hour",
        type=int,
        default=None,
        metavar="HOUR",
        help="Reference hour (0, 8, or 16). Overrides pdc_ref_hour from region config when set.",
    )
    p.add_argument(
        "--start",
        type=str,
        default=None,
        help="Event week start date (YYYY-MM-DD). Auto-detected from data if not set.",
    )
    p.add_argument(
        "--end",
        type=str,
        default=None,
        help="Event week end date (YYYY-MM-DD). Auto-detected from data if not set.",
    )
    p.add_argument(
        "--baseline-shift-days",
        type=int,
        default=7,
        help="Days to shift backward for baseline (default: 7). Ignored if --use-baseline-column.",
    )
    p.add_argument(
        "--use-baseline-column",
        action="store_true",
        help="Use n_baseline from CSV directly (Meta pre-computed). Use when data doesn't span 7+ days for shift.",
    )
    return p.parse_args()


def main():
    args = parse_args()

    # Resolve paths from --region config or args
    if args.region:
        import region_config
        cfg = region_config.get_region_config(args.region)
        input_path = args.input or cfg.get("pdc_raw_dir") or cfg.get("pdc_processed_csv")
        output_path = args.output or cfg.get("meta")
        config_use_baseline = cfg.get("pdc_use_baseline_column")  # None = auto
        ref_hour = args.ref_hour if args.ref_hour is not None else cfg.get("pdc_ref_hour", 0)
        if not input_path:
            raise ValueError(f"Region {args.region} needs pdc_raw_dir or pdc_processed_csv in config")
        if not output_path:
            output_path = PROJECT_ROOT / "outputs" / f"fb_baseline_median_{args.region}.gpkg"
        if args.use_baseline_column:
            config_use_baseline = True
        print(f"Region: {args.region} ({cfg.get('name', args.region)})")
    else:
        input_path = args.input or Path(
            "/Users/wenlanzhang/Downloads/PhD_UCL/Data/Meta/Population During Crisis/Processed/PDC_aoi_24_0424_0514.csv"
        )
        output_path = args.output or (PROJECT_ROOT / "outputs" / "fb_baseline_median.gpkg")
        config_use_baseline = args.use_baseline_column
        ref_hour = args.ref_hour if args.ref_hour is not None else 0

    if ref_hour not in (0, 8, 16):
        raise ValueError(f"ref_hour must be 0, 8, or 16 (got {ref_hour})")

    input_path = Path(input_path)
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    # 1. Load PDC data (from raw dir or CSV)
    if input_path.is_dir():
        df = preprocess_raw_pdc(input_path)
        if args.save_csv:
            args.save_csv.parent.mkdir(parents=True, exist_ok=True)
            df.to_csv(args.save_csv, index=False)
            print(f"  Saved preprocessed CSV: {args.save_csv}")
    else:
        print(f"Reading PDC data from {input_path}...")
        df = pd.read_csv(input_path, dtype={"quadkey": str})
        df.columns = df.columns.str.strip()
        if "n_baseline" in df.columns:
            df["n_baseline"] = pd.to_numeric(df["n_baseline"], errors="coerce")
    if "n_crisis" not in df.columns:
        # Try alternative column names
        count_col = next((c for c in df.columns if "crisis" in c.lower() or "count" in c.lower() or "n_" in c), None)
        if count_col:
            df = df.rename(columns={count_col: "n_crisis"})
        else:
            raise ValueError(f"Expected 'n_crisis' column. Columns: {list(df.columns)}")

    df["date_time"] = pd.to_datetime(df["date_time"])
    df["quadkey"] = df["quadkey"].astype(str)
    has_n_baseline = "n_baseline" in df.columns
    date_span_days = (df["date_time"].max() - df["date_time"].min()).days

    # Auto-decide baseline method: config override, else data-driven
    # If data spans >= 14 days: use 7-day shift (enough history). Else: use n_baseline column.
    if config_use_baseline is True:
        use_baseline = True
        if not has_n_baseline:
            raise ValueError("pdc_use_baseline_column=true but n_baseline column not in CSV")
    elif config_use_baseline is False:
        use_baseline = False
    else:
        # Auto: >= 14 days -> shift; < 14 days -> n_baseline (if available)
        if date_span_days >= 14:
            use_baseline = False
            print(f"  Auto: data spans {date_span_days} days (>= 14) -> using 7-day shift")
        else:
            use_baseline = has_n_baseline
            if use_baseline:
                print(f"  Auto: data spans {date_span_days} days (< 14) -> using n_baseline from CSV")
            else:
                print(f"  Auto: data spans {date_span_days} days (< 14) but n_baseline not in CSV -> using 7-day shift (may have NaN)")
                use_baseline = False

    cols = ["quadkey", "date_time", "n_crisis"]
    if use_baseline:
        cols.append("n_baseline")
    df = df[cols].copy()
    print(f"  Loaded {len(df)} rows, {df['quadkey'].nunique()} unique quadkeys")

    # Auto-detect date range from data if not specified
    start_date = args.start
    end_date = args.end
    if start_date is None or end_date is None:
        dt_min = df["date_time"].min()
        dt_max = df["date_time"].max()
        start_date = start_date or dt_min.strftime("%Y-%m-%d")
        end_date = end_date or dt_max.strftime("%Y-%m-%d")
        print(f"  Auto-detected date range: {start_date} to {end_date}")

    # 2. Create baseline
    if use_baseline:
        print("Using n_baseline from CSV (Meta pre-computed)...")
        df_merged = df.dropna(subset=["n_baseline"]).copy()
    else:
        print(f"Creating baseline (shift {args.baseline_shift_days} days backward)...")
        df_shifted = df[["quadkey", "date_time", "n_crisis"]].copy()
        df_shifted = df_shifted.rename(columns={"n_crisis": "n_baseline"})
        # Row (Q, D-7) is the baseline for event date D. Add date_event = D so we can merge.
        df_shifted["date_event"] = df_shifted["date_time"] + pd.Timedelta(days=args.baseline_shift_days)
        df_merged = df.merge(
            df_shifted[["quadkey", "date_event", "n_baseline"]],
            left_on=["quadkey", "date_time"],
            right_on=["quadkey", "date_event"],
            how="left",
        )
        df_merged = df_merged.drop(columns=["date_event"], errors="ignore")
        df_merged = df_merged.dropna(subset=["n_crisis", "n_baseline"], how="all")

    # 3. Filter to event week
    start = pd.to_datetime(start_date)
    end = pd.to_datetime(end_date) + pd.Timedelta(days=1)  # inclusive of end date
    mask = (df_merged["date_time"] >= start) & (df_merged["date_time"] < end)
    df_filtered = df_merged.loc[mask].copy()
    print(f"  Event week {start_date} to {end_date}: {len(df_filtered)} rows")

    # 4. Filter to reference hour (midnight by default)
    df_filtered["hour"] = df_filtered["date_time"].dt.hour
    df_ref = df_filtered[df_filtered["hour"] == ref_hour].copy()
    print(f"  Reference hour {ref_hour}: {len(df_ref)} rows")

    # 5. Median baseline per quadkey
    fb_baseline = (
        df_ref.groupby("quadkey")["n_baseline"]
        .median()
        .reset_index()
        .rename(columns={"n_baseline": "fb_baseline_median"})
    )
    print(f"  Computed median baseline for {len(fb_baseline)} quadkeys")

    # 6. Add geometry
    fb_baseline["geometry"] = fb_baseline["quadkey"].apply(quadkey_to_geometry)
    gdf = gpd.GeoDataFrame(
        fb_baseline,
        geometry="geometry",
        crs="EPSG:4326",
    )

    # 7. Save (01_harmonise renames first numeric column to meta_baseline)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_file(output_path, layer="fb_baseline_median", driver="GPKG")
    print(f"Saved: {output_path}")
    print(f"  Columns: {list(gdf.columns)}")
    col = "fb_baseline_median"
    print(f"  {col}: min={gdf[col].min():.1f}, max={gdf[col].max():.1f}, sum={gdf[col].sum():.0f}")


if __name__ == "__main__":
    main()
