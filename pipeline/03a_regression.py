#!/usr/bin/env python3
"""
03a — Regression (Residual ~ Poverty + Distance + Density) and diagnostics.

- Residual distribution sanity check (histogram, KDE, skewness) before OLS
- OLS with standardized coefficients (beta) and partial R²
- Heteroskedasticity, VIF

Usage:
  python scripts/03a_regression.py -i outputs/02/harmonised_with_residual.gpkg

Outputs: Table2_regression.csv (with beta_standardized, partial_R2), diagnostic plots.
"""

import argparse
import sys
from pathlib import Path
import numpy as np
import pandas as pd
from scipy import stats
from scipy.stats import linregress
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poverty_utils  # your helper that loads & prepares the gdf

DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg"
OUT_SUBDIR = "03a_regression"


def _stars(p):
    return "***" if p < 0.001 else ("**" if p < 0.01 else ("*" if p < 0.05 else ""))


def safe_standardize(arr):
    arr = np.asarray(arr, dtype=float).copy()
    arr[~np.isfinite(arr)] = np.nan  # replace inf with nan for nanmean/nanstd
    mean = np.nanmean(arr)
    std = np.nanstd(arr)
    if std < 1e-10 or not np.isfinite(std):
        std = 1.0
    out = (arr - mean) / std
    out[~np.isfinite(out)] = np.nan
    return out


def parse_args():
    p = argparse.ArgumentParser(description="03a — Regression + diagnostics")
    p.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT, help="02_harmonised_with_residual.gpkg")
    p.add_argument("-o", "--output-dir", type=Path, default=PROJECT_ROOT / "outputs", help="outputs root")
    p.add_argument("--project-crs", type=str, default="EPSG:32737", help="CRS for distances (default UTM 37S)")
    p.add_argument("--residual-var", type=str, default="allocation_residual",
                   help="Which residual column to use as dependent variable.")
    return p.parse_args()


