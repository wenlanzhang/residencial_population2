#!/usr/bin/env python3
"""
Cross-city comparison: run steps 01, 02, 03c for multiple regions, aggregate into summary tables.

Table 1: City | N Cells | Spearman ρ | Pearson r | ΔGini (Meta−WP) | Top 10% WP | Top 10% Meta | Δ Top 10% | Mean Residual
Table 2: City | OLS τ | SEM τ | exp(SEM τ) | SEM p-value  (Poverty Effect, Spatially Corrected)

Usage:
  python cross-city/run_cross_city_table.py                    # Run 01+02+03c for all regions, then aggregate
  python cross-city/run_cross_city_table.py --aggregate-only   # Only aggregate from existing outputs
  python cross-city/run_cross_city_table.py --regions KEN_Nairobi,KEN_Mombasa,MEX  # Limit to specific regions
"""

import argparse
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


def run_step_01(region: str, ref_hour: Optional[int] = None) -> bool:
    """Run harmonisation for region. Returns True on success."""
    cmd = [sys.executable, str(SCRIPTS / "01_harmonise_datasets.py"), "--region", region]
    if ref_hour is not None:
        cmd.extend(["--ref-hour", str(ref_hour)])
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

    if not gpkg_path.exists():
        return None

    metrics = {"City": city_label, "Region": region}

    # Read Table1 if available
    if tbl1_path.exists():
        tbl1 = pd.read_csv(tbl1_path)
        metric_to_val = dict(zip(tbl1.iloc[:, 0], tbl1.iloc[:, 1]))
        metrics["N_Cells"] = int(metric_to_val.get("Number of quadkeys", 0))
        metrics["Spearman_rho"] = _to_float(metric_to_val.get("Spearman ρ (log shares)", ""))
        metrics["Pearson_r"] = _to_float(metric_to_val.get("Pearson r (log shares)", ""))
        metrics["Delta_Gini"] = _to_float(metric_to_val.get("ΔGini (Meta − WP)", ""))
        metrics["Mean_Residual"] = _to_float(metric_to_val.get("Mean allocation_residual", ""))
    else:
        # Compute from gpkg
        import geopandas as gpd
        from scipy import stats

        gdf = gpd.read_file(gpkg_path)
        if "allocation_residual" not in gdf.columns:
            return None
        wp_s = gdf["worldpop_share"].values
        meta_s = gdf["meta_share"].values
        valid = (wp_s > 0) & (meta_s > 0)
        wp_s = wp_s[valid]
        meta_s = meta_s[valid]
        log_wp = np.log(wp_s)
        log_meta = np.log(meta_s)

        metrics["N_Cells"] = int(valid.sum())
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
        import geopandas as gpd
        gdf = gpd.read_file(gpkg_path)
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
    args = p.parse_args()

    regions = get_regions(args.regions)
    if not regions:
        print("No regions to process. Check --regions or config/regions.json.")
        sys.exit(1)

    print(f"Regions: {', '.join(regions)}")

    if not args.aggregate_only:
        for region in regions:
            print(f"\n--- Running 01 + 02 + 03c for {region} ---")
            if not run_step_01(region, ref_hour=args.ref_hour):
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
        "N_Cells",
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


if __name__ == "__main__":
    main()
