#!/usr/bin/env python3
"""
03f — Sensitivity analyses for spatial error specification.

Loads harmonised_with_residual.gpkg, recreates treatment definition,
re-runs SEM under various filters. Outputs a summary table for reviewers.

Sections:
  03f-A (A–E). Existing model/specification robustness:
    A. Baseline SEM: Y ~ T + Distance + LogDensity (reference τ)
    B. Continuous poverty: Y ~ poverty_mean + Distance + LogDensity (β_poverty)
    C. Top vs Bottom quintile only: filter to extremes, redefine T, SEM
    D. Remove top 5% density cells: LogDensity ≤ 95th percentile
    E. Remove central 10%: Distance ≥ 10th percentile
  03f-B (F). Observed Meta count ≥20/30/50 sensitivity:
     hold R = allocation_residual and T = 1(D ≥ Q75_full) fixed, then
     drop cells with meta_baseline below 20 / 30 / 50 before refitting SEM.
     Does not re-run 01 --filter-by meta (that would change the analysis universe).
  03f-C (G). Low-count composition diagnostic: which cells drive F's attenuation.
     Groups <20 / 20–29 / 30–49 / ≥50 with frozen T; table + cell-level plot.
  03f-D (H). Missing-cell privacy-censoring sensitivity:
     independent zoom-level city grid (not Meta-defined). WorldPop>0 cells with
     unpublished Meta are imputed in turn as 1 / 5 / 9.9; Meta shares and
     R = log(meta_share / worldpop_share) are rebuilt; same SEM is refit.
     No extra WorldPop-size filter. Cities only (needs the step-01 clip).

Usage:
  conda activate geo_env_LLM
  python pipeline/03f_robustness.py --region ZAF_CapeTown

Outputs:
  outputs/{REGION}/03f_robustness/Table_robustness_summary.csv
  outputs/{REGION}/03f_robustness/Table_meta_count_sensitivity.csv
  outputs/{REGION}/03f_robustness/Table_meta_count_composition.csv
  outputs/{REGION}/03f_robustness/meta_count_cells.csv
  outputs/{REGION}/03f_robustness/Table_meta_count_censoring_sensitivity.csv
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
import region_config
import independent_grid

DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg"
OUT_SUBDIR = "03f_robustness"


def _scalar(x):
    arr = np.asarray(x)
    return float(arr.flat[0]) if arr.size > 0 else np.nan


def _build_knn_weights(gdf, project_crs, k=6):
    """Build KNN weights (k=6) for numerical stability, no islands. Returns (gdf, w)."""
    from libpysal.weights import KNN
    gdf_proj = gdf.to_crs(poverty_utils.utm_crs_for(gdf))
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


class _SemFit:
    """Minimal spreg-like result: betas, std_err, z_stat with constant at index 0."""

    def __init__(self, betas, std_err):
        from scipy.stats import norm
        self.betas = np.asarray(betas).reshape(-1, 1)
        self.std_err = np.asarray(std_err).reshape(-1)
        z = self.betas.ravel() / np.where(self.std_err == 0, np.nan, self.std_err)
        p = 2.0 * norm.sf(np.abs(z))
        self.z_stat = list(zip(z, p))


def _ml_error_large_n(y, x, w):
    """
    ML SEM for large n.

    spreg.ML_Error inverts (I − λW) (n × n) only to get Var(λ). That step hung
    on the IDN/PHL/MEX footprints. β and λ are block-diagonal in the SEM
    information matrix, so τ SEs are sig² (X*'X*)⁻¹ after the GLS transform
    and do not need that inverse.
    """
    from scipy.optimize import minimize_scalar
    from scipy.sparse import identity
    from libpysal import weights as lpweights
    from spreg.ml_error import err_c_loglik_sp
    from spreg import user_output as USER

    y = np.asarray(y, dtype=float).reshape(-1, 1)
    x_constant, _, _ = USER.check_constant(np.asarray(x, dtype=float), None)
    n = y.shape[0]
    ylag = lpweights.lag_spatial(w, y)
    xlag = lpweights.lag_spatial(w, x_constant)
    I = identity(w.n, format="csr")
    Wsp = w.sparse
    res = minimize_scalar(
        err_c_loglik_sp,
        0.0,
        bounds=(-1.0, 1.0),
        args=(n, y, ylag, x_constant, xlag, I, Wsp),
        method="bounded",
        tol=1e-7,
    )
    lam = float(np.asarray(res.x).reshape(-1)[0])
    ys = y - lam * ylag
    xs = x_constant - lam * xlag
    xsxsi = np.linalg.inv(xs.T @ xs)
    b = xsxsi @ (xs.T @ ys)
    u = y - x_constant @ b
    e_filtered = u - lam * lpweights.lag_spatial(w, u)
    sig2 = float((e_filtered.T @ e_filtered).item() / n)
    se_beta = np.sqrt(np.maximum(np.diag(sig2 * xsxsi), 0.0))
    betas = np.vstack([b, np.array([[lam]])])
    std_err = np.append(se_beta, np.nan)
    return _SemFit(betas, std_err)


def run_sem(y, x, w, x_names):
    """Run ML SEM. Large n skips spreg's n×n (I−λW) inverse (Var(λ) only)."""
    from spreg import ML_Error
    n = len(y)
    if n >= 12000:
        print(f"    SEM method=LU-GLS (n={n}; skip n×n inverse)", flush=True)
        return _ml_error_large_n(y, x, w)
    method = "LU" if n >= 1500 else "full"
    if method == "LU":
        print(f"    SEM method=LU (n={n})", flush=True)
    return ML_Error(
        y, x, w, name_y="Y", name_x=x_names, name_w="KNN", name_ds="quadkeys", method=method
    )


Z_CRIT = 1.96  # 95% CI
META_COUNT_CUTOFFS = (20, 30, 50)
META_COUNT_BINS = [-np.inf, 20, 30, 50, np.inf]
META_COUNT_LABELS = ["<20", "20–29", "30–49", "≥50"]
# Fixed privacy-floor scenarios (not a draw from 0–10). 9.9 is just below Meta's ~10 floor.
CENSOR_SCENARIOS = (
    ("Low censored", "1", 1.0),
    ("Mid censored", "5", 5.0),
    ("Max censored", "9.9", 9.9),
)


def _add_distance_density(gdf):
    """Distance to sample centroid and WorldPop density (same as load_and_prepare_gdf)."""
    from shapely.geometry import Point

    gdf = gdf.copy()
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    project_crs = poverty_utils.utm_crs_for(gdf)
    gdf_proj = gdf.to_crs(project_crs)
    valid_geom = poverty_utils.has_valid_centroids(gdf_proj)
    if not valid_geom.all():
        gdf = gdf.loc[valid_geom].reset_index(drop=True)
        gdf_proj = gdf_proj.loc[valid_geom].reset_index(drop=True)
    centroids = gdf_proj.geometry.centroid
    centroid_study = Point(centroids.x.mean(), centroids.y.mean())
    gdf["Distance"] = gdf_proj.geometry.centroid.distance(centroid_study)
    gdf["area_km2"] = gdf_proj.geometry.area / 1e6
    gdf["PopulationDensity"] = gdf["worldpop_count"] / gdf["area_km2"].clip(lower=1e-6)
    return gdf


def _sem_eligible_censoring(grid):
    """WorldPop>0 and poverty-valid cells on the independent grid. No Meta requirement."""
    g = grid.copy()
    if "meta_missing" in g.columns:
        g["meta_missing"] = independent_grid._as_bool(g["meta_missing"])
    wp = pd.to_numeric(g["worldpop_count"], errors="coerce")
    g = g.loc[wp > 0].copy()
    n_wp = len(g)
    n_missing_wp = int(g["meta_missing"].sum()) if "meta_missing" in g.columns else 0
    g = g.loc[independent_grid.is_eligible(g)].copy().reset_index(drop=True)
    n_imputed = int(g["meta_missing"].sum()) if "meta_missing" in g.columns else 0
    return g, n_wp, n_missing_wp, n_imputed


def _sem_tau_row(sem, n, n_full, min_meta_label):
    """Extract τ, SE, 95% CI, exp(τ), p for the treatment coefficient (index 1)."""
    tau = _scalar(sem.betas[1])
    se = _scalar(sem.std_err[1])
    p = _scalar(sem.z_stat[1][1])
    finite = np.isfinite(tau) and np.isfinite(se)
    return {
        "min_meta": min_meta_label,
        "N": int(n),
        "retained_pct": round(100.0 * n / n_full, 2) if n_full else np.nan,
        "tau": tau,
        "se": se,
        "CI_low": tau - Z_CRIT * se if finite else np.nan,
        "CI_high": tau + Z_CRIT * se if finite else np.nan,
        "exp_tau": float(np.exp(tau)) if np.isfinite(tau) else np.nan,
        "p": p,
    }


def parse_args():
    p = argparse.ArgumentParser(description="03f — Sensitivity analyses for spatial error specification")
    p.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("-o", "--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    p.add_argument("--region", type=str, default=None)
    region_config.add_footprint_arg(p)
    p.add_argument("--project-crs", type=str, default="EPSG:32737")
    return p.parse_args()


def main():
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError(f"Missing input: {args.input}. Run step 02 first.")

    out_dir = region_config.resolve_step_paths(
        args.region, OUT_SUBDIR, args.output_dir, args.input,
        footprint=getattr(args, "footprint", None),
    )

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

    def _run_sem_fixed_t(gdf_sub):
        """SEM with frozen T (full-sample Q75). Rebuilds W; z-scores controls in-sample."""
        if len(gdf_sub) < 20:
            return None
        gdf_sub, w = _build_knn_weights(gdf_sub, args.project_crs)
        if len(gdf_sub) < 20:
            return None
        t = gdf_sub["T_fixed"].values
        if np.unique(t).size < 2:
            print("    warning: T_fixed has no variation in this subset; skipping SEM")
            return None
        dist = gdf_sub["Distance"].values
        ld = np.log(gdf_sub["PopulationDensity"].values + 1)
        X = pd.DataFrame({
            "T": t,
            "Distance": (dist - dist.mean()) / (dist.std() + 1e-10),
            "LogDensity": (ld - ld.mean()) / (ld.std() + 1e-10),
        })
        y = gdf_sub["allocation_residual"].values.reshape(-1, 1)
        sem = run_sem(y, X.values, w, list(X.columns))
        return sem, len(gdf_sub)

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
    # Section F — Meta low-count / disclosure-threshold sensitivity
    # Hold R (allocation_residual) and T = 1(poverty ≥ Q75_full) fixed.
    # Filter meta_baseline immediately before fitting; rebuild W on remaining cells.
    # -------------------------------------------------------------------------
    print("\n--- F. Meta low-count / disclosure-threshold sensitivity ---")
    if "meta_baseline" not in gdf_full.columns:
        raise ValueError(
            "Input must include meta_baseline (Step 02 GPKG). "
            "Do not re-harmonise with 01 --filter-by meta for this experiment."
        )
    n_full = len(gdf_full)
    gdf_full = gdf_full.copy()
    gdf_full["T_fixed"] = (gdf_full["poverty_mean"].values >= q75).astype(int)
    n_treated = int(gdf_full["T_fixed"].sum())
    print(
        f"  Frozen T: poverty_mean Q75 = {q75:.4f} on full analysis sample "
        f"(N = {n_full}, treated = {n_treated})"
    )
    print("  Outcome R = allocation_residual (Step 02); W rebuilt after each filter")

    meta_rows = []
    specs_f = [("baseline", None)] + [(str(c), c) for c in META_COUNT_CUTOFFS]
    for label, min_meta in specs_f:
        if min_meta is None:
            g = gdf_full.copy()
        else:
            g = gdf_full[gdf_full["meta_baseline"] >= min_meta].copy()
        print(f"  min_meta = {label}: N_filter = {len(g)} / {n_full}")
        fitted = _run_sem_fixed_t(g)
        if fitted is None:
            meta_rows.append({
                "min_meta": label,
                "N": len(g),
                "retained_pct": round(100.0 * len(g) / n_full, 2) if n_full else np.nan,
                "tau": np.nan,
                "se": np.nan,
                "CI_low": np.nan,
                "CI_high": np.nan,
                "exp_tau": np.nan,
                "p": np.nan,
            })
            continue
        sem_f, n_f = fitted
        row_f = _sem_tau_row(sem_f, n_f, n_full, label)
        meta_rows.append(row_f)
        print(
            f"    N = {row_f['N']} ({row_f['retained_pct']:.1f}% retained), "
            f"τ = {row_f['tau']:.4f}, SE = {row_f['se']:.4f}, "
            f"CI95 = [{row_f['CI_low']:.4f}, {row_f['CI_high']:.4f}], "
            f"exp(τ) = {row_f['exp_tau']:.4f}, p = {row_f['p']:.4g}"
        )

    tbl_meta = pd.DataFrame(meta_rows)
    tbl_meta.to_csv(out_dir / "Table_meta_count_sensitivity.csv", index=False)
    print("\n--- Meta count sensitivity (min_meta | N | retained_pct | τ | SE | CI | exp(τ) | p) ---")
    print(tbl_meta.to_string(index=False))
    print(f"  Saved: {out_dir / 'Table_meta_count_sensitivity.csv'}")

    # -------------------------------------------------------------------------
    # Section G — Meta-count composition diagnostic
    # Same sample, same frozen T, same R. Do not refit SEM.
    # -------------------------------------------------------------------------
    print("\n--- G. Meta-count composition diagnostic ---")
    gdf_full["meta_count_group"] = pd.cut(
        gdf_full["meta_baseline"],
        bins=META_COUNT_BINS,
        labels=META_COUNT_LABELS,
        right=False,
    )
    comp_rows = []
    for lab in META_COUNT_LABELS:
        sub = gdf_full.loc[gdf_full["meta_count_group"] == lab]
        n = int(len(sub))
        if n == 0:
            comp_rows.append({
                "meta_count_group": lab,
                "n": 0,
                "median_meta": np.nan,
                "median_worldpop": np.nan,
                "median_grdi": np.nan,
                "pct_high_deprivation": np.nan,
                "median_allocation_residual": np.nan,
                "median_density": np.nan,
                "median_distance": np.nan,
            })
            continue
        comp_rows.append({
            "meta_count_group": lab,
            "n": n,
            "median_meta": float(sub["meta_baseline"].median()),
            "median_worldpop": float(sub["worldpop_count"].median()),
            "median_grdi": float(sub["poverty_mean"].median()),
            "pct_high_deprivation": float(100.0 * sub["T_fixed"].mean()),
            "median_allocation_residual": float(sub["allocation_residual"].median()),
            "median_density": float(sub["PopulationDensity"].median()),
            "median_distance": float(sub["Distance"].median()),
        })
        r = comp_rows[-1]
        print(
            f"  {lab:>6}: N={n:4d}, median GRDI={r['median_grdi']:.2f}, "
            f"high depr={r['pct_high_deprivation']:.1f}%, "
            f"median R={r['median_allocation_residual']:.3f}, "
            f"median WP={r['median_worldpop']:.1f}"
        )

    tbl_comp = pd.DataFrame(comp_rows)
    tbl_comp.to_csv(out_dir / "Table_meta_count_composition.csv", index=False)
    print("\n--- Meta count composition ---")
    print(tbl_comp.to_string(index=False))
    print(f"  Saved: {out_dir / 'Table_meta_count_composition.csv'}")

    cells = pd.DataFrame({
        "meta_baseline": gdf_full["meta_baseline"].to_numpy(),
        "allocation_residual": gdf_full["allocation_residual"].to_numpy(),
        "high_deprivation": gdf_full["T_fixed"].to_numpy(),
        "meta_count_group": gdf_full["meta_count_group"].astype(str).to_numpy(),
    })
    cells.to_csv(out_dir / "meta_count_cells.csv", index=False)
    print(f"  Saved: {out_dir / 'meta_count_cells.csv'}")

    # -------------------------------------------------------------------------
    # Section H — 03f-D: missing-cell privacy-censoring sensitivity
    # Independent city grid (clip tiles, not Meta). Cells with WorldPop>0 and
    # unpublished Meta are filled at 1 / 5 / 9.9; shares and R are rebuilt;
    # same SEM. T frozen at original analysis-sample Q75 so treatment is not
    # redefined by the extra cells. No extra WorldPop-size filter.
    # -------------------------------------------------------------------------
    print("\n--- H. Missing-cell privacy-censoring sensitivity (03f-D) ---")

    def _censor_row(scenario, assumption, n, n_imputed, tau, se, p):
        finite = np.isfinite(tau) and np.isfinite(se)
        return {
            "scenario": scenario,
            "assumption": assumption,
            "N": int(n) if n is not None and np.isfinite(n) else np.nan,
            "n_imputed": int(n_imputed) if n_imputed is not None and np.isfinite(n_imputed) else 0,
            "tau": tau,
            "se": se,
            "CI_low": tau - Z_CRIT * se if finite else np.nan,
            "CI_high": tau + Z_CRIT * se if finite else np.nan,
            "exp_tau": float(np.exp(tau)) if np.isfinite(tau) else np.nan,
            "p": p,
        }

    censor_rows = [
        _censor_row("Original", "missing excluded", n_full, 0, tau_a, se_a, p_a)
    ]
    paths_c = independent_grid.resolve_city_grid_inputs(
        region=args.region,
        input_path=args.input,
        footprint=getattr(args, "footprint", None),
    )
    if paths_c is None:
        print("  Skipping 03f-D (needs a city clip; not run on footprints)")
    else:
        try:
            grid = independent_grid.load_or_build_independent_grid(paths_c)
            g_sem, n_wp, n_missing_wp, n_imputed = _sem_eligible_censoring(grid)
            print(
                f"  WP>0 on independent grid: {n_wp} "
                f"(unpublished Meta among them: {n_missing_wp})"
            )
            print(
                f"  SEM-eligible (WP>0 and poverty valid): {len(g_sem)} "
                f"(imputed Meta cells: {n_imputed})"
            )
            print("  Frozen T: original analysis-sample poverty Q75; W rebuilt; shares rebuilt")
            if n_imputed:
                sub_m = g_sem.loc[g_sem["meta_missing"]]
                pct_t = 100.0 * (sub_m["poverty_mean"].to_numpy() >= q75).mean()
                print(
                    f"  Imputed cells: median WP={float(sub_m['worldpop_count'].median()):.1f}, "
                    f"median GRDI={float(sub_m['poverty_mean'].median()):.2f}, "
                    f"high depr (frozen Q75)={pct_t:.1f}%"
                )
            g_sem = _add_distance_density(g_sem)
            g_sem["T_fixed"] = (g_sem["poverty_mean"].to_numpy() >= q75).astype(int)
            missing_mask = (
                g_sem["meta_missing"].to_numpy()
                | g_sem["meta_baseline"].isna().to_numpy()
                | (pd.to_numeric(g_sem["meta_baseline"], errors="coerce").fillna(0).to_numpy() <= 0)
            )
            n_imputed_sem = int(missing_mask.sum())
            wp_arr = pd.to_numeric(g_sem["worldpop_count"], errors="coerce").to_numpy(dtype=float)
            meta_obs = pd.to_numeric(g_sem["meta_baseline"], errors="coerce").to_numpy(dtype=float)
            for label, assumption, fill in CENSOR_SCENARIOS:
                g = g_sem.copy()
                meta = np.where(missing_mask, float(fill), meta_obs)
                ok = np.isfinite(meta) & (meta > 0) & np.isfinite(wp_arr) & (wp_arr > 0)
                if not ok.all():
                    g = g.loc[ok].copy()
                    meta_use = meta[ok]
                    wp_use = wp_arr[ok]
                    n_imp = int(missing_mask[ok].sum())
                else:
                    meta_use = meta
                    wp_use = wp_arr
                    n_imp = n_imputed_sem
                meta_share = meta_use / meta_use.sum()
                wp_share = wp_use / wp_use.sum()
                g["allocation_residual"] = np.log(meta_share / wp_share)
                print(f"  {label}: Meta={assumption} on {n_imp} unpublished cells; N={len(g)}")
                fitted = _run_sem_fixed_t(g)
                if fitted is None:
                    censor_rows.append(
                        _censor_row(label, assumption, len(g), n_imp, np.nan, np.nan, np.nan)
                    )
                    continue
                sem_h, n_h = fitted
                tau_h = _scalar(sem_h.betas[1])
                se_h = _scalar(sem_h.std_err[1])
                p_h = _scalar(sem_h.z_stat[1][1])
                row = _censor_row(label, assumption, n_h, n_imp, tau_h, se_h, p_h)
                censor_rows.append(row)
                print(
                    f"    N = {row['N']}, τ = {row['tau']:.4f}, SE = {row['se']:.4f}, "
                    f"CI95 = [{row['CI_low']:.4f}, {row['CI_high']:.4f}], "
                    f"exp(τ) = {row['exp_tau']:.4f}, p = {row['p']:.4g}"
                )
        except Exception as e:
            print(f"  03f-D failed: {e}")
            import traceback
            traceback.print_exc()

    tbl_censor = pd.DataFrame(censor_rows)
    tbl_censor.to_csv(out_dir / "Table_meta_count_censoring_sensitivity.csv", index=False)
    print("\n--- Missing-cell privacy-censoring sensitivity ---")
    print(tbl_censor.to_string(index=False))
    print(f"  Saved: {out_dir / 'Table_meta_count_censoring_sensitivity.csv'}")

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