def main():
    args = parse_args()

    if not args.input.exists():
        raise FileNotFoundError(f"Missing input: {args.input}. Run step 02 first.")

    out_dir = args.output_dir / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    import geopandas as gpd
    # quick check for requested column
    sample = gpd.read_file(args.input, rows=1)
    residual_var = args.residual_var if args.residual_var in sample.columns else ("allocation_residual" if "allocation_residual" in sample.columns else "allocation_log_ratio")
    if residual_var != args.residual_var:
        print(f"Note: requested residual var '{args.residual_var}' not in input; falling back to '{residual_var}'")
    dv_label = "allocation_residual (raw DV)"

    # load and prepare gdf (your helper should handle CRS, distance, population density columns, etc.)
    gdf = poverty_utils.load_and_prepare_gdf(args.input, args.project_crs, residual_col=residual_var)

    print("=" * 60)
    print("03a — Regression + Diagnostics")
    print("=" * 60)
    print(f"  Dependent variable: {dv_label}")
    print(f"  Valid quadkeys: {len(gdf)}")
    if "poverty_mean" in gdf.columns:
        print(f"  Poverty range: {gdf['poverty_mean'].min():.4f}–{gdf['poverty_mean'].max():.4f}")
    else:
        raise KeyError("poverty_mean missing in prepared gdf; ensure step 01 included poverty or re-run with poverty.")

    # pull arrays
    poverty = gdf["poverty_mean"].values
    dv = gdf[residual_var].values

    # standardize poverty for interpretable coefficients
    poverty_z = safe_standardize(poverty)

    # A. Residual distribution sanity check (before OLS)
    print("\n--- A. Residual Distribution (DV sanity check) ---")
    skew_dv = stats.skew(dv)
    print(f"  Skewness of {dv_label}: {skew_dv:.4f}")
    print("  (Log-ratio residuals often skew; |skew| > 1 suggests non-normality)")
    # Save data for R plotting (03a_plots.R)
    pd.DataFrame({"allocation_residual": dv}).to_csv(out_dir / "03a_residual_for_plots.csv", index=False)
    pd.DataFrame([{"skew": skew_dv, "dv_label": dv_label}]).to_csv(out_dir / "03a_residual_meta.csv", index=False)
    print(f"  Saved: {out_dir / '03a_residual_for_plots.csv'} (run Rscript pipeline/03a_plots.R for figure)")

    # B. Regression
    print("\n--- B. Regression ---")
    print("\nModel 1: DV = β0 + β1 * Poverty_z (bivariate)")
    slope, intercept, r_val, p_val, se = linregress(poverty_z, dv)
    m1_poverty_coef, m1_poverty_se = slope, se
    m1_const_coef = intercept
    print(f"  β₀ = {intercept:.4f}")
    print(f"  β₁ = {slope:.4f} (SE = {se:.4f}), p = {p_val:.4f}")

    # Model 2: controlled
    print("\nModel 2: DV = β0 + β1*Poverty_z + β2*Distance_z + β3*LogPopDensity_z (controlled)")
    model2 = None
    model2_robust = None
    try:
        import statsmodels.api as sm
        # prepare predictors with safe standardization
        if "Distance" not in gdf.columns:
            raise KeyError("Distance column missing from gdf. poverty_utils.load_and_prepare_gdf should compute it.")
        if "PopulationDensity" not in gdf.columns:
            raise KeyError("PopulationDensity missing from gdf. Ensure it's prepared in poverty_utils.")

        log_dens = np.log(np.asarray(gdf["PopulationDensity"].values, dtype=float) + 1.0)
        log_dens[~np.isfinite(log_dens)] = np.nan
        X_df = pd.DataFrame({
            "Poverty": poverty_z,
            "Distance": safe_standardize(gdf["Distance"].values),
            "PopulationDensity": safe_standardize(log_dens)
        })
        # Drop rows with any inf/nan in X or dv (statsmodels requires finite data)
        valid = np.isfinite(dv) & X_df.notna().all(axis=1)
        if valid.sum() < 10:
            raise ValueError(f"Only {valid.sum()} rows with finite data; need at least 10 for Model 2")
        X_clean = sm.add_constant(X_df[valid])
        dv_clean = dv[valid]
        if valid.sum() < len(gdf):
            print(f"  Dropped {len(gdf) - valid.sum()} rows with inf/nan in predictors or DV")
        model2 = sm.OLS(dv_clean, X_clean).fit()
        model2_robust = sm.OLS(dv_clean, X_clean).fit(cov_type="HC3")

        # print tidy coefficients table
        print(model2.summary().tables[1].as_text())

        # multiplicative interpretation if DV is log ratio
        if residual_var in ["allocation_residual", "allocation_log_ratio"]:
            try:
                mult_effect = np.exp(model2.params["Poverty"])
                print(f"\nexp(β₁) = {mult_effect:.3f} multiplicative difference in Meta/WP ratio per SD increase in poverty")
            except Exception:
                pass

        # Standardized coefficients (beta): beta_j = coef_j * (std_Xj / std_y)
        # X are z-scored so std_Xj = 1; beta_j = coef_j / std_y
        std_y = np.std(dv_clean)
        beta_std = model2.params.copy()
        beta_std["const"] = np.nan  # constant not standardized
        for col in X_df.columns:
            beta_std[col] = model2.params[col] / std_y if std_y > 1e-10 else np.nan

        # Partial R²: R²(full) - R²(without j)
        r2_full = model2.rsquared
        partial_r2 = {}
        for col in X_df.columns:
            cols_drop = [c for c in X_df.columns if c != col]
            X_red = sm.add_constant(X_df.loc[valid, cols_drop])
            m_red = sm.OLS(dv_clean, X_red).fit()
            partial_r2[col] = r2_full - m_red.rsquared
        partial_r2["const"] = np.nan

        # save coefficients with beta and partial R²
        coef_df = pd.DataFrame({
            "coef": model2.params,
            "std_err": model2.bse,
            "std_err_HC3": model2_robust.bse,
            "t": model2.tvalues,
            "t_HC3": model2_robust.tvalues,
            "p": model2.pvalues,
            "p_HC3": model2_robust.pvalues,
            "beta_standardized": [beta_std[c] for c in model2.params.index],
            "partial_R2": [partial_r2.get(c, np.nan) for c in model2.params.index],
        }, index=model2.params.index)
        coef_df.to_csv(out_dir / "regression_coefficients.csv")
        print(f"  Saved: {out_dir / 'regression_coefficients.csv'}")
        print("  Beta (standardized):", {c: f"{beta_std[c]:.4f}" for c in X_df.columns})
        print("  Partial R²:", {c: f"{partial_r2[c]:.4f}" for c in X_df.columns})

        # C. Heteroskedasticity
        print("\n--- C. Heteroskedasticity ---")
        try:
            from statsmodels.stats.diagnostic import het_breuschpagan, het_white
            bp_stat, bp_p, _, _ = het_breuschpagan(model2.resid, X_clean)
            print(f"  Breusch-Pagan: LM={bp_stat:.4f}, p={bp_p:.4f}")
            w_stat, w_p, _, _ = het_white(model2.resid, X_clean)
            print(f"  White: LM={w_stat:.4f}, p={w_p:.4f}")
            het_df = pd.DataFrame([
                {"Test": "Breusch-Pagan", "Statistic": bp_stat, "p_value": bp_p},
                {"Test": "White", "Statistic": w_stat, "p_value": w_p},
            ])
            het_df.to_csv(out_dir / "Table2b_heteroskedasticity.csv", index=False)
            print(f"  Saved: {out_dir / 'Table2b_heteroskedasticity.csv'}")
        except Exception as e:
            print(f"  Heteroskedasticity tests skipped or failed: {e}")

        # D. VIF
        print("\n--- D. Multicollinearity (VIF) ---")
        try:
            from statsmodels.stats.outliers_influence import variance_inflation_factor
            vif_results = []
            # VIF needs design matrix without const in position argument consistent with columns
            cols = X_clean.columns.tolist()
            for i, col in enumerate(cols):
                if col == "const":
                    continue
                vif = variance_inflation_factor(X_clean.values, cols.index(col))
                vif_results.append({"Variable": col, "VIF": vif})
            vif_df = pd.DataFrame(vif_results)
            vif_df.to_csv(out_dir / "Table2b_VIF.csv", index=False)
            print(vif_df.to_string(index=False))
            print(f"  Saved: {out_dir / 'Table2b_VIF.csv'}")
        except Exception as e:
            print(f"  VIF calculation skipped or failed: {e}")

    except ImportError:
        print("  (Install statsmodels to run regressions and diagnostics: pip install statsmodels)")
    except Exception as e:
        print(f"  Model 2 failed: {e}")

    # write Table 2 formatted output (with beta_standardized, partial_R2)
    print("\n--- Writing Table 2 (regression summary) ---")
    try:
        if model2 is not None:
            def _se_str(m, r, col):
                try:
                    base = f"{m.params[col]:.3f}{_stars(m.pvalues[col])} (SE={m.bse[col]:.3f})"
                    if r is not None and col in r.bse.index:
                        return base.replace(")", f", HC3={r.bse[col]:.3f})")
                    return base
                except Exception:
                    return ""
            # Build rows with beta and partial R²
            rows = []
            for col, label in [("Poverty", "Poverty (std)"), ("Distance", "Distance (std)"),
                               ("PopulationDensity", "Log pop density (std)")]:
                m1_str = f"{m1_poverty_coef:.3f}{_stars(p_val)} ({m1_poverty_se:.3f})" if col == "Poverty" else "—"
            rows.append({
                "Variable": label,
                "Model_1_Bivariate": m1_str,
                "Model_2_Controlled": _se_str(model2, model2_robust, col),
                "beta_standardized": f"{beta_std[col]:.4f}" if col in beta_std and not np.isnan(beta_std.get(col, np.nan)) else "—",
                "partial_R2": f"{partial_r2[col]:.4f}" if col in partial_r2 and not np.isnan(partial_r2.get(col, np.nan)) else "—",
            })
            rows.append({
                "Variable": "Constant",
                "Model_1_Bivariate": f"{m1_const_coef:.3f}",
                "Model_2_Controlled": f"{model2.params['const']:.3f}{_stars(model2.pvalues['const'])} ({model2.bse['const']:.3f})",
                "beta_standardized": "—",
                "partial_R2": "—",
            })
            rows.append({"Variable": "Observations", "Model_1_Bivariate": str(len(gdf)), "Model_2_Controlled": str(len(gdf)), "beta_standardized": "—", "partial_R2": "—"})
            tbl2_df = pd.DataFrame(rows)
        else:
            tbl2_df = pd.DataFrame([
                {"Variable": "Poverty (std)", "Model_1_Bivariate": f"{m1_poverty_coef:.3f}{_stars(p_val)} ({m1_poverty_se:.3f})", "Model_2_Controlled": "", "beta_standardized": "", "partial_R2": ""},
                {"Variable": "Constant", "Model_1_Bivariate": f"{m1_const_coef:.3f}", "Model_2_Controlled": "", "beta_standardized": "", "partial_R2": ""},
                {"Variable": "Observations", "Model_1_Bivariate": str(len(gdf)), "Model_2_Controlled": "", "beta_standardized": "", "partial_R2": ""},
            ])
        tbl2_df.to_csv(out_dir / "Table2_regression.csv", index=False)
        print(f"  Saved: {out_dir / 'Table2_regression.csv'}")
    except Exception as e:
        print(f"  Writing Table 2 failed: {e}")

    print("\nDone.")
    print("=" * 60)


if __name__ == "__main__":
    main()
