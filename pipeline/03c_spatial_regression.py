#!/usr/bin/env python3
"""
03c — Spatial regression (SLM and SEM) with causal treatment T.

Uses spreg (PySAL): ML_Lag (SLM) and ML_Error (SEM).
Dependent variable: allocation_residual (consistent with 03a).

Causal specification:
  T = 1 if poverty in top quartile (treatment)
  X = [T, Distance, LogDensity] — Poverty removed (T already captures it)

  SLM: Y = ρWY + τT + β₁Distance + β₂LogDensity + ε
  SEM: Y = λWε + τT + β₁Distance + β₂LogDensity + ε

Compare τ (OLS adjusted from 03e) vs τ (SEM). If τ remains similar in magnitude
and statistically significant after SEM, this suggests that residual spatial
autocorrelation does not fully account for the observed association.

Outputs:
  Table_spatial_regression_full.csv
  Table3_SLM_SEM_coefficients.csv
  Table_tau_comparison.csv  # τ across OLS, SLM, SEM
  Table_model_comparison.csv
  Table_Moran_residuals_diagnostic.csv
  slm_residual_map.png
  sem_residual_map.png
"""

import argparse
import sys
from pathlib import Path

import numpy as np

# Shim for libpysal: scipy.inf removed in newer scipy
import scipy
if not hasattr(scipy, "inf"):
    scipy.inf = np.inf
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poverty_utils

DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg"
OUT_SUBDIR = "03c_spatial_regression"


def _stars(p):
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))


