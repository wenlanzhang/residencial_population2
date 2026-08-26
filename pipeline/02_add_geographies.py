#!/usr/bin/env python3
"""
Step 02 (event-footprint prep) — Attach analysis geography to the aligned quadkey cache.

Does not run SEM / Gini / correlation. Labels only.

Joins each aligned quadkey to:
  - country / ISO3 from footprint config
  - GHSL-SMOD settlement class (detailed + collapsed Urban centre / Town / Rural)
  - GHSL urban-centre ID and name (UCDB)
  - optional city boundary (e.g. Nairobi, Mombasa)

Usage:
  python pipeline/02_add_geographies.py --footprint KEN
  python pipeline/02_add_geographies.py --footprint KEN --download-smod
  python pipeline/02_add_geographies.py --footprint KEN --workers 4

Inputs:
  data/processed/{CODE}_aligned.parquet   (legacy; now data/processed/footprints/)

Outputs:
  data/processed/{CODE}_aligned_geographies.parquet
  outputs/footprints/{CODE}/geographies/summary_by_ghsl_class.csv
  outputs/footprints/{CODE}/geographies/summary_by_urban_centre.csv
  outputs/footprints/{CODE}/geographies/summary_by_city_boundary.csv
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))

import region_config
from align_utils import add_shares_and_ratios
from ghsl_utils import (
    assign_smod_centroid,
    assign_smod_composition,
    attach_smod_columns,
    ensure_smod_raster,
)

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def parse_args():
    p = argparse.ArgumentParser(description="Add GHSL and admin geography labels to aligned quadkeys.")
    p.add_argument("--footprint", type=str, required=True, help="Footprint code from config (e.g. KEN)")
    p.add_argument("-i", "--input", type=Path, default=None, help="Override aligned parquet/gpkg from step 01")
    p.add_argument("-o", "--output", type=Path, default=None, help="Override labelled parquet path")
    p.add_argument("--smod", type=Path, default=None, help="Override GHS-SMOD GeoTIFF")
    p.add_argument("--ucdb", type=Path, default=None, help="Override GHS Urban Centre Database GPKG")
    p.add_argument("--download-smod", action="store_true", help="Download GHS-SMOD 30-arc-sec mosaic if missing")
    p.add_argument("--workers", type=int, default=1, help="Unused (kept for wrapper compatibility).")
    p.add_argument(
        "--smod-method",
        type=str,
        default="land",
        choices=["land", "majority", "centroid"],
        help="Which class is stored in ghsl_class (main analysis column). "
        "land (default): dominant non-water SMOD class; majority: overall "
        "all_touched majority; centroid: one sample. water_fraction and "
        "ghsl_class_majority are always stored when using land/majority.",
    )
    p.add_argument("--save-gpkg", action="store_true", help="Also write a GeoPackage for QGIS inspection")
    p.add_argument("--no-cities", action="store_true", help="Skip optional city-boundary overlay")
    p.add_argument("--no-ucdb", action="store_true", help="Skip GHSL urban-centre name join")
    return p.parse_args()


def load_aligned(path: Path) -> gpd.GeoDataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Aligned dataset not found: {path}\n"
            "  Run: python pipeline/01_harmonise_datasets.py --footprint KEN"
        )
    if path.suffix.lower() == ".parquet":
        gdf = gpd.read_parquet(path)
    else:
        gdf = gpd.read_file(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    elif str(gdf.crs) != "EPSG:4326":
        gdf = gdf.to_crs("EPSG:4326")
    if "quadkey" not in gdf.columns:
        raise ValueError(f"Expected quadkey column in {path}")
    return gdf


def _largest_overlap_join(left: gpd.GeoDataFrame, right: gpd.GeoDataFrame, cols: list[str]) -> pd.DataFrame:
    """
    Spatial join keeping the right-hand polygon with the largest intersection area
    per left geometry. Returns a DataFrame indexed like left, with `cols`.
    """
    keep = [c for c in cols if c in right.columns]
    if not keep:
        return pd.DataFrame(index=left.index, columns=cols)

    right = right[["geometry"] + keep].copy()
    right = right[~right.geometry.is_empty & right.geometry.notna()]
    if right.empty:
        return pd.DataFrame(index=left.index, columns=keep)

    crs_area = left.estimate_utm_crs()
    left_tmp = left[["geometry"]].to_crs(crs_area).copy()
    left_tmp["_left_id"] = np.arange(len(left_tmp))
    right_p = right.to_crs(crs_area)
    joined = left_tmp.sjoin(right_p, how="left", predicate="intersects")
    if joined.empty:
        return pd.DataFrame(index=left.index, columns=keep)

    # Rows with no match keep NaN
    unmatched = joined["index_right"].isna()
    if unmatched.all():
        out = pd.DataFrame(index=left.index, columns=keep)
        return out

    matched = joined.loc[~unmatched].copy()
    if matched.empty:
        return pd.DataFrame(index=left.index, columns=keep)

    left_geom = matched.geometry
    right_geom = right_p.geometry.loc[matched["index_right"].astype(int)].values
    inter = left_geom.intersection(gpd.GeoSeries(right_geom, index=matched.index, crs=crs_area))
    matched["_overlap"] = inter.area
    best = matched.sort_values("_overlap", ascending=False).drop_duplicates("_left_id", keep="first")
    out = pd.DataFrame(index=np.arange(len(left)), columns=keep)
    out.loc[best["_left_id"].to_numpy(), keep] = best[keep].to_numpy()
    out.index = left.index
    return out


def add_smod(gdf: gpd.GeoDataFrame, smod_path: Path, method: str = "land") -> gpd.GeoDataFrame:
    """
    Assign GHS-SMOD composition to each quadkey.

    Always stores (except centroid-only):
      water_fraction, ghsl_class_majority (overall SMOD majority),
      ghsl_class (main): dominant land class unless the cell has no land pixels.

    method selects which label is copied into ghsl_class:
      land      — dominant_land_class (default; people live on the land portion)
      majority  — overall majority including water (sensitivity)
      centroid  — one sample at the representative point
    """
    method = (method or "land").strip().lower()
    print(f"  GHS-SMOD composition ({method}) ← {smod_path}")
    if method == "centroid":
        codes = assign_smod_centroid(gdf, smod_path)
        gdf = attach_smod_columns(gdf, codes=codes)
    else:
        comp = assign_smod_composition(gdf, smod_path)
        gdf = attach_smod_columns(gdf, composition=comp)
        if method == "majority":
            gdf["ghsl_class"] = gdf["ghsl_class_majority"]
            gdf["ghsl_smod"] = gdf["ghsl_smod_majority"]
            gdf["ghsl_smod_label"] = gdf["ghsl_smod_majority_label"]
    n_ok = gdf["ghsl_class"].notna().sum()
    print(f"    labelled {n_ok} / {len(gdf)} quadkeys")
    if n_ok:
        print("    main ghsl_class (dominant land unless 100% water):")
        print(gdf["ghsl_class"].value_counts(dropna=False).to_string())
        if "ghsl_class_majority" in gdf.columns:
            print("    sensitivity ghsl_class_majority (overall SMOD majority):")
            print(gdf["ghsl_class_majority"].value_counts(dropna=False).to_string())
        if "water_fraction" in gdf.columns:
            wf = gdf["water_fraction"]
            coastal = (wf > 0) & (gdf["ghsl_class"] != "Water")
            print(
                f"    water_fraction: median={wf.median():.2f}; "
                f"coastal-but-land-class cells: {int(coastal.sum())}"
            )
    return gdf


def add_ucdb(gdf: gpd.GeoDataFrame, ucdb_path: Path, iso3: str | None) -> gpd.GeoDataFrame:
    print(f"  GHSL urban centres (UCDB) ← {ucdb_path}")
    bbox = tuple(gdf.total_bounds)
    uc = gpd.read_file(ucdb_path, bbox=bbox)
    if uc.crs is None:
        uc = uc.set_crs("EPSG:4326")
    elif str(uc.crs) != "EPSG:4326":
        uc = uc.to_crs("EPSG:4326")
    if iso3 and "CTR_MN_ISO" in uc.columns:
        # Keep this country plus unnamed/cross-border centres that still intersect
        uc_iso = uc[uc["CTR_MN_ISO"].astype(str).str.upper() == iso3.upper()]
        # Also keep centres whose bbox overlaps the footprint (border towns)
        minx, miny, maxx, maxy = gdf.total_bounds
        uc_overlap = uc.cx[minx:maxx, miny:maxy]
        uc = pd.concat([uc_iso, uc_overlap]).drop_duplicates(subset=["ID_HDC_G0"] if "ID_HDC_G0" in uc.columns else None)
        uc = gpd.GeoDataFrame(uc, geometry="geometry", crs="EPSG:4326")
    else:
        minx, miny, maxx, maxy = gdf.total_bounds
        uc = uc.cx[minx:maxx, miny:maxy]

    rename = {}
    if "ID_HDC_G0" in uc.columns:
        rename["ID_HDC_G0"] = "urban_centre_id"
    if "UC_NM_MN" in uc.columns:
        rename["UC_NM_MN"] = "urban_centre"
    uc = uc.rename(columns=rename)
    cols = [c for c in ("urban_centre_id", "urban_centre") if c in uc.columns]
    labels = _largest_overlap_join(gdf, uc, cols)
    gdf = gdf.copy()
    for c in cols:
        gdf[c] = labels[c].values
    n = gdf["urban_centre"].notna().sum() if "urban_centre" in gdf.columns else 0
    print(f"    {n} quadkeys inside an urban centre")
    return gdf


def add_city_boundaries(gdf: gpd.GeoDataFrame, city_boundaries: dict) -> gpd.GeoDataFrame:
    """Overlay named city polygons; a quadkey gets the city with largest overlap."""
    parts = []
    for name, path in city_boundaries.items():
        path = Path(path)
        if not path.exists():
            print(f"  city boundary missing, skip {name}: {path}")
            continue
        city = gpd.read_file(path)
        if city.crs is None:
            city = city.set_crs("EPSG:4326")
        elif str(city.crs) != "EPSG:4326":
            city = city.to_crs("EPSG:4326")
        city = city[["geometry"]].copy()
        city["city_boundary"] = name
        parts.append(city)
    if not parts:
        return gdf
    cities = gpd.GeoDataFrame(pd.concat(parts, ignore_index=True), crs="EPSG:4326")
    print(f"  city boundaries: {', '.join(city_boundaries.keys())}")
    labels = _largest_overlap_join(gdf, cities, ["city_boundary"])
    gdf = gdf.copy()
    gdf["city_boundary"] = labels["city_boundary"].values
    print(gdf["city_boundary"].value_counts(dropna=False).to_string())
    return gdf


def summarise(gdf: gpd.GeoDataFrame, group_cols: list[str]) -> pd.DataFrame:
    present = [c for c in group_cols if c in gdf.columns]
    if not present:
        return pd.DataFrame()
    work = gdf.copy()
    for c in present:
        work[c] = work[c].fillna("—")
    work["meta_observed"] = work["meta_baseline"].notna() if "meta_baseline" in work.columns else False
    agg = {
        "quadkey": "count",
        "meta_observed": "sum",
        "meta_baseline": "sum",
        "worldpop_count": "sum",
    }
    if "poverty_mean" in work.columns:
        agg["poverty_mean"] = "mean"
    if "ratio_meta_wp" in work.columns:
        agg["ratio_meta_wp"] = "median"
    if "repr_residual" in work.columns:
        agg["repr_residual"] = "mean"
    out = work.groupby(present, dropna=False).agg(agg).reset_index()
    out = out.rename(
        columns={
            "quadkey": "n_quadkeys",
            "meta_observed": "n_meta_observed",
            "meta_baseline": "meta_baseline_sum",
            "worldpop_count": "worldpop_sum",
        }
    )
    out["n_meta_na"] = out["n_quadkeys"] - out["n_meta_observed"]
    if "meta_baseline_sum" in out.columns and "worldpop_sum" in out.columns:
        out["ratio_totals"] = out["meta_baseline_sum"] / out["worldpop_sum"].replace(0, np.nan)
    return out.sort_values("n_quadkeys", ascending=False)


def main():
    args = parse_args()
    cfg = region_config.get_footprint_config(args.footprint)
    iso3 = cfg.get("iso3") or args.footprint
    country_name = cfg.get("country_name") or cfg.get("name") or iso3

    in_path = args.input or region_config.get_aligned_parquet(args.footprint)
    out_parquet = args.output or region_config.get_geographies_parquet(args.footprint)
    out_dir = region_config.get_footprint_output_dir(args.footprint, "geographies")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Footprint: {args.footprint} ({cfg.get('name', args.footprint)})")
    print(f"  Input: {in_path}")
    gdf = load_aligned(in_path)
    print(f"  Quadkeys: {len(gdf)}")

    gdf = gdf.copy()
    gdf["country"] = country_name
    gdf["iso3"] = iso3

    smod_path = args.smod or cfg.get("ghsl_smod")
    smod_path = ensure_smod_raster(Path(smod_path), download=args.download_smod)
    gdf = add_smod(gdf, smod_path, method=getattr(args, "smod_method", "land"))

    if not args.no_ucdb:
        ucdb_path = args.ucdb or cfg.get("ghsl_ucdb")
        if ucdb_path and Path(ucdb_path).exists():
            gdf = add_ucdb(gdf, Path(ucdb_path), iso3=iso3)
        else:
            print(f"  UCDB missing ({ucdb_path}); urban_centre will be empty")

    if not args.no_cities:
        cities = cfg.get("city_boundaries") or {}
        if cities:
            gdf = add_city_boundaries(gdf, cities)

    # Stage-2 shares: land cells with Meta observed and WorldPop > 0.
    # Both M* and W* use this identical S (WorldPop in Meta-NA cells is excluded).
    if "ghsl_class" in gdf.columns:
        land = gdf["ghsl_class"].isin(["Urban centre", "Town / semi-dense", "Rural"])
        print("\n--- Stage-2 shares (land ∩ Meta observed ∩ WorldPop>0) ---")
        gdf = add_shares_and_ratios(gdf, universe=land)

    # Column order: identifiers, observed-user baseline, resident population, residuals, geography
    preferred = [
        "quadkey",
        "meta_baseline",
        "meta_observed",
        "worldpop_count",
        "poverty_mean",
        "poverty_source",
        "meta_share",
        "worldpop_share",
        "repr_residual",
        "diff_meta_wp",
        "ratio_meta_wp",
        "log_ratio_meta_wp",
        "country",
        "iso3",
        "ghsl_smod",
        "ghsl_smod_label",
        "ghsl_class",
        "ghsl_class_majority",
        "water_fraction",
        "urban_centre_id",
        "urban_centre",
        "city_boundary",
        "geometry",
    ]
    rest = [c for c in gdf.columns if c not in preferred]
    gdf = gdf[[c for c in preferred if c in gdf.columns] + rest]

    out_parquet.parent.mkdir(parents=True, exist_ok=True)
    gdf.to_parquet(out_parquet, index=False)
    print(f"\nSaved: {out_parquet}")

    if args.save_gpkg:
        gpkg_path = out_dir / "aligned_with_geographies.gpkg"
        gdf.to_file(gpkg_path, driver="GPKG")
        print(f"Saved: {gpkg_path}")

    tables = {
        "summary_by_ghsl_class.csv": summarise(gdf, ["country", "ghsl_class", "ghsl_smod_label"]),
        "summary_by_ghsl_majority.csv": summarise(gdf, ["country", "ghsl_class_majority"]),
        "summary_by_urban_centre.csv": summarise(gdf, ["country", "ghsl_class", "urban_centre"]),
        "summary_by_city_boundary.csv": summarise(gdf, ["country", "city_boundary", "ghsl_class"]),
    }
    for name, table in tables.items():
        if table.empty:
            continue
        dest = out_dir / name
        table.to_csv(dest, index=False)
        print(f"Saved: {dest}")

    print("\n--- Preview (first 8 rows) ---")
    preview_cols = [
        c
        for c in [
            "quadkey",
            "meta_baseline",
            "worldpop_count",
            "poverty_mean",
            "country",
            "ghsl_class",
            "urban_centre",
            "city_boundary",
        ]
        if c in gdf.columns
    ]
    print(gdf[preview_cols].head(8).to_string(index=False))
    return gdf


if __name__ == "__main__":
    main()
