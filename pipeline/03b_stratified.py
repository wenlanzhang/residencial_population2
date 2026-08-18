#!/usr/bin/env python3
"""
03b — Stratified comparison and Gini by poverty quintile.

Residual by poverty stratum (Table 3), Gini by poverty quintile (Table 4),
rank instability between Meta and WorldPop allocation shares (Table_rank_instability.csv).

Usage:
  python pipeline/03b_stratified.py -i outputs/{REGION}/02/harmonised_with_residual.gpkg -o outputs/{REGION} --project-crs EPSG:32737
"""

import argparse
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import pandas as pd
from scipy import stats

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))
import poverty_utils

DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg"
OUT_SUBDIR = "03b_stratified"


def gini_coefficient(x):
    """Gini coefficient (0 = equality, 1 = maximal inequality)."""
    x = np.asarray(x)
    x = x[~np.isnan(x) & (x >= 0)]
    if len(x) < 2:
        return np.nan
    x = np.sort(x)
    n = len(x)
    return (2 * np.sum((np.arange(1, n + 1)) * x) - (n + 1) * np.sum(x)) / (n * np.sum(x))


def _top_k_jaccard(scores_a: np.ndarray, scores_b: np.ndarray, k: float) -> tuple[float, int]:
    """Jaccard overlap between indices of top-k cells by score (by descending score)."""
    nloc = len(scores_a)
    kk = max(1, min(int(round(k)), nloc))
    top_a = set(np.argsort(-scores_a)[:kk].tolist())
    top_b = set(np.argsort(-scores_b)[:kk].tolist())
    uni = top_a | top_b
    if not uni:
        return float("nan"), kk
    return len(top_a & top_b) / len(uni), kk


def parse_args():
    p = argparse.ArgumentParser(description="03b — Stratified + inequality")
    p.add_argument("-i", "--input", type=Path, default=DEFAULT_INPUT)
    p.add_argument("-o", "--output-dir", type=Path, default=PROJECT_ROOT / "outputs")
    p.add_argument("--project-crs", type=str, default="EPSG:32737", help="CRS for distance (default: UTM 37S Nairobi)")
    return p.parse_args()


