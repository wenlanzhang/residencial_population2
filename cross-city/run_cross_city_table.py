#!/usr/bin/env python3
"""
Cross-city comparison: run steps 01, 02, 03c for multiple regions, aggregate into summary tables.

Table 1: City | N Cells | Total WorldPop | Total Meta (FB) | Total area (km²) | Spearman ρ | Pearson r | ...
Table 2: City | OLS τ | SEM τ | exp(SEM τ) | SEM p-value  (Poverty Effect, Spatially Corrected)

Usage:
  python cross-city/run_cross_city_table.py                    # Run 01+02+03c for all regions, then aggregate
  python cross-city/run_cross_city_table.py --aggregate-only   # Only aggregate from existing outputs
  python cross-city/run_cross_city_table.py --regions KEN_Nairobi,KEN_Mombasa,MEX  # Limit to specific regions
"""

import argparse
import math
import subprocess
import sys
from pathlib import Path
from typing import Optional

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "pipeline"
sys.path.insert(0, str(SCRIPTS))


def get_regions(regions_arg=None):
    """Get list of region codes from config. Supports prefixes: PHI -> both PHI cities, KEN -> both Kenya cities."""
    import region_config
    all_regions = region_config.list_regions()
    if regions_arg:
        requested = [r.strip() for r in regions_arg.split(",") if r.strip()]
        result = []
        for r in requested:
            expanded = region_config.expand_region_to_list(r)
            if not expanded:
                continue
            result.extend(expanded)
        return list(dict.fromkeys(result))  # dedupe; empty if no matches
    return all_regions


def run_step_01(
    region: str,
    ref_hour: Optional[int] = None,
    poverty_source: Optional[str] = None,
    clip_source: Optional[str] = None,
) -> bool:
    """Run harmonisation for region. Returns True on success."""
    cmd = [sys.executable, str(SCRIPTS / "01_harmonise_datasets.py"), "--region", region]
    if ref_hour is not None:
        cmd.extend(["--ref-hour", str(ref_hour)])
    if poverty_source:
        cmd.extend(["--poverty-source", poverty_source])
    if clip_source:
        cmd.extend(["--clip-source", clip_source])
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode == 0


def run_step_02(region: str) -> bool:
    """Run Meta vs WorldPop comparison for region. Returns True on success."""
    cmd = [sys.executable, str(SCRIPTS / "02_compare_meta_worldpop.py"), "--region", region]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode == 0


def run_step_03c(region: str) -> bool:
    """Run spatial regression (03c) for region. Returns True on success."""
    import region_config
    gpkg_02 = region_config.get_output_dir(region, "02") / "harmonised_with_residual.gpkg"
    out_root = region_config.get_output_dir(region, "02").parent
    cmd = [sys.executable, str(SCRIPTS / "03c_spatial_regression.py"), "-i", str(gpkg_02), "-o", str(out_root)]
    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
    return result.returncode == 0


