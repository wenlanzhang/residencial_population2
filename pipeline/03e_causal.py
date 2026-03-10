#!/usr/bin/env python3
"""
03e — Causal setup: Treatment, Outcome, Controls, Estimand + Three Estimators.

Defines the causal framework for estimating the effect of high poverty on
allocation residual (Meta vs WorldPop discrepancy).

Treatment:     T_i = 1 if poverty in top quartile
Outcome:       Y_i = allocation_residual
Controls:      Distance, Log population density
Target estimand (under conditional ignorability): τ = E[Y(1) - Y(0)]
  Interpretation relies on the assumption that conditional on controls
  (Distance, LogDensity), treatment assignment is unconfounded.

Three estimators under different modeling strategies:
  1. Covariate-adjusted regression: Y = α + τT + Xβ + ε  → τ, robust SE, exp(τ)
  2. Inverse Probability Weighting (IPW): propensity P(T=1|X), weighted ATE
  3. Doubly Robust / Double ML: residualize Y and T on X, regress Y_resid on T_resid

Usage:
  conda activate geo_env_LLM   # or ensure statsmodels is installed
  python scripts/03e_causal.py -i outputs/02/harmonised_with_residual.gpkg

Outputs: 03e_causal_definitions.csv, 03e_treatment_summary.csv, 03e_estimators.csv
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poverty_utils

DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg"
OUT_SUBDIR = "03e_causal"


def parse_args():
    p = argparse.ArgumentParser(description="03e — Causal setup: Treatment, Outcome, Controls, Estimand")
    p.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT, help="02_harmonised_with_residual.gpkg")
    p.add_argument("-o", "--output-dir", type=Path, default=PROJECT_ROOT / "outputs", help="outputs root")
    p.add_argument("--project-crs", type=str, default="EPSG:32737", help="CRS for distances")
    return p.parse_args()


def main():
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Missing input: {args.input}. Run step 02 first.")

    out_dir = args.output_dir / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    gdf = poverty_utils.load_and_prepare_gdf(
        args.input, args.project_crs, residual_col="allocation_residual"
    )

    # -------------------------------------------------------------------------
    # Treatment: T_i = 1 if poverty in top quartile
    # -------------------------------------------------------------------------
    poverty = gdf["poverty_mean"].values
    q75 = np.nanpercentile(poverty, 75)
    T = (poverty >= q75).astype(int)

    # -------------------------------------------------------------------------
    # Outcome: Y_i = allocation_residual
    # -------------------------------------------------------------------------
    Y = gdf["allocation_residual"].values

    # -------------------------------------------------------------------------
    # Controls: Distance, Log population density
    # -------------------------------------------------------------------------
    Distance = gdf["Distance"].values
    log_pop_density = np.log(gdf["PopulationDensity"].values + 1.0)

    # -------------------------------------------------------------------------
    # Target estimand (under conditional ignorability): τ = E[Y(1) - Y(0)]
    # Interpretation relies on the assumption that conditional on controls
    # (Distance, LogDensity), treatment assignment is unconfounded.
    # -------------------------------------------------------------------------
    # Naive difference-in-means (unadjusted)
    Y1 = Y[T == 1]
    Y0 = Y[T == 0]
    tau_naive = np.nanmean(Y1) - np.nanmean(Y0)

    # Design matrix X (controls)
    X_df = pd.DataFrame({
        "Distance": (Distance - np.nanmean(Distance)) / (np.nanstd(Distance) + 1e-10),
        "log_pop_density": (log_pop_density - np.nanmean(log_pop_density)) / (np.nanstd(log_pop_density) + 1e-10),
    })

    # -------------------------------------------------------------------------
    # 1️⃣ Covariate-adjusted regression: Y = α + τT + Xβ + ε
    # -------------------------------------------------------------------------
    tau_reg, se_reg_robust, exp_tau_reg = np.nan, np.nan, np.nan
    try:
        import statsmodels.api as sm
        X_full = sm.add_constant(pd.DataFrame({"T": T}).join(X_df))
        ols = sm.OLS(Y, X_full).fit()
        ols_robust = sm.OLS(Y, X_full).fit(cov_type="HC3")
        tau_reg = ols.params["T"]
        se_reg_robust = ols_robust.bse["T"]
        exp_tau_reg = np.exp(tau_reg)
    except ImportError:
        pass

    # -------------------------------------------------------------------------
    # 2️⃣ Inverse Probability Weighting (IPW)
    # -------------------------------------------------------------------------
    tau_ipw, se_ipw = np.nan, np.nan
    try:
        import statsmodels.api as sm
        X_ps = sm.add_constant(X_df)
        logit = sm.Logit(T, X_ps).fit(disp=0)
        e = logit.predict(X_ps)
        e = np.clip(e, 0.01, 0.99)  # overlap
        print(f"  Propensity score range: {e.min():.3f} – {e.max():.3f}")
        psi = T * Y / e - (1 - T) * Y / (1 - e)
        tau_ipw = np.nanmean(psi)
        n = len(Y)
        se_ipw = np.sqrt(np.nanvar(psi) / n) if n > 1 else np.nan
    except Exception as ex:
        print(f"  IPW warning: {ex}")

    # -------------------------------------------------------------------------
    # 3️⃣ Doubly Robust / Double ML: residualize Y and T on X, regress Y_resid on T_resid
    # -------------------------------------------------------------------------
    tau_dml, se_dml = np.nan, np.nan
    try:
        import statsmodels.api as sm
        X_sm = sm.add_constant(X_df)
        # Y_resid = Y - E[Y|X]
        m_y = sm.OLS(Y, X_sm).fit()
        Y_resid = Y - m_y.predict(X_sm)
        # T_resid = T - E[T|X] (propensity)
        logit = sm.Logit(T, X_sm).fit(disp=0)
        e = logit.predict(X_sm)
        T_resid = T - e
        # Regress Y_resid on T_resid (no constant)
        dml = sm.OLS(Y_resid, T_resid).fit()
        dml_robust = sm.OLS(Y_resid, T_resid).fit(cov_type="HC3")
        tau_dml = dml.params.iloc[0]
        se_dml = dml_robust.bse.iloc[0]
    except Exception as ex:
        print(f"  Double ML warning: {ex}")

    # -------------------------------------------------------------------------
    # Save estimators table
    # -------------------------------------------------------------------------
    estimators_df = pd.DataFrame([
        {"Estimator": "Naive (diff-in-means)", "tau": tau_naive, "se_robust": np.nan, "exp_tau": np.exp(tau_naive)},
        {"Estimator": "1. Covariate-adjusted regression", "tau": tau_reg, "se_robust": se_reg_robust, "exp_tau": exp_tau_reg},
        {"Estimator": "2. IPW", "tau": tau_ipw, "se_robust": se_ipw, "exp_tau": np.exp(tau_ipw) if not np.isnan(tau_ipw) else np.nan},
        {"Estimator": "3. Doubly Robust (Double ML)", "tau": tau_dml, "se_robust": se_dml, "exp_tau": np.exp(tau_dml) if not np.isnan(tau_dml) else np.nan},
    ])
    estimators_df.to_csv(out_dir / "03e_estimators.csv", index=False)

    # -------------------------------------------------------------------------
    # Save definitions
    # -------------------------------------------------------------------------
    definitions = pd.DataFrame([
        {"Component": "Treatment", "Definition": "T_i = 1 if poverty in top quartile", "Variable": "poverty_mean >= 75th percentile"},
        {"Component": "Outcome", "Definition": "Y_i = allocation_residual", "Variable": "log(meta_share / worldpop_share)"},
        {"Component": "Control_1", "Definition": "Distance to study centroid", "Variable": "Distance"},
        {"Component": "Control_2", "Definition": "Log population density", "Variable": "log(PopulationDensity + 1)"},
        {"Component": "Estimand", "Definition": "Target estimand (under conditional ignorability): τ = E[Y(1) - Y(0)]", "Variable": "ATE; interpretation assumes unconfoundedness given controls"},
    ])
    definitions.to_csv(out_dir / "03e_causal_definitions.csv", index=False)

    # -------------------------------------------------------------------------
    # Treatment summary
    # -------------------------------------------------------------------------
    summary = pd.DataFrame([
        {"Statistic": "N total", "Value": len(gdf)},
        {"Statistic": "N treated (T=1)", "Value": int(T.sum())},
        {"Statistic": "N control (T=0)", "Value": int((1 - T).sum())},
        {"Statistic": "Poverty 75th percentile (cutoff)", "Value": f"{q75:.4f}"},
        {"Statistic": "E[Y|T=1] (mean outcome treated)", "Value": f"{np.nanmean(Y1):.4f}"},
        {"Statistic": "E[Y|T=0] (mean outcome control)", "Value": f"{np.nanmean(Y0):.4f}"},
        {"Statistic": "τ_naive (unadjusted ATE)", "Value": f"{tau_naive:.4f}"},
    ])
    summary.to_csv(out_dir / "03e_treatment_summary.csv", index=False)

    # Add treatment and controls to gdf for downstream use
    gdf_causal = gdf.copy()
    gdf_causal["T"] = T
    gdf_causal["Y"] = Y
    gdf_causal["log_pop_density"] = log_pop_density
    gdf_causal.to_file(out_dir / "03e_causal_analysis.gpkg", driver="GPKG")

    # -------------------------------------------------------------------------
    # Print
    # -------------------------------------------------------------------------
    print("=" * 60)
    print("03e — Causal Setup (Treatment, Outcome, Controls, Estimand)")
    print("=" * 60)
    print("\n--- Definitions ---")
    for _, row in definitions.iterrows():
        print(f"  {row['Component']}: {row['Definition']}")
    print("\n--- Summary ---")
    for _, row in summary.iterrows():
        print(f"  {row['Statistic']}: {row['Value']}")
    print("\n--- Three estimators under different modeling strategies ---")
    for _, row in estimators_df.iterrows():
        se_str = f", SE_robust={row['se_robust']:.4f}" if not np.isnan(row['se_robust']) else ""
        exp_str = f", exp(τ)={row['exp_tau']:.4f}" if not np.isnan(row['exp_tau']) else ""
        print(f"  {row['Estimator']}: τ={row['tau']:.4f}{se_str}{exp_str}")
    print(f"\n  Saved: {out_dir / '03e_causal_definitions.csv'}")
    print(f"  Saved: {out_dir / '03e_treatment_summary.csv'}")
    print(f"  Saved: {out_dir / '03e_estimators.csv'}")
    print(f"  Saved: {out_dir / '03e_causal_analysis.gpkg'} (T, Y, log_pop_density added)")
    print("\nDone.")
    print("=" * 60)


if __name__ == "__main__":
    main()