def main():
    args = parse_args()
    if not args.input.exists():
        raise FileNotFoundError("Provide -i path (output from script 02)")
    out_dir = args.output_dir / OUT_SUBDIR
    out_dir.mkdir(parents=True, exist_ok=True)

    gdf = poverty_utils.load_and_prepare_gdf(args.input, args.project_crs, residual_col="allocation_residual")
    print("=" * 60)
    print("03b — Stratified Comparison + Gini by Poverty Quintile")
    print("=" * 60)
    print(f"  Valid quadkeys: {len(gdf)}")

    # E. Rank instability (prioritisation of Meta vs WorldPop shares on this sample)
    print("\n--- E. Rank instability ---")
    wp_v = gdf["worldpop_count"].astype(float).fillna(0).values
    meta_v = gdf["meta_baseline"].astype(float).fillna(0).values
    n_r = len(gdf)
    Tw = float(np.sum(wp_v))
    Tm = float(np.sum(meta_v))
    if n_r < 2 or Tw <= 0 or Tm <= 0:
        print("  Skipped (need ≥2 cells and positive WP/Meta totals).")
        rank_row = {
            "n_cells": n_r,
            "spearman_rho": float("nan"),
            "spearman_p": float("nan"),
            "kendall_tau": float("nan"),
            "kendall_p": float("nan"),
            "mean_abs_rank_gap_norm": float("nan"),
            "jaccard_top_1pct": float("nan"),
            "k_top_1pct": float("nan"),
            "jaccard_top_5pct": float("nan"),
            "k_top_5pct": float("nan"),
            "jaccard_top_10pct": float("nan"),
            "k_top_10pct": float("nan"),
        }
    else:
        r_wp = stats.rankdata(wp_v, method="average")
        r_meta = stats.rankdata(meta_v, method="average")
        denom = (n_r - 1) if n_r > 1 else float("nan")
        mean_abs_gap_norm = float(np.mean(np.abs(r_wp - r_meta)) / denom)
        sp_rho, sp_p = stats.spearmanr(wp_v, meta_v)
        kd_tau, kd_p = stats.kendalltau(wp_v, meta_v)
        rank_row = {
            "n_cells": n_r,
            "spearman_rho": float(sp_rho) if sp_rho is not None and not np.isnan(sp_rho) else float("nan"),
            "spearman_p": float(sp_p) if sp_p is not None and not np.isnan(sp_p) else float("nan"),
            "kendall_tau": float(kd_tau) if kd_tau is not None and not np.isnan(kd_tau) else float("nan"),
            "kendall_p": float(kd_p) if kd_p is not None and not np.isnan(kd_p) else float("nan"),
            "mean_abs_rank_gap_norm": mean_abs_gap_norm,
        }
        for pct, key_j, key_k in (
            (0.01, "jaccard_top_1pct", "k_top_1pct"),
            (0.05, "jaccard_top_5pct", "k_top_5pct"),
            (0.10, "jaccard_top_10pct", "k_top_10pct"),
        ):
            k_target = max(1, round(pct * n_r))
            j1, k1 = _top_k_jaccard(wp_v, meta_v, k_target)
            rank_row[key_j] = j1
            rank_row[key_k] = int(k1)
        print(
            f"  Spearman ρ={rank_row['spearman_rho']:.4f}, Kendall τ={rank_row['kendall_tau']:.4f}, "
            f"mean |Δrank|/(n−1)={rank_row['mean_abs_rank_gap_norm']:.4f}"
        )
        print(
            f"  Top-K Jaccard (WP vs Meta hotspots): "
            f"1%→{rank_row['jaccard_top_1pct']:.3f} (K={rank_row['k_top_1pct']}), "
            f"5%→{rank_row['jaccard_top_5pct']:.3f} (K={rank_row['k_top_5pct']}), "
            f"10%→{rank_row['jaccard_top_10pct']:.3f} (K={rank_row['k_top_10pct']})"
        )
    rank_path = out_dir / "Table_rank_instability.csv"
    pd.DataFrame([rank_row]).to_csv(rank_path, index=False)
    print(f"  Saved: {rank_path}")

    # A. Interaction term: Residual ~ Poverty + PopulationDensity + Poverty×PopulationDensity
    print("\n--- A. Interaction: Poverty × PopulationDensity ---")
    try:
        import statsmodels.api as sm
        pov_s = (gdf["poverty_mean"] - gdf["poverty_mean"].mean()) / gdf["poverty_mean"].std()
        pop_s = (gdf["PopulationDensity"] - gdf["PopulationDensity"].mean()) / gdf["PopulationDensity"].std()
        X = pd.DataFrame({"Poverty": pov_s, "PopulationDensity": pop_s, "Poverty_x_PopDens": pov_s * pop_s})
        X = sm.add_constant(X)
        model_int = sm.OLS(gdf["allocation_residual"], X).fit()
        print(model_int.summary().tables[1].as_text())
        if "Poverty_x_PopDens" in model_int.params and model_int.pvalues["Poverty_x_PopDens"] < 0.05:
            print("  ✓ Significant interaction — poverty effect varies by density")
        int_coef = pd.DataFrame({
            "coef": model_int.params, "std_err": model_int.bse,
            "p": model_int.pvalues,
        })
        int_coef.to_csv(out_dir / "Table_interaction.csv", index=True)
        print(f"  Saved: {out_dir / 'Table_interaction.csv'}")

        # Marginal effects: predicted residual across poverty levels (at median density)
        pov_vals = np.linspace(gdf["poverty_mean"].min(), gdf["poverty_mean"].max(), 50)
        pov_s_pred = (pov_vals - gdf["poverty_mean"].mean()) / gdf["poverty_mean"].std()
        pop_med_s = (gdf["PopulationDensity"].median() - gdf["PopulationDensity"].mean()) / gdf["PopulationDensity"].std()
        X_pred = pd.DataFrame({
            "Poverty": pov_s_pred,
            "PopulationDensity": np.full_like(pov_s_pred, pop_med_s),
            "Poverty_x_PopDens": pov_s_pred * pop_med_s,
        })
        X_pred = sm.add_constant(X_pred)
        # Align columns to model params (const name can differ: "const" vs "intercept")
        exog_names = list(model_int.params.index)
        if exog_names[0] not in X_pred.columns:
            X_pred.insert(0, exog_names[0], 1.0)
        X_pred = X_pred[exog_names]
        pred = model_int.predict(exog=X_pred)
        se = np.sqrt(np.diag(X_pred.values @ model_int.cov_params() @ X_pred.values.T))
        # Save for R plotting (03b_plots.R)
        pd.DataFrame({
            "poverty": pov_vals, "pred": pred,
            "ci_lo": pred - 1.96 * se, "ci_hi": pred + 1.96 * se
        }).to_csv(out_dir / "03b_marginal_effects_for_plots.csv", index=False)
        print(f"  Saved: {out_dir / '03b_marginal_effects_for_plots.csv'} (run Rscript pipeline/03b_plots.R)")
    except ImportError:
        print("  (Install statsmodels for interaction model)")
    except Exception as e:
        print(f"  Interaction model: {e}")

    # C. Stratified comparison
    print("\n--- C. Stratified Comparison ---")
    gdf["poverty_strata"] = pd.cut(
        gdf["poverty_mean"],
        bins=[-np.inf, gdf["poverty_mean"].quantile(0.25),
              gdf["poverty_mean"].quantile(0.75), np.inf],
        labels=["Low (bottom 25%)", "Medium", "High (top 25%)"],
    )
    strata_stats = gdf.groupby("poverty_strata", observed=False)["allocation_residual"].agg(["mean", "count"])
    print(strata_stats)

    order_s = ["Low (bottom 25%)", "Medium", "High (top 25%)"]
    tbl3 = pd.DataFrame([
        (s, strata_stats.loc[s, "mean"], int(strata_stats.loc[s, "count"])) for s in order_s
    ], columns=["Poverty Stratum", "Mean Residual", "N"])
    tbl3["Mean Residual"] = tbl3["Mean Residual"].map(lambda x: f"{x:.3f}")
    tbl3.to_csv(out_dir / "Table3_poverty_strata.csv", index=False)
    print(f"  Saved: {out_dir / 'Table3_poverty_strata.csv'}")

    h_stat, p_kw = stats.kruskal(
        gdf[gdf["poverty_strata"] == "Low (bottom 25%)"]["allocation_residual"],
        gdf[gdf["poverty_strata"] == "Medium"]["allocation_residual"],
        gdf[gdf["poverty_strata"] == "High (top 25%)"]["allocation_residual"],
    )
    print(f"Kruskal-Wallis H = {h_stat:.4f}, p = {p_kw:.4f}")

    # Save for R plotting (03b_plots.R)
    gdf[["poverty_strata", "allocation_residual"]].to_csv(out_dir / "03b_strata_for_plots.csv", index=False)
    print(f"  Saved: {out_dir / '03b_strata_for_plots.csv'}")

    # D. Gini by poverty quintile
    print("\n--- D. Gini by Poverty Quintile ---")
    gdf["pov_quintile"] = pd.qcut(
        gdf["poverty_mean"], q=5,
        labels=["Q1 (low)", "Q2", "Q3", "Q4", "Q5 (high)"]
    )
    q_order = ["Q1 (low)", "Q2", "Q3", "Q4", "Q5 (high)"]
    results = []
    for q in q_order:
        sub = gdf[gdf["pov_quintile"] == q]
        # Gini on shares for spatial allocation inequality
        wp_s = sub["worldpop_share"] if "worldpop_share" in sub.columns else sub["worldpop_count"] / sub["worldpop_count"].sum()
        meta_s = sub["meta_share"] if "meta_share" in sub.columns else sub["meta_baseline"] / sub["meta_baseline"].sum()
        gini_wp = gini_coefficient(wp_s.values)
        gini_meta = gini_coefficient(meta_s.values)
        results.append({
            "quintile": str(q),
            "n": len(sub),
            "gini_worldpop": gini_wp,
            "gini_meta": gini_meta,
            "delta_gini": gini_meta - gini_wp,
        })
    df_ineq = pd.DataFrame(results)
    print(df_ineq.to_string(index=False))

    q_labels = {"Q1 (low)": "Q1 (Lowest poverty)", "Q2": "Q2", "Q3": "Q3", "Q4": "Q4", "Q5 (high)": "Q5 (Highest poverty)"}
    tbl4 = pd.DataFrame([
        (
            q_labels.get(r["quintile"], r["quintile"]),
            f"{r['gini_worldpop']:.3f}",
            f"{r['gini_meta']:.3f}",
            f"{r['delta_gini']:.3f}",
        )
        for r in results
    ], columns=["Poverty Quintile", "Gini (WorldPop)", "Gini (Meta)", "ΔGini (Meta − WP)"])
    tbl4.to_csv(out_dir / "Table4_gini_by_quintile.csv", index=False)
    print(f"\n  Saved: {out_dir / 'Table4_gini_by_quintile.csv'}")
    print("  If Meta Gini exceeds WorldPop Gini in high-poverty quintiles → greater spatial concentration in Meta allocation.")

    # Table4 already saved; 03b_plots.R will read it for Gini bar chart
    print(f"  (run Rscript pipeline/03b_plots.R for figures)")
    print("=" * 60)


if __name__ == "__main__":
    main()