def extract_metrics_from_region(region: str) -> dict | None:
    """
    Extract comparison metrics from a region's 02 output.
    Reads Table1 and lorenz_headlines CSVs, or computes from harmonised_with_residual.gpkg.
    """
    import region_config
    out_dir = region_config.get_output_dir(region, "02")
    cfg = region_config.get_region_config(region)
    city_label = cfg.get("city_label") or cfg.get("map_bbox_label") or cfg.get("name") or region

    # Try reading from CSVs first
    tbl1_path = out_dir / "Table1_meta_worldpop_metrics.csv"
    lorenz_path = out_dir / "02_lorenz_headlines.csv"
    gpkg_path = out_dir / "harmonised_with_residual.gpkg"
    gpkg_01_path = region_config.get_output_dir(region, "01") / "harmonised_meta_worldpop.gpkg"

    if not gpkg_path.exists():
        return None

    import geopandas as gpd

    # Step 02 GPKG = analysis grid only (both shares > 0; zeros dropped in 02_compare_meta_worldpop.py).
    gdf_analysis = gpd.read_file(gpkg_path)
    metrics = {"City": city_label, "Region": region}

    # City-wide totals (step 01): all harmonised quadkeys, including zeros — geodata export unchanged.
    if gpkg_01_path.exists():
        gdf_all = gpd.read_file(gpkg_01_path)
        metrics.update(_harmonised_city_totals(gdf_all))
    else:
        metrics.update(_harmonised_city_totals(gdf_analysis))

    # Analysis grid (step 02): valid cells only — same rows as correlations / regressions.
    metrics.update(_analysis_grid_totals(gdf_analysis, metrics.get("Total_Area_km2")))
    metrics.update(
        _population_pct_of_total(
            metrics.get("Total_WorldPop"),
            metrics.get("Total_Meta_FB"),
            metrics.get("Valid_WorldPop"),
            metrics.get("Valid_Meta_FB"),
        )
    )

    # Harmonised grid area as % of the city boundary used in step 01.
    gdf_for_crs = gdf_all if gpkg_01_path.exists() else gdf_analysis
    city_boundary_km2 = _city_boundary_area_km2(cfg, gdf_for_crs, region)
    metrics.update(
        _grid_area_pct_of_city(
            metrics.get("Total_Area_km2"),
            metrics.get("Valid_Area_km2"),
            city_boundary_km2,
        )
    )

    gdf = gdf_analysis  # downstream metrics read from analysis grid

    # Read Table1 if available
    if tbl1_path.exists():
        tbl1 = pd.read_csv(tbl1_path)
        metric_to_val = dict(zip(tbl1.iloc[:, 0], tbl1.iloc[:, 1]))
        n_from_csv = int(metric_to_val.get("Number of quadkeys", 0))
        if not metrics.get("N_Cells_valid"):
            metrics["N_Cells_valid"] = n_from_csv
        metrics["Spearman_rho"] = _to_float(metric_to_val.get("Spearman ρ (log shares)", ""))
        metrics["Pearson_r"] = _to_float(metric_to_val.get("Pearson r (log shares)", ""))
        metrics["Delta_Gini"] = _to_float(metric_to_val.get("ΔGini (Meta − WP)", ""))
        metrics["Mean_Residual"] = _to_float(metric_to_val.get("Mean allocation_residual", ""))
    else:
        # Compute from gpkg
        from scipy import stats

        if "allocation_residual" not in gdf.columns:
            return None
        wp_s = gdf["worldpop_share"].values
        meta_s = gdf["meta_share"].values
        valid = (wp_s > 0) & (meta_s > 0)
        wp_s = wp_s[valid]
        meta_s = meta_s[valid]
        log_wp = np.log(wp_s)
        log_meta = np.log(meta_s)

        metrics["N_Cells_valid"] = int(valid.sum())
        r_s, _ = stats.spearmanr(log_wp, log_meta)
        r_p, _ = stats.pearsonr(log_wp, log_meta)
        metrics["Spearman_rho"] = float(r_s) if not np.isnan(r_s) else np.nan
        metrics["Pearson_r"] = float(r_p) if not np.isnan(r_p) else np.nan

        gini_wp = _gini(wp_s)
        gini_meta = _gini(meta_s)
        metrics["Delta_Gini"] = float(gini_meta - gini_wp)

        res = gdf.loc[valid, "allocation_residual"].values
        metrics["Mean_Residual"] = float(np.nanmean(res)) if len(res) > 0 else np.nan

    # Top 10% WP, Top 10% Meta, Δ Top 10% from lorenz_headlines or compute
    if lorenz_path.exists():
        lorenz = pd.read_csv(lorenz_path)
        # First row is Top 10% (pct=0.10)
        if len(lorenz) > 0:
            row = lorenz.iloc[0]
            metrics["Top10_WP"] = float(row.get("Y_WP", np.nan))
            metrics["Top10_Meta"] = float(row.get("Y_Meta", np.nan))
            metrics["Top10_Delta_Share"] = float(row.get("Delta_Y_Meta_minus_WP", np.nan))
        else:
            metrics["Top10_WP"] = np.nan
            metrics["Top10_Meta"] = np.nan
            metrics["Top10_Delta_Share"] = np.nan
    else:
        wp_s = gdf["worldpop_share"].values
        meta_s = gdf["meta_share"].values
        valid = (wp_s > 0) & (meta_s > 0)
        wp_s = wp_s[valid]
        meta_s = meta_s[valid]
        n = len(wp_s)
        k = max(1, int(np.ceil(0.10 * n)))
        wp_sorted = np.sort(wp_s)[::-1]
        meta_sorted = np.sort(meta_s)[::-1]
        metrics["Top10_WP"] = float(wp_sorted[:k].sum())
        metrics["Top10_Meta"] = float(meta_sorted[:k].sum())
        metrics["Top10_Delta_Share"] = float(meta_sorted[:k].sum() - wp_sorted[:k].sum())
    if "Top10_WP" not in metrics:
        metrics["Top10_WP"] = np.nan
    if "Top10_Meta" not in metrics:
        metrics["Top10_Meta"] = np.nan
    if "Top10_Delta_Share" not in metrics:
        metrics["Top10_Delta_Share"] = np.nan

    return metrics


