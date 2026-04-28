#!/usr/bin/env python3
"""
Prepare student-ready "real-data anchor" tables from pipeline outputs.

Reads, for each region:
  outputs/{REGION}/02/harmonised_with_residual.gpkg  (layer: harmonised_with_residual)

Outputs, for each region:
  (default) outputs/{REGION}/student_data/anchor_table.csv
  (optional) {output_root}/{REGION}/anchor_table.csv

Each output row = one grid cell (quadkey polygon).

Required columns (student-facing):
  - cell_id: unique ID (quadkey)
  - x_meta: Meta baseline population count (per cell)
  - x_wp: WorldPop population count (per cell)
  - wealth: Relative Wealth Index (RWI) with higher = wealthier
  - x_coord, y_coord: centroid coordinates in a projected CRS (meters)
  - area: cell area (m^2)

Helpful extras:
  - distance_to_center: distance from study centroid (meters)
  - log_density: log((x_wp + eps) / (area + eps))  (eps prevents -inf)
  - shares: p_meta, p_wp (students should use shares for comparison experiments)
  - residual (optional helper): log((p_meta + eps) / (p_wp + eps))

Notes:
  - The pipeline stores poverty as poverty_mean = -RWI (so higher = poorer).
    We convert back to wealth as wealth = -poverty_mean.
  - Filtering follows the "valid cell" rule: x_meta > 0 AND x_wp > 0 AND wealth not missing.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path

import numpy as np
import pandas as pd

try:
    import geopandas as gpd
except ModuleNotFoundError as e:
    raise ModuleNotFoundError(
        "Missing dependency 'geopandas'. Install the project requirements (pip install -r requirements.txt) "
        "or run inside your configured conda env before running this script."
    ) from e


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _utm_epsg_from_lonlat(lon: float, lat: float) -> int:
    """
    Pick a UTM CRS EPSG code from lon/lat.
    Northern hemisphere: EPSG:326xx, Southern: EPSG:327xx
    """
    zone = int(math.floor((lon + 180.0) / 6.0) + 1)
    zone = max(1, min(zone, 60))
    return (32600 + zone) if lat >= 0 else (32700 + zone)


def _pick_projected_crs(gdf_wgs84: "gpd.GeoDataFrame", override: str | None) -> str:
    if override:
        return override
    b = gdf_wgs84.total_bounds  # xmin, ymin, xmax, ymax in lon/lat
    clon = float((b[0] + b[2]) / 2)
    clat = float((b[1] + b[3]) / 2)
    return f"EPSG:{_utm_epsg_from_lonlat(clon, clat)}"


def prepare_region(input_gpkg: Path, projected_crs: str | None = None) -> tuple[pd.DataFrame, str]:
    gdf = gpd.read_file(input_gpkg)
    if "quadkey" not in gdf.columns:
        raise ValueError(f"Expected 'quadkey' column in {input_gpkg}")
    for col in ("meta_baseline", "worldpop_count", "poverty_mean"):
        if col not in gdf.columns:
            raise ValueError(f"Expected '{col}' column in {input_gpkg}")

    # wealth: convert back from pipeline's poverty_mean = -RWI
    wealth = -pd.to_numeric(gdf["poverty_mean"], errors="coerce")

    valid = (
        pd.to_numeric(gdf["meta_baseline"], errors="coerce").fillna(0) > 0
    ) & (
        pd.to_numeric(gdf["worldpop_count"], errors="coerce").fillna(0) > 0
    ) & (wealth.notna())
    gdf = gdf.loc[valid].copy()
    gdf["wealth"] = wealth.loc[valid].astype(float)

    # Ensure WGS84 before selecting UTM
    if gdf.crs is None:
        raise ValueError(f"{input_gpkg} has no CRS; cannot compute projected coordinates.")
    gdf_wgs84 = gdf.to_crs("EPSG:4326")
    proj_crs = _pick_projected_crs(gdf_wgs84, projected_crs)
    gdf_proj = gdf_wgs84.to_crs(proj_crs)

    cent = gdf_proj.geometry.centroid
    x = cent.x.to_numpy()
    y = cent.y.to_numpy()

    area_m2 = gdf_proj.geometry.area.to_numpy()
    area_m2 = np.maximum(area_m2, 1e-9)

    x_center = float(np.mean(x)) if len(x) else float("nan")
    y_center = float(np.mean(y)) if len(y) else float("nan")
    dist = np.sqrt((x - x_center) ** 2 + (y - y_center) ** 2)

    eps = 1e-10
    x_wp = pd.to_numeric(gdf_wgs84["worldpop_count"], errors="coerce").astype(float).to_numpy()
    x_meta = pd.to_numeric(gdf_wgs84["meta_baseline"], errors="coerce").astype(float).to_numpy()

    log_density = np.log((x_wp + eps) / (area_m2 + eps))

    meta_sum = float(np.nansum(np.where(np.isfinite(x_meta) & (x_meta > 0), x_meta, 0.0)))
    wp_sum = float(np.nansum(np.where(np.isfinite(x_wp) & (x_wp > 0), x_wp, 0.0)))
    p_meta = (x_meta + eps) / (meta_sum + eps)
    p_wp = (x_wp + eps) / (wp_sum + eps)
    residual = np.log((p_meta + eps) / (p_wp + eps))

    wealth_rank = pd.Series(gdf_wgs84["wealth"].astype(float)).rank(pct=True).to_numpy()

    out = pd.DataFrame(
        {
            "cell_id": gdf_wgs84["quadkey"].astype(str).to_numpy(),
            "region": None,  # filled by caller
            "x_meta": x_meta,
            "x_wp": x_wp,
            "wealth": gdf_wgs84["wealth"].astype(float).to_numpy(),
            "wealth_rank": wealth_rank,
            "x_coord": x,
            "y_coord": y,
            "area": area_m2,
            "distance_to_center": dist,
            "log_density": log_density,
            "p_meta": p_meta,
            "p_wp": p_wp,
            "residual": residual,
            "pop_meta": x_meta,
            "pop_worldpop": x_wp,
        }
    )

    return out, proj_crs


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Prepare student-ready anchor tables from outputs/{REGION}/02/harmonised_with_residual.gpkg"
    )
    p.add_argument(
        "--regions",
        type=str,
        default=None,
        help="Comma-separated region codes (default: all in config/regions.json)",
    )
    p.add_argument(
        "--projected-crs",
        type=str,
        default=None,
        help="Override projected CRS for ALL regions (e.g., EPSG:32651). Default: auto-pick UTM per region.",
    )
    p.add_argument(
        "--out-subdir",
        type=str,
        default="student_data",
        help="Subdirectory under outputs/{REGION}/ to write files (default: student_data)",
    )
    p.add_argument(
        "--output-root",
        type=str,
        default=None,
        help="If set, write each region to {output_root}/... (instead of outputs/{REGION}/{out_subdir}/).",
    )
    p.add_argument(
        "--flat-output",
        action="store_true",
        help="When used with --output-root, write flat files as {output_root}/{REGION}_{EPSGxxxx}.csv instead of per-region subfolders.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()
    import sys

    sys.path.insert(0, str(PROJECT_ROOT / "pipeline"))
    import region_config  # type: ignore

    if args.regions:
        regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    else:
        regions = region_config.list_regions()

    n_ok = 0
    n_skip = 0
    for region in regions:
        input_path = PROJECT_ROOT / "outputs" / region / "02" / "harmonised_with_residual.gpkg"
        if not input_path.exists():
            print(f"[SKIP] {region}: missing {input_path}")
            n_skip += 1
            continue

        try:
            df, proj_crs = prepare_region(input_path, projected_crs=args.projected_crs)
        except Exception as e:
            print(f"[FAIL] {region}: {e}")
            n_skip += 1
            continue
        df["region"] = region

        if args.output_root:
            out_root = Path(args.output_root)
            if args.flat_output:
                epsg = str(proj_crs).replace(":", "")
                out_dir = out_root
                out_csv = out_dir / f"{region}_{epsg}.csv"
            else:
                out_dir = out_root / region
                out_csv = out_dir / "anchor_table.csv"
        else:
            out_dir = PROJECT_ROOT / "outputs" / region / args.out_subdir
            out_csv = out_dir / "anchor_table.csv"
        out_dir.mkdir(parents=True, exist_ok=True)
        df.to_csv(out_csv, index=False)
        print(f"[OK] {region}: wrote {out_csv} ({len(df):,} rows)")
        n_ok += 1

    print(f"\nDone. Regions processed: {n_ok}, skipped/failed: {n_skip}")
    print("Note: x_meta/x_wp are raw counts. Use p_meta/p_wp (shares) for share-based analyses.")


if __name__ == "__main__":
    main()