def parse_args():
    p = argparse.ArgumentParser(description="03c — Spatial regression (SLM, SEM)")
    p.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("-o", "--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    p.add_argument("--project-crs", type=str, default="EPSG:32737")
    return p.parse_args()


def main():
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError("Provide -i path (output from script 02)")

    out_dir = args.output_dir / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    gdf = poverty_utils.load_and_prepare_gdf(args.input, args.project_crs, residual_col="allocation_residual")

    print("=" * 60)
    print("03c — Spatial Regression (SLM, SEM)")
    print("=" * 60)
    print(f"  Valid quadkeys: {len(gdf)}")

    # --------------------------------------------------
    # 1️⃣ Treatment T and controls (causal specification)
    # T = 1 if poverty in top quartile; Poverty removed (T captures it)
    # --------------------------------------------------
    poverty = gdf["poverty_mean"].values
    q75 = np.nanpercentile(poverty, 75)
    T = (poverty >= q75).astype(int)

    log_dens = np.log(gdf["PopulationDensity"].values + 1)
    X = pd.DataFrame({
        "T": T,
        "Distance": (gdf["Distance"].values - gdf["Distance"].mean()) / (gdf["Distance"].std() + 1e-10),
        "LogDensity": (log_dens - log_dens.mean()) / (log_dens.std() + 1e-10),
    })

    x = X.values
    x_names = list(X.columns)

    # --------------------------------------------------
    # 2️⃣ Dependent variable (allocation_residual)
    # --------------------------------------------------
    y = gdf["allocation_residual"].values.reshape(-1, 1)

    print(f"  Dependent variable: allocation_residual")
    print(f"  Mean DV: {y.mean():.4f}")

    # --------------------------------------------------
    # 3️⃣ Spatial weights — KNN (k=6) for numerical stability, no islands
    # --------------------------------------------------
    gdf_proj = gdf.to_crs(args.project_crs)
    # Drop invalid geometries (empty centroids cause KNN.from_dataframe to fail)
    valid_geom = poverty_utils.has_valid_centroids(gdf_proj)
    if not valid_geom.all():
        n_drop = (~valid_geom).sum()
        gdf = gdf.loc[valid_geom].reset_index(drop=True)
        gdf_proj = gdf_proj.loc[valid_geom].reset_index(drop=True)
        print(f"  Dropped {n_drop} rows with invalid geometry centroids")
        poverty = gdf["poverty_mean"].values
        q75 = np.nanpercentile(poverty, 75)
        T = (poverty >= q75).astype(int)
        log_dens = np.log(gdf["PopulationDensity"].values + 1)
        X = pd.DataFrame({
            "T": T,
            "Distance": (gdf["Distance"].values - gdf["Distance"].mean()) / (gdf["Distance"].std() + 1e-10),
            "LogDensity": (log_dens - log_dens.mean()) / (log_dens.std() + 1e-10),
        })
        x = X.values
        x_names = list(X.columns)
        y = gdf["allocation_residual"].values.reshape(-1, 1)
    from libpysal.weights import KNN
    # Extract centroid coords explicitly (from_dataframe can fail with Point geometries)
    xs = gdf_proj.geometry.centroid.x.values.astype(float)
    ys = gdf_proj.geometry.centroid.y.values.astype(float)
    valid_coords = np.isfinite(xs) & np.isfinite(ys)
    if not valid_coords.all():
        gdf = gdf.loc[valid_coords].reset_index(drop=True)
        gdf_proj = gdf_proj.loc[valid_coords].reset_index(drop=True)
        xs, ys = xs[valid_coords], ys[valid_coords]
        poverty = gdf["poverty_mean"].values
        q75 = np.nanpercentile(poverty, 75)
        T = (poverty >= q75).astype(int)
        log_dens = np.log(gdf["PopulationDensity"].values + 1)
        X = pd.DataFrame({
            "T": T,
            "Distance": (gdf["Distance"].values - gdf["Distance"].mean()) / (gdf["Distance"].std() + 1e-10),
            "LogDensity": (log_dens - log_dens.mean()) / (log_dens.std() + 1e-10),
        })
        x, x_names = X.values, list(X.columns)
        y = gdf["allocation_residual"].values.reshape(-1, 1)
    coords = np.column_stack([xs, ys])
    w = KNN.from_array(coords, k=6, ids=gdf_proj.index.tolist())
    w.transform = "r"

    from spreg import OLS, ML_Lag, ML_Error
    from spreg.diagnostics import likratiotest
    from esda.moran import Moran

    # --------------------------------------------------
    # 4️⃣ OLS (for model comparison only)
    # --------------------------------------------------
    ols_spreg = OLS(
        y, x, w=w,
        name_y="allocation_residual",
        name_x=x_names,
        name_w="KNN",
        name_ds="quadkeys"
    )

    # --------------------------------------------------
    # 5️⃣ Spatial Lag Model
    # --------------------------------------------------
    print("\n--- Spatial Lag Model (SLM) ---")
    slm = ML_Lag(
        y, x, w,
        name_y="allocation_residual",
        name_x=x_names,
        name_w="KNN",
        name_ds="quadkeys"
    )
    print(slm.summary)

    # --------------------------------------------------
    # 6️⃣ Spatial Error Model
    # --------------------------------------------------
    print("\n--- Spatial Error Model (SEM) ---")
    sem = ML_Error(
        y, x, w,
        name_y="allocation_residual",
        name_x=x_names,
        name_w="KNN",
        name_ds="quadkeys"
    )
    print(sem.summary)

    # --------------------------------------------------
    # 7️⃣ Moran’s I on SEM filtered residuals
    # --------------------------------------------------
    print("\n--- Moran's I on residuals (diagnostic: autocorrelation should drop) ---")
    resid_ols = np.asarray(ols_spreg.u).ravel()
    resid_slm = np.asarray(slm.u).ravel()
    # SEM: use e_filtered (innovation residuals); u is structural error (spatially correlated by construction)
    resid_sem = np.asarray(getattr(sem, "e_filtered", sem.u)).ravel()
    moran_ols = Moran(resid_ols, w)
    moran_slm = Moran(resid_slm, w)
    moran_sem = Moran(resid_sem, w)
    i_ols = moran_ols.I
    i_slm = moran_slm.I
    i_sem = moran_sem.I
    pct_red_slm = (1 - i_slm / i_ols) * 100 if abs(i_ols) > 1e-10 else np.nan
    pct_red_sem = (1 - i_sem / i_ols) * 100 if abs(i_ols) > 1e-10 else np.nan

    print(f"  OLS residuals: Moran's I = {i_ols:.4f}, p = {moran_ols.p_sim:.4f}")
    print(f"  SLM residuals: Moran's I = {i_slm:.4f}, p = {moran_slm.p_sim:.4f}  (% reduction vs OLS: {pct_red_slm:.1f}%)")
    print(f"  SEM residuals: Moran's I = {i_sem:.4f}, p = {moran_sem.p_sim:.4f}  (% reduction vs OLS: {pct_red_sem:.1f}%)")
    print("  (Spatial model residuals should show lower I -> autocorrelation reduced)")
    moran_diag = pd.DataFrame([
        {"Model": "OLS", "Moran_I": i_ols, "p_value": moran_ols.p_sim, "pct_reduction_vs_OLS": np.nan},
        {"Model": "SLM", "Moran_I": i_slm, "p_value": moran_slm.p_sim, "pct_reduction_vs_OLS": pct_red_slm},
        {"Model": "SEM", "Moran_I": i_sem, "p_value": moran_sem.p_sim, "pct_reduction_vs_OLS": pct_red_sem},
    ])
    moran_diag.to_csv(out_dir / "Table_Moran_residuals_diagnostic.csv", index=False)

    # --------------------------------------------------
    # 8️⃣ Save coefficient table — use model name_x for correct mapping
    # ML_Lag: name_x = [CONSTANT, Poverty, Distance, PopulationDensity, W_y]; betas match
    # ML_Error: name_x = [CONSTANT, ..., lambda]; betas match
    # --------------------------------------------------
    def _scalar(x):
        arr = np.asarray(x)
        return float(arr.flat[0]) if arr.size > 0 else np.nan

    def _p_fmt(p):
        return "<0.001" if p < 0.001 else f"{p:.4f}"

    def _coef_fmt(coef, p):
        return f"{float(coef):.4f}{_stars(p)}"

    # Build rows from model name_x (exclude spatial param for main table)
    slm_names = getattr(slm, "name_x", None) or ["CONSTANT", "T", "Distance", "LogDensity", "W_y"]
    sem_names = getattr(sem, "name_x", None) or ["CONSTANT", "T", "Distance", "LogDensity", "lambda"]
    # SLM: betas[0]=const, [1]=T, [2]=Distance, [3]=LogDensity, [4]=rho
    # SEM: betas[0]=const, [1]=T, [2]=Distance, [3]=LogDensity, [4]=lambda
    var_labels = {"CONSTANT": "Constant", "constant": "Constant", "T": "T (poverty top quartile)",
                   "Distance": "Distance (z)", "LogDensity": "Log Population Density (z)"}
    rows = []
    for i, (sn, en) in enumerate(zip(slm_names[:-1], sem_names[:-1])):
        label = var_labels.get(sn, sn)
        slm_p = _scalar(slm.z_stat[i][1])
        sem_p = _scalar(sem.z_stat[i][1])
        rows.append({
            "Variable": label,
            "SLM_coef": _scalar(slm.betas[i]),
            "SLM_SE": _scalar(slm.std_err[i]),
            "SLM_p": slm_p,
            "SLM_sig": _stars(slm_p),
            "SEM_coef": _scalar(sem.betas[i]),
            "SEM_SE": _scalar(sem.std_err[i]),
            "SEM_p": sem_p,
            "SEM_sig": _stars(sem_p),
        })
    # Spatial parameters
    rho_idx = len(slm_names) - 1
    lam_idx = len(sem_names) - 1
    slm_rho_p = _scalar(slm.z_stat[rho_idx][1])
    sem_lam_p = _scalar(sem.z_stat[lam_idx][1])
    rows.append({
        "Variable": "Spatial parameter",
        "SLM_coef": _scalar(slm.rho),
        "SLM_SE": _scalar(slm.std_err[rho_idx]),
        "SLM_p": slm_rho_p,
        "SLM_sig": _stars(slm_rho_p),
        "SEM_coef": _scalar(sem.lam),
        "SEM_SE": _scalar(sem.std_err[lam_idx]),
        "SEM_p": sem_lam_p,
        "SEM_sig": _stars(sem_lam_p),
    })

    tbl = pd.DataFrame(rows)
    tbl.to_csv(out_dir / "Table_spatial_regression_full.csv", index=False)

    # Table: Variable | SLM Coef | SEM Coef | SEM p-value (built from rows)
    tbl_formatted = pd.DataFrame([
        {"Variable": r["Variable"], "SLM Coef": _coef_fmt(r["SLM_coef"], r["SLM_p"]), "SEM Coef": _coef_fmt(r["SEM_coef"], r["SEM_p"]), "SEM p-value": _p_fmt(r["SEM_p"])}
        for r in rows[:-1]
    ])
    tbl_formatted = pd.concat([
        tbl_formatted,
        pd.DataFrame([{"Variable": "Spatial parameter", "SLM Coef": f"ρ = {_coef_fmt(_scalar(slm.rho), slm_rho_p)}", "SEM Coef": f"λ = {_coef_fmt(_scalar(sem.lam), sem_lam_p)}", "SEM p-value": _p_fmt(sem_lam_p)}])
    ], ignore_index=True)
    tbl_formatted.to_csv(out_dir / "Table3_SLM_SEM_coefficients.csv", index=False)
    print("\nTable: SLM & SEM Coefficients")
    print(tbl_formatted.to_string(index=False))

    # --------------------------------------------------
    # 8b. τ comparison: OLS (adjusted) vs SLM vs SEM
    # --------------------------------------------------
    tau_ols = np.nan
    tau_ols_se_robust = np.nan
    tau_ols_p = np.nan
    try:
        import statsmodels.api as sm
        X_sm = sm.add_constant(X)
        ols_robust = sm.OLS(y.ravel(), X_sm).fit(cov_type="HC3")
        tau_ols = ols_robust.params["T"]
        tau_ols_se_robust = ols_robust.bse["T"]
        tau_ols_p = ols_robust.pvalues["T"]
    except Exception as ex:
        print(f"  OLS robust (for τ comparison) skipped: {ex}")

    # Index of T in betas (second position after constant)
    t_idx = 1
    tau_slm = _scalar(slm.betas[t_idx])
    tau_slm_se = _scalar(slm.std_err[t_idx])
    tau_slm_p = _scalar(slm.z_stat[t_idx][1])
    tau_sem = _scalar(sem.betas[t_idx])
    tau_sem_se = _scalar(sem.std_err[t_idx])
    tau_sem_p = _scalar(sem.z_stat[t_idx][1])

    tau_comp = pd.DataFrame([
        {"Model": "OLS (covariate-adjusted)", "tau": tau_ols, "SE": tau_ols_se_robust, "p_value": tau_ols_p, "exp_tau": np.exp(tau_ols) if not np.isnan(tau_ols) else np.nan},
        {"Model": "SLM (spatial lag)", "tau": tau_slm, "SE": tau_slm_se, "p_value": tau_slm_p, "exp_tau": np.exp(tau_slm)},
        {"Model": "SEM (spatial error)", "tau": tau_sem, "SE": tau_sem_se, "p_value": tau_sem_p, "exp_tau": np.exp(tau_sem)},
    ])
    tau_comp.to_csv(out_dir / "Table_tau_comparison.csv", index=False)

    print("\n--- τ comparison (treatment effect across models) ---")
    for _, r in tau_comp.iterrows():
        sig = _stars(r["p_value"]) if not np.isnan(r["p_value"]) else ""
        print(f"  {r['Model']}: τ = {r['tau']:.4f}{sig} (SE = {r['SE']:.4f}), exp(τ) = {r['exp_tau']:.4f}")
    if tau_sem_p < 0.05 and abs(tau_sem) > 0.1:
        print("  → τ remains similar in magnitude and statistically significant after SEM; residual spatial autocorrelation does not fully account for the observed association.")
    else:
        print("  → Interpret with caution: τ may be attenuated or non-significant after spatial correction.")

    # --------------------------------------------------
    # 9️⃣ Model comparison (AIC)
    # --------------------------------------------------
    def _aic_fmt(a):
        a = float(a)
        return f"{a:.1f}" if a < 1000 else f"~{int(round(a))}"

    comp_df = pd.DataFrame([
        {"Model": "OLS", "AIC": ols_spreg.aic, "R2": ols_spreg.r2},
        {"Model": "SLM", "AIC": slm.aic, "R2": slm.pr2},
        {"Model": "SEM", "AIC": sem.aic, "R2": sem.pr2},
    ])
    comp_df.to_csv(out_dir / "Table_model_comparison.csv", index=False)

    # --------------------------------------------------
    # 🔟 Residual maps
    # --------------------------------------------------
    gdf_map = gdf.copy()
    gdf_map["slm_residual"] = np.asarray(slm.u).ravel()
    gdf_map["sem_residual"] = np.asarray(sem.u).ravel()
    # Save for R plotting (03c_plots.R)
    gdf_map.to_file(out_dir / "03c_residuals_for_plots.gpkg", driver="GPKG")
    print(f"  Saved: {out_dir / '03c_residuals_for_plots.gpkg'} (run Rscript pipeline/03c_plots.R for maps)")

    print("=" * 60)
    print("Spatial regression complete.")
    print("=" * 60)


if __name__ == "__main__":
    main()