def extract_rank_instability_from_region(region: str) -> dict | None:
    """Load Table_rank_instability.csv from 03b_stratified when present."""
    import region_config

    path = region_config.get_output_dir(region, "02").parent / "03b_stratified" / "Table_rank_instability.csv"
    if not path.exists():
        return None
    df = pd.read_csv(path)
    if df.empty:
        return None
    cfg = region_config.get_region_config(region)
    city_label = cfg.get("city_label") or cfg.get("map_bbox_label") or cfg.get("name") or region
    row = df.iloc[0].to_dict()
    row["City"] = city_label
    row["Region"] = region
    return row


def extract_poverty_effect_from_region(region: str) -> dict | None:
    """
    Extract Table 2 — Poverty Effect (Spatially Corrected) from 03c output.
    Columns: City, OLS τ, SEM τ, exp(SEM τ), SEM p-value
    """
    import region_config
    out_dir = region_config.get_output_dir(region, "02").parent / "03c_spatial_regression"
    cfg = region_config.get_region_config(region)
    city_label = cfg.get("city_label") or cfg.get("map_bbox_label") or cfg.get("name") or region

    tau_path = out_dir / "Table_tau_comparison.csv"
    if not tau_path.exists():
        return None

    df = pd.read_csv(tau_path)
    ols_row = df[df["Model"].str.contains("OLS", na=False)]
    sem_row = df[df["Model"].str.contains("SEM", na=False)]

    ols_tau = _to_float(ols_row["tau"].iloc[0]) if len(ols_row) > 0 else np.nan
    sem_tau = _to_float(sem_row["tau"].iloc[0]) if len(sem_row) > 0 else np.nan
    sem_p = _to_float(sem_row["p_value"].iloc[0]) if len(sem_row) > 0 else np.nan
    exp_sem_tau = np.exp(sem_tau) if not np.isnan(sem_tau) else np.nan

    def _p_fmt(p):
        if np.isnan(p):
            return ""
        if p < 0.001:
            return "<0.001"
        return f"{p:.3f}"

    return {
        "City": city_label,
        "Region": region,
        "OLS_tau": ols_tau,
        "SEM_tau": sem_tau,
        "exp_SEM_tau": exp_sem_tau,
        "SEM_p_value": sem_p,
        "SEM_p_fmt": _p_fmt(sem_p),
    }


def _to_float(x):
    try:
        return float(x)
    except (ValueError, TypeError):
        return float("nan")


def _gini(x):
    x = np.asarray(x)
    x = x[~np.isnan(x) & (x >= 0)]
    if len(x) == 0:
        return np.nan
    x = np.sort(x)
    n = len(x)
    cumx = np.cumsum(x)
    return (2 * np.sum((np.arange(1, n + 1)) * x) - (n + 1) * np.sum(x)) / (n * np.sum(x))


