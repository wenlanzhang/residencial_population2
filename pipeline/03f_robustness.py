#!/usr/bin/env python3
"""
03f — Sensitivity analyses for spatial error specification.

Loads harmonised_with_residual.gpkg, recreates treatment definition,
re-runs SEM under various filters. Outputs a summary table for reviewers.

Sections:
  A. Baseline SEM: Y ~ T + Distance + LogDensity (reference τ)
  B. Continuous poverty: Y ~ poverty_mean + Distance + LogDensity (β_poverty)
  C. Top vs Bottom quintile only: filter to extremes, redefine T, SEM
  D. Remove top 5% density cells: LogDensity ≤ 95th percentile
  E. Remove central 10%: Distance ≥ 10th percentile

Usage:
  conda activate geo_env_LLM
  python scripts/03f_robustness.py

Outputs: outputs/03f_robustness/Table_robustness_summary.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import scipy
if not hasattr(scipy, "inf"):
    scipy.inf = np.inf
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poverty_utils

DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg"
OUT_SUBDIR = "03f_robustness"


def _scalar(x):
    arr = np.asarray(x)
    return float(arr.flat[0]) if arr.size > 0 else np.nan


def _build_knn_weights(gdf, project_crs, k=6):
    """Build KNN weights (k=6) for numerical stability, no islands. Returns (gdf, w)."""
    from libpysal.weights import KNN
    gdf_proj = gdf.to_crs(project_crs)
    # Drop invalid geometries (empty centroids cause KNN to fail)
    valid_geom = poverty_utils.has_valid_centroids(gdf_proj)
    if not valid_geom.all():
        gdf = gdf.loc[valid_geom].reset_index(drop=True)
        gdf_proj = gdf_proj.loc[valid_geom].reset_index(drop=True)
    # Extract coords explicitly (from_dataframe can fail with Point geometries)
    xs = gdf_proj.geometry.centroid.x.values.astype(float)
    ys = gdf_proj.geometry.centroid.y.values.astype(float)
    valid_coords = np.isfinite(xs) & np.isfinite(ys)
    if not valid_coords.all():
        gdf = gdf.loc[valid_coords].reset_index(drop=True)
        gdf_proj = gdf_proj.loc[valid_coords].reset_index(drop=True)
        xs, ys = xs[valid_coords], ys[valid_coords]
    coords = np.column_stack([xs, ys])
    w = KNN.from_array(coords, k=k)
    w.transform = "r"
    return gdf, w


def run_sem(y, x, w, x_names):
    """Run ML_Error (SEM), return (coef_idx, sem) for extracting coefficient at index."""
    from spreg import ML_Error
    sem = ML_Error(y, x, w, name_y="Y", name_x=x_names, name_w="KNN", name_ds="quadkeys")
    return sem


def parse_args():
    p = argparse.ArgumentParser(description="03f — Sensitivity analyses for spatial error specification")
    p.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("-o", "--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    p.add_argument("--project-crs", type=str, default="EPSG:32737")
    return p.parse_args()


def main():
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Missing input: {args.input}. Run step 02 first.")

    out_dir = args.output_dir / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    gdf_full = poverty_utils.load_and_prepare_gdf(
        args.input, args.project_crs, residual_col="allocation_residual"
    )

    # Recreate treatment: T = 1 if poverty in top quartile
    poverty = gdf_full["poverty_mean"].values
    q75 = np.nanpercentile(poverty, 75)
    # Quintiles: Q1 = bottom 20%, Q5 = top 20%
    q1_pct = np.nanpercentile(poverty, 20)   # bottom quintile cutoff
    q5_pct = np.nanpercentile(poverty, 80)   # top quintile cutoff

    log_dens_full = np.log(gdf_full["PopulationDensity"].values + 1)
    dist_full = gdf_full["Distance"].values

    def _prepare_x(gdf, use_t=True, use_poverty=False):
        """Prepare X matrix: T or poverty_mean, Distance, LogDensity (all z-scored within sample)."""
        pov = gdf["poverty_mean"].values
        dist = gdf["Distance"].values
        ld = np.log(gdf["PopulationDensity"].values + 1)
        if use_t:
            t = (pov >= np.nanpercentile(pov, 75)).astype(int)
            X = pd.DataFrame({
                "T": t,
                "Distance": (dist - dist.mean()) / (dist.std() + 1e-10),
                "LogDensity": (ld - ld.mean()) / (ld.std() + 1e-10),
            })
        elif use_poverty:
            X = pd.DataFrame({
                "Poverty": (pov - pov.mean()) / (pov.std() + 1e-10),
                "Distance": (dist - dist.mean()) / (dist.std() + 1e-10),
                "LogDensity": (ld - ld.mean()) / (ld.std() + 1e-10),
            })
        else:
            X = pd.DataFrame({
                "T": (pov >= np.nanpercentile(pov, 75)).astype(int),
                "Distance": (dist - dist.mean()) / (dist.std() + 1e-10),
                "LogDensity": (ld - ld.mean()) / (ld.std() + 1e-10),
            })
        return X

    def _run_sem_on_subset(gdf_sub, use_t=True, use_poverty=False):
        if len(gdf_sub) < 20:
            return np.nan, np.nan, np.nan
        gdf_sub, w = _build_knn_weights(gdf_sub, args.project_crs)
        if len(gdf_sub) < 20:
            return np.nan, np.nan, np.nan
        X = _prepare_x(gdf_sub, use_t=use_t, use_poverty=use_poverty)
        x = X.values
        x_names = list(X.columns)
        y = gdf_sub["allocation_residual"].values.reshape(-1, 1)
        sem = run_sem(y, x, w, x_names)
        # First coefficient after constant (treatment or poverty)
        coef_idx = 1
        tau = _scalar(sem.betas[coef_idx])
        se = _scalar(sem.std_err[coef_idx])
        p = _scalar(sem.z_stat[coef_idx][1])
        return tau, se, p

    results = []

    # -------------------------------------------------------------------------
    # Section A — Baseline SEM (Reference)
    # -------------------------------------------------------------------------
    print("=" * 60)
    print("03f — Sensitivity Analyses")
    print("=" * 60)
    print("\n--- A. Baseline SEM (reference) ---")
    tau_a, se_a, p_a = _run_sem_on_subset(gdf_full, use_t=True, use_poverty=False)
    results.append({"Specification": "Baseline SEM", "τ": tau_a, "SE": se_a, "p": p_a})
    print(f"  τ = {tau_a:.4f}, SE = {se_a:.4f}, p = {p_a:.4f}")

    # -------------------------------------------------------------------------
    # Section B — Robustness 1: Continuous Poverty
    # -------------------------------------------------------------------------
    print("\n--- B. Continuous poverty (SEM) ---")
    tau_b, se_b, p_b = _run_sem_on_subset(gdf_full, use_t=False, use_poverty=True)
    results.append({"Specification": "Continuous poverty", "τ": tau_b, "SE": se_b, "p": p_b})
    print(f"  β_poverty = {tau_b:.4f}, SE = {se_b:.4f}, p = {p_b:.4f}")

    # -------------------------------------------------------------------------
    # Section C — Robustness 2: Top vs Bottom Quintile Only
    # -------------------------------------------------------------------------
    print("\n--- C. Top vs Bottom quintile only ---")
    mask_extremes = (poverty <= q1_pct) | (poverty >= q5_pct)
    gdf_extremes = gdf_full[mask_extremes].copy()
    # Redefine T: T=1 if poverty ≥ Q5 (top quintile), T=0 if poverty ≤ Q1 (bottom quintile)
    gdf_extremes["T_extreme"] = (gdf_extremes["poverty_mean"].values >= q5_pct).astype(int)
    gdf_extremes, w_c = _build_knn_weights(gdf_extremes, args.project_crs)
    # Override _prepare_x for this case: we need T_extreme, not quartile-based T
    X_c = pd.DataFrame({
        "T": gdf_extremes["T_extreme"].values,
        "Distance": (gdf_extremes["Distance"].values - gdf_extremes["Distance"].mean()) / (gdf_extremes["Distance"].std() + 1e-10),
        "LogDensity": (np.log(gdf_extremes["PopulationDensity"].values + 1) - np.log(gdf_extremes["PopulationDensity"].values + 1).mean()) / (np.log(gdf_extremes["PopulationDensity"].values + 1).std() + 1e-10),
    })
    x_c = X_c.values
    x_names_c = list(X_c.columns)
    y_c = gdf_extremes["allocation_residual"].values.reshape(-1, 1)
    sem_c = run_sem(y_c, x_c, w_c, x_names_c)
    tau_c = _scalar(sem_c.betas[1])
    se_c = _scalar(sem_c.std_err[1])
    p_c = _scalar(sem_c.z_stat[1][1])
    results.append({"Specification": "Top vs Bottom quintile", "τ": tau_c, "SE": se_c, "p": p_c})
    print(f"  N = {len(gdf_extremes)}, τ_extremes = {tau_c:.4f}, SE = {se_c:.4f}, p = {p_c:.4f}")

    # -------------------------------------------------------------------------
    # Section D — Robustness 3: Remove Top 5% Density Cells
    # -------------------------------------------------------------------------
    print("\n--- D. Remove top 5% density cells ---")
    ld_95 = np.nanpercentile(log_dens_full, 95)
    mask_dens = log_dens_full <= ld_95
    gdf_sub_d = gdf_full[mask_dens].copy()
    tau_d, se_d, p_d = _run_sem_on_subset(gdf_sub_d, use_t=True, use_poverty=False)
    results.append({"Specification": "Drop top 5% density", "τ": tau_d, "SE": se_d, "p": p_d})
    print(f"  N = {len(gdf_sub_d)}, τ = {tau_d:.4f}, SE = {se_d:.4f}, p = {p_d:.4f}")

    # -------------------------------------------------------------------------
    # Section E — Robustness 4: Remove Central 10%
    # -------------------------------------------------------------------------
    print("\n--- E. Remove central 10% ---")
    dist_10 = np.nanpercentile(dist_full, 10)
    mask_dist = dist_full >= dist_10
    gdf_sub_e = gdf_full[mask_dist].copy()
    tau_e, se_e, p_e = _run_sem_on_subset(gdf_sub_e, use_t=True, use_poverty=False)
    results.append({"Specification": "Drop central 10%", "τ": tau_e, "SE": se_e, "p": p_e})
    print(f"  N = {len(gdf_sub_e)}, τ = {tau_e:.4f}, SE = {se_e:.4f}, p = {p_e:.4f}")

    # -------------------------------------------------------------------------
    # Output Table: Specification | τ | SE | p (4 decimal places)
    # -------------------------------------------------------------------------
    tbl = pd.DataFrame(results)
    for col in ["τ", "SE", "p"]:
        tbl[col] = tbl[col].round(4)
    tbl.to_csv(out_dir / "Table_robustness_summary.csv", index=False)
    print("\n--- Sensitivity Summary (Specification | τ | SE | p) ---")
    print(tbl.to_string(index=False))
    print(f"\n  Saved: {out_dir / 'Table_robustness_summary.csv'}")
    print("=" * 60)


if __name__ == "__main__":
    main()