def _pick_projected_crs(gdf_wgs84) -> str:
    """UTM CRS for area sums (matches pipeline conventions where possible)."""
    b = gdf_wgs84.total_bounds
    clon = float((b[0] + b[2]) / 2)
    clat = float((b[1] + b[3]) / 2)
    if 118 <= clon <= 127 and 5 <= clat <= 20:
        return "EPSG:32651"
    if 36 <= clon <= 40 and -4.5 <= clat <= 0:
        return "EPSG:32737"
    zone = int(math.floor((clon + 180.0) / 6.0) + 1)
    zone = max(1, min(zone, 60))
    epsg = (32600 + zone) if clat >= 0 else (32700 + zone)
    return f"EPSG:{epsg}"


def _polygon_area_km2(gdf) -> float:
    """Sum quadkey polygon areas in a projected CRS (km²)."""
    gdf_wgs = gdf.to_crs("EPSG:4326") if str(gdf.crs) != "EPSG:4326" else gdf
    gdf_proj = gdf_wgs.to_crs(_pick_projected_crs(gdf_wgs))
    return float((gdf_proj.geometry.area / 1e6).sum())


def _city_boundary_area_km2(cfg, reference_gdf, region: str | None = None) -> float | None:
    """Area of the city clip polygon in km² (same UTM as grid).

    Prefers the polygon saved by step 01 (`outputs/{REGION}/01/clip_boundary.gpkg`)
    so OSM/geoBoundaries runs match the boundary that was actually used.
    """
    import geopandas as gpd
    import region_config
    from clip_utils import load_clip_boundary, unary_geom

    code = region or cfg.get("region_code")
    boundary = None
    if code:
        saved = region_config.get_output_dir(code, "01") / "clip_boundary.gpkg"
        if saved.exists():
            boundary = gpd.read_file(saved)
    if boundary is None:
        try:
            boundary = load_clip_boundary(cfg, region_code=code)
        except Exception as e:
            print(f"  City boundary skipped for {code}: {e}")
            return None
    if boundary is None:
        return None

    ref_wgs = reference_gdf.to_crs("EPSG:4326") if str(reference_gdf.crs) != "EPSG:4326" else reference_gdf
    proj_crs = _pick_projected_crs(ref_wgs)
    if boundary.crs != proj_crs:
        boundary = boundary.to_crs(proj_crs)
    return float(unary_geom(boundary).area / 1e6)


def _grid_area_pct_of_city(
    total_grid_area_km2: float | None,
    valid_grid_area_km2: float | None,
    city_boundary_km2: float | None,
) -> dict:
    """Grid coverage relative to official city boundary area."""
    if not city_boundary_km2 or city_boundary_km2 <= 0:
        return {
            "Total_Area_pct_city": np.nan,
            "Valid_Area_pct_city": np.nan,
        }
    total_pct = (
        (total_grid_area_km2 / city_boundary_km2 * 100.0)
        if total_grid_area_km2 is not None
        else np.nan
    )
    valid_pct = (
        (valid_grid_area_km2 / city_boundary_km2 * 100.0)
        if valid_grid_area_km2 is not None
        else np.nan
    )
    return {
        "Total_Area_pct_city": total_pct,
        "Valid_Area_pct_city": valid_pct,
    }


def _harmonised_city_totals(gdf) -> dict:
    """
    City-wide totals from step-01 harmonised grid (all quadkeys, including zero-count cells).
    Geodata export is not filtered here — filter applies only in step 02 and in summary tables.
    """
    wp = pd.to_numeric(gdf["worldpop_count"], errors="coerce").fillna(0)
    meta = pd.to_numeric(gdf["meta_baseline"], errors="coerce").fillna(0)
    return {
        "N_Cells_total": len(gdf),
        "Total_WorldPop": float(wp.sum()),
        "Total_Meta_FB": float(meta.sum()),
        "Total_Area_km2": _polygon_area_km2(gdf),
    }


def _population_pct_of_total(
    total_wp: float | None,
    total_meta: float | None,
    valid_wp: float | None,
    valid_meta: float | None,
) -> dict:
    """Share of harmonised population counts that fall in valid (analysis) cells."""
    wp_pct = (
        (valid_wp / total_wp * 100.0) if total_wp is not None and total_wp > 0 else np.nan
    )
    meta_pct = (
        (valid_meta / total_meta * 100.0)
        if total_meta is not None and total_meta > 0
        else np.nan
    )
    return {
        "Valid_WorldPop_pct": wp_pct,
        "Valid_Meta_pct": meta_pct,
    }


def _analysis_grid_totals(gdf_analysis, total_harmonised_area_km2: float | None) -> dict:
    """
    Analysis grid (step-02 GPKG): cells with both shares > 0 (zeros already dropped in step 02).
    Population and area sums match N_Cells_valid and all share-based pipeline outputs.
    """
    wp = pd.to_numeric(gdf_analysis["worldpop_count"], errors="coerce").fillna(0)
    meta = pd.to_numeric(gdf_analysis["meta_baseline"], errors="coerce").fillna(0)
    valid_area_km2 = _polygon_area_km2(gdf_analysis)
    denom = total_harmonised_area_km2 if total_harmonised_area_km2 else np.nan
    valid_area_pct = (
        (valid_area_km2 / denom * 100.0) if denom and denom > 0 else np.nan
    )
    return {
        "N_Cells_valid": len(gdf_analysis),
        "Valid_WorldPop": float(wp.sum()),
        "Valid_Meta_FB": float(meta.sum()),
        "Valid_Area_km2": valid_area_km2,
        "Valid_Area_pct": valid_area_pct,
    }


def main():
    p = argparse.ArgumentParser(
        description="Cross-city comparison: run 01+02 for regions, produce summary table",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--aggregate-only",
        action="store_true",
        help="Only aggregate from existing 02 outputs (skip running 01 and 02)",
    )
    p.add_argument(
        "--regions",
        type=str,
        default=None,
        help="Comma-separated region codes (default: all from config)",
    )
    p.add_argument(
        "-o", "--output",
        type=Path,
        default=None,
        help="Output directory or Table 1 CSV path (default: outputs/cross-city/). Tables saved to same dir.",
    )
    p.add_argument(
        "--ref-hour",
        type=int,
        default=None,
        choices=[0, 8, 16],
        help="Reference hour for Meta baseline (0, 8, or 16). Uses fb_baseline_median_h{HOUR:02d}.gpkg.",
    )
    p.add_argument(
        "--poverty-source",
        type=str,
        default=None,
        choices=["grdi", "rwi"],
        help="Poverty layer for step 01: grdi (default GeoTIFF) or rwi (Meta RWI CSV).",
    )
    p.add_argument(
        "--clip-source",
        type=str,
        default=None,
        choices=["local", "osm", "geob"],
        help="City boundary for step 01: local (default), osm, or geob.",
    )
    args = p.parse_args()

    regions = get_regions(args.regions)
    if not regions:
        print("No regions to process. Check --regions or config/regions.json.")
        sys.exit(1)

    print(f"Regions: {', '.join(regions)}")

    if not args.aggregate_only:
        for region in regions:
            print(f"\n--- Running 01 + 02 + 03c for {region} ---")
            if not run_step_01(
                region,
                ref_hour=args.ref_hour,
                poverty_source=args.poverty_source,
                clip_source=args.clip_source,
            ):
                print(f"  WARNING: Step 01 failed for {region}")
            if not run_step_02(region):
                print(f"  WARNING: Step 02 failed for {region}")
            if not run_step_03c(region):
                print(f"  WARNING: Step 03c failed for {region}")

    # Aggregate Table 1 (comparison metrics)
    rows = []
    for region in regions:
        m = extract_metrics_from_region(region)
        if m:
            rows.append(m)
        else:
            print(f"  Skipped {region}: no 02 output found")

    if not rows:
        print("No metrics extracted. Run without --aggregate-only to generate 02 outputs first.")
        sys.exit(1)

    df = pd.DataFrame(rows)
    # Reorder columns for table
    col_order = [
        "City",
        "N_Cells_total",
        "Total_WorldPop",
        "Total_Meta_FB",
        "Total_Area_km2",
        "Total_Area_pct_city",
        "N_Cells_valid",
        "Valid_WorldPop",
        "Valid_WorldPop_pct",
        "Valid_Meta_FB",
        "Valid_Meta_pct",
        "Valid_Area_km2",
        "Valid_Area_pct",
        "Valid_Area_pct_city",
        "Spearman_rho",
        "Pearson_r",
        "Delta_Gini",
        "Top10_WP",
        "Top10_Meta",
        "Top10_Delta_Share",
        "Mean_Residual",
    ]
    df = df[[c for c in col_order if c in df.columns]]

    # Rename for display
    df = df.rename(columns={
        "N_Cells_total": "N cells (total)",
        "Total_WorldPop": "Total WorldPop",
        "Total_Meta_FB": "Total Meta (FB)",
        "Total_Area_km2": "Total area (km²)",
        "Total_Area_pct_city": "Total area (% of city)",
        "N_Cells_valid": "N cells (valid)",
        "Valid_WorldPop": "Valid WorldPop",
        "Valid_WorldPop_pct": "Valid WorldPop (% of total)",
        "Valid_Meta_FB": "Valid Meta (FB)",
        "Valid_Meta_pct": "Valid Meta (% of total)",
        "Valid_Area_km2": "Valid area (km²)",
        "Valid_Area_pct": "Valid area (% of harmonised grid)",
        "Valid_Area_pct_city": "Valid area (% of city)",
        "Spearman_rho": "Spearman ρ",
        "Pearson_r": "Pearson r",
        "Delta_Gini": "ΔGini (Meta−WP)",
        "Top10_WP": "Top 10% WP",
        "Top10_Meta": "Top 10% Meta",
        "Top10_Delta_Share": "Δ Top 10%",
        "Mean_Residual": "Mean Residual",
    })

    base = args.output or (PROJECT_ROOT / "outputs" / "cross-city" / "Table1_cross_city_table.csv")
    out_dir = base if (base.suffix == "" or base.is_dir()) else base.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    tbl1_path = out_dir / "Table1_cross_city_table.csv"
    df.to_csv(tbl1_path, index=False, float_format="%.4f")
    print(f"\nSaved: {tbl1_path}")
    print(df.to_string(index=False))

    # Table 2 — Poverty Effect (Spatially Corrected)
    tbl2_rows = []
    for region in regions:
        m = extract_poverty_effect_from_region(region)
        if m:
            tbl2_rows.append(m)
        else:
            print(f"  Skipped {region} for Table 2: no 03c output found")

    if tbl2_rows:
        df2 = pd.DataFrame(tbl2_rows)
        df2_out = df2[["City", "OLS_tau", "SEM_tau", "exp_SEM_tau", "SEM_p_fmt"]].copy()
        df2_out = df2_out.rename(columns={
            "OLS_tau": "OLS τ",
            "SEM_tau": "SEM τ",
            "exp_SEM_tau": "exp(SEM τ)",
            "SEM_p_fmt": "SEM p-value",
        })
        tbl2_path = out_dir / "Table2_poverty_effect_spatially_corrected.csv"
        df2_out.to_csv(tbl2_path, index=False, float_format="%.2f")
        print(f"\nSaved: {tbl2_path}")
        print("Table 2 — Poverty Effect (Spatially Corrected)")
        print(df2_out.to_string(index=False))
    else:
        print("\nTable 2 skipped: no 03c outputs. Run without --aggregate-only to generate.")

    # Rank instability (03b)
    rank_rows = []
    for region in regions:
        rm = extract_rank_instability_from_region(region)
        if rm:
            rank_rows.append(rm)
        else:
            print(f"  Skipped {region} for rank instability: no 03b Table_rank_instability.csv")

    if rank_rows:
        df_rank = pd.DataFrame(rank_rows)
        front = ["City", "Region"]
        rest = [c for c in df_rank.columns if c not in front]
        df_rank = df_rank[front + sorted(rest)]
        rank_out = out_dir / "Table_rank_instability_cross_city.csv"
        df_rank.to_csv(rank_out, index=False, float_format="%.6f")
        print(f"\nSaved: {rank_out}")
        print("Rank instability (Meta vs WorldPop shares, 03b analysis grid)")
        print(df_rank.to_string(index=False))
    else:
        print("\nRank instability cross-city table skipped: no 03b Table_rank_instability.csv files found.")


if __name__ == "__main__":
    main()
