#!/usr/bin/env python3
"""
04 — Allocation difference in person units (counterfactual totals on the step-02 sample).

Uses quadkeys from harmonised_with_residual.gpkg (same rows as script 02). Conditional
shares on that sample sum to 1:

  s_wp_i = worldpop_i / sum(worldpop),  s_meta_i = meta_i / sum(meta)

Counterfactuals (allocation-only; neither source is asserted as census truth):

  A — WorldPop total, Meta spatial pattern:  pop_hat_i = s_meta_i * sum(wp)
      delta_wp_ref_i = pop_hat_i - worldpop_i  (sums to ~0)

  B — Meta total, WorldPop spatial pattern:  pop_tilde_i = s_wp_i * sum(meta)
      delta_meta_ref_i = pop_tilde_i - meta_i  (sums to ~0)

Usage:
  python pipeline/04_impact.py --region KEN_Nairobi
  python pipeline/04_impact.py -i outputs/02/harmonised_with_residual.gpkg -o outputs
  python pipeline/04_impact.py --region MEX_MexicoCity --plot-map --save-gpkg

Outputs (under outputs/{REGION}/04_impact/ by default):
  Table4_impact_population_summary.csv — includes share_mass_redistribution_M (half-L1 between share vectors).
  Table4b_allocation_sensitivity.csv — budget share to high-poverty cells (poverty_mean ≥ p75) and allocation Gini;
      rows: full_grid and analysis_sample_only (same mask as 03b) when residual + poverty allow.
  Optional Python maps/GPKG: 04_delta_people_wp_total.png, 04_delta_people_meta_total.png, 04_impact_per_cell.gpkg
  R figures: pipeline/04_plots.R — dumbbell (high-poverty shares), bar chart (M), combined 04_operation_impact; see script header for --cross-city.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg"
OUT_SUBDIR = "04_impact"


def _resolve_paths(args: argparse.Namespace) -> tuple[Path, Path]:
    import region_config

    if getattr(args, "region", None) and getattr(args, "footprint", None):
        raise SystemExit("Use --region (city) or --footprint (event AOI), not both.")
    if args.footprint:
        code = region_config.require_footprint(args.footprint)
        inp = region_config.footprint_geo_dir(code, "02") / "harmonised_with_residual.gpkg"
        out_root = args.output_dir if args.output_dir is not None else region_config.footprint_csv_dir(code)
        return inp, out_root
    if args.region:
        args.region = region_config.require_city_region(args.region)
        inp = region_config.geo_dir(args.region, "02") / "harmonised_with_residual.gpkg"
        out_root = args.output_dir if args.output_dir is not None else region_config.csv_dir(args.region)
        return inp, out_root
    inp = args.input or DEFAULT_INPUT
    out_root = args.output_dir or PROJECT_ROOT / "outputs"
    return inp, out_root


def _gini_coefficient(x: np.ndarray) -> float:
    """Gini coefficient (0 = equality, 1 = maximal inequality). Matches 03b formula."""
    x = np.asarray(x, dtype=float)
    x = x[~np.isnan(x) & (x >= 0)]
    if len(x) < 2:
        return float("nan")
    x = np.sort(x)
    n = len(x)
    return float((2 * np.sum((np.arange(1, n + 1)) * x) - (n + 1) * np.sum(x)) / (n * np.sum(x)))


def _allocation_sensitivity_block(
    label: str,
    region: str,
    n_cells: int,
    poverty_vals: np.ndarray,
    s_wp: np.ndarray,
    s_meta: np.ndarray,
) -> dict:
    """Budget B=1 proportional to shares; compare Meta vs WP share accruing to high-poverty (≥ p75) cells."""
    q75 = float(np.nanpercentile(poverty_vals.astype(float), 75))
    mask = poverty_vals.astype(float) >= q75
    n_high = int(np.sum(mask))
    share_wp_s = float(np.sum(s_wp[mask]))
    share_meta_s = float(np.sum(s_meta[mask]))
    gw = _gini_coefficient(s_wp)
    gm = _gini_coefficient(s_meta)
    return {
        "sample_scope": label,
        "region": region,
        "n_cells": n_cells,
        "q75_poverty": q75,
        "n_high_poverty": n_high,
        "share_wp_high_poverty": share_wp_s,
        "share_meta_high_poverty": share_meta_s,
        "diff_meta_minus_wp": share_meta_s - share_wp_s,
        "gini_wp_alloc": gw,
        "gini_meta_alloc": gm,
        "delta_gini": gm - gw,
    }


def _metrics(delta: np.ndarray, total_ref: float) -> dict:
    abs_d = np.abs(delta)
    n = len(delta)
    l1_half = 0.5 * float(np.nansum(abs_d))
    mean_abs = float(np.nanmean(abs_d)) if n else float("nan")
    med_abs = float(np.nanmedian(abs_d)) if n else float("nan")
    rmse = float(np.sqrt(np.nanmean(delta**2))) if n else float("nan")
    max_abs = float(np.nanmax(abs_d)) if n else float("nan")
    pct = (mean_abs / total_ref * 100.0) if total_ref > 0 else float("nan")
    return {
        "mean_abs_delta": mean_abs,
        "median_abs_delta": med_abs,
        "rmse_delta": rmse,
        "max_abs_delta": max_abs,
        "l1_transfer": l1_half,
        "mean_abs_delta_pct_of_total": pct,
    }


def parse_args():
    p = argparse.ArgumentParser(description="04 — Person-level allocation impact (counterfactuals)")
    p.add_argument("-i", "--input", type=Path, default=None, help="harmonised_with_residual.gpkg from step 02")
    p.add_argument("-o", "--output-dir", type=Path, default=None, help="Region output root (default: outputs or outputs/{region})")
    p.add_argument("--region", type=str, default=None, help="Region code; sets input/output paths via config")
    import region_config
    region_config.add_footprint_arg(p)
    p.add_argument("--plot-map", action="store_true", help="Write choropleth maps of per-cell deltas")
    p.add_argument("--save-gpkg", action="store_true", help="Write per-cell GeoPackage with counterfactual columns")
    p.add_argument(
        "--project-crs",
        type=str,
        default="EPSG:32737",
        help="CRS for 03b-aligned subsample (analysis_sample_only row); passed to poverty_utils",
    )
    return p.parse_args()


def main():
    args = parse_args()
    input_path, out_root = _resolve_paths(args)
    if not input_path.exists():
        raise FileNotFoundError(f"Missing input: {input_path}. Run step 02 first.")

    if args.footprint:
        import region_config
        out_dir = region_config.footprint_step_paths(args.footprint, OUT_SUBDIR)
    elif args.region:
        import region_config
        out_dir = region_config.step_paths(args.region, OUT_SUBDIR)
    else:
        out_dir = out_root / OUT_SUBDIR
        out_dir.mkdir(parents=True, exist_ok=True)

    import geopandas as gpd

    gdf = gpd.read_file(input_path)
    wp_col = "worldpop_count" if "worldpop_count" in gdf.columns else "worldpop_raw"
    meta_col = "meta_baseline" if "meta_baseline" in gdf.columns else "meta_raw"
    if wp_col not in gdf.columns or meta_col not in gdf.columns:
        raise ValueError(f"Expected columns {wp_col!r} and {meta_col!r} in {input_path}")

    wp = gdf[wp_col].astype(float).fillna(0).values
    meta = gdf[meta_col].astype(float).fillna(0).values
    T_wp = float(np.nansum(wp))
    T_meta = float(np.nansum(meta))
    if T_wp <= 0 or T_meta <= 0:
        raise ValueError(f"Non-positive totals: sum(worldpop)={T_wp}, sum(meta)={T_meta}")

    s_wp = wp / T_wp
    s_meta = meta / T_meta

    pop_cf_meta_pattern_wp_total = s_meta * T_wp
    pop_cf_wp_pattern_meta_total = s_wp * T_meta
    delta_wp_ref = pop_cf_meta_pattern_wp_total - wp
    delta_meta_ref = pop_cf_wp_pattern_meta_total - meta

    m_wp = _metrics(delta_wp_ref, T_wp)
    m_meta = _metrics(delta_meta_ref, T_meta)

    row = {
        "region": args.region or "",
        "n_cells": len(gdf),
        "total_worldpop": T_wp,
        "total_meta": T_meta,
        "sum_delta_wp_ref": float(np.nansum(delta_wp_ref)),
        "sum_delta_meta_ref": float(np.nansum(delta_meta_ref)),
    }
    for k, v in m_wp.items():
        row[f"wp_ref_{k}"] = v
    for k, v in m_meta.items():
        row[f"meta_ref_{k}"] = v

    # Share-space mass redistribution: M = (1/2) * sum_i |s_meta_i - s_wp_i| (total variation distance).
    M = 0.5 * float(np.nansum(np.abs(s_meta - s_wp)))
    row["share_mass_redistribution_M"] = M
    row["share_mass_redistribution_M_pct"] = 100.0 * M
    expected_wp_l1 = T_wp * M
    if not np.isclose(m_wp["l1_transfer"], expected_wp_l1, rtol=1e-9, atol=1e-6):
        print(
            f"  Note: wp_ref_l1_transfer ({m_wp['l1_transfer']:.6g}) vs T_wp*M ({expected_wp_l1:.6g}) — check inputs.",
            file=sys.stderr,
        )

    summary_path = out_dir / "Table4_impact_population_summary.csv"
    pd.DataFrame([row]).to_csv(summary_path, index=False)

    print("=" * 60)
    print("04 — Allocation impact (person units, conditional shares on this sample)")
    print("=" * 60)
    print(f"  Input: {input_path}")
    print(f"  Cells: {len(gdf)}, total WorldPop: {T_wp:.2f}, total Meta: {T_meta:.2f}")
    print(f"  sum(delta_wp_ref) = {row['sum_delta_wp_ref']:.6f} (expect ~0)")
    print(f"  sum(delta_meta_ref) = {row['sum_delta_meta_ref']:.6f} (expect ~0)")
    print(f"  wp_ref  L1 transfer (half L1): {m_wp['l1_transfer']:.2f}")
    print(f"  meta_ref L1 transfer (half L1): {m_meta['l1_transfer']:.2f}")
    print(f"  Share mass redistribution M (half-L1 on shares): {M:.6f} ({100.0 * M:.4f}% of unit budget)")
    print(f"  Saved: {summary_path}")

    # --- Allocation sensitivity (high poverty) + Gini on allocations (Table 4b) ---
    if "poverty_mean" not in gdf.columns:
        print(
            "  Skipping Table4b_allocation_sensitivity.csv (no poverty_mean column).",
            file=sys.stderr,
        )
    else:
        sens_rows = []
        pov_full = gdf["poverty_mean"].values
        sens_rows.append(_allocation_sensitivity_block("full_grid", args.region or "", len(gdf), pov_full, s_wp, s_meta))

        if "allocation_residual" in gdf.columns or "allocation_log_ratio" in gdf.columns:
            try:
                import poverty_utils

                gdf_a = poverty_utils.load_and_prepare_gdf(
                    input_path, args.project_crs, residual_col="allocation_residual"
                )
                wp_a = (
                    gdf_a["worldpop_count"].astype(float).fillna(0).values
                    if "worldpop_count" in gdf_a.columns
                    else gdf_a[wp_col].astype(float).fillna(0).values
                )
                meta_a = (
                    gdf_a["meta_baseline"].astype(float).fillna(0).values
                    if "meta_baseline" in gdf_a.columns
                    else gdf_a[meta_col].astype(float).fillna(0).values
                )
                Tw = float(np.nansum(wp_a))
                Tm = float(np.nansum(meta_a))
                if Tw > 0 and Tm > 0:
                    sens_rows.append(
                        _allocation_sensitivity_block(
                            "analysis_sample_only",
                            args.region or "",
                            len(gdf_a),
                            gdf_a["poverty_mean"].values,
                            wp_a / Tw,
                            meta_a / Tm,
                        )
                    )
                else:
                    print(
                        "  Skipping analysis_sample_only row (non-positive totals on 03b subsample).",
                        file=sys.stderr,
                    )
            except Exception as exc:
                print(f"  Skipping analysis_sample_only row: {exc}", file=sys.stderr)
        else:
            print(
                "  Skipping analysis_sample_only row (no allocation_residual; run step 02).",
                file=sys.stderr,
            )

        tbl4b_path = out_dir / "Table4b_allocation_sensitivity.csv"
        pd.DataFrame(sens_rows).to_csv(tbl4b_path, index=False)
        print(f"  Saved: {tbl4b_path}")

    if args.save_gpkg:
        out_gdf = gdf.copy()
        out_gdf["pop_cf_meta_pattern_wp_total"] = pop_cf_meta_pattern_wp_total
        out_gdf["pop_cf_wp_pattern_meta_total"] = pop_cf_wp_pattern_meta_total
        out_gdf["delta_people_wp_total"] = delta_wp_ref
        out_gdf["delta_people_meta_total"] = delta_meta_ref
        gpkg_path = out_dir / "04_impact_per_cell.gpkg"
        out_gdf.to_file(gpkg_path, driver="GPKG")
        print(f"  Saved: {gpkg_path}")

    if args.plot_map:
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        def _one_map(series: np.ndarray, title: str, fname: str):
            fig, ax = plt.subplots(figsize=(8, 8))
            lim = max(abs(np.nanmin(series)), abs(np.nanmax(series)), 1e-6)
            gdf.plot(
                ax=ax,
                column=series,
                legend=True,
                cmap="RdBu_r",
                legend_kwds={"shrink": 0.6},
                vmin=-lim,
                vmax=lim,
            )
            ax.set_title(title)
            ax.set_axis_off()
            plt.tight_layout()
            plt.savefig(out_dir / fname, dpi=150, bbox_inches="tight")
            plt.close()

        _one_map(
            delta_wp_ref,
            "Δ people (WorldPop ref): Meta pattern at WP total − WorldPop",
            "04_delta_people_wp_total.png",
        )
        _one_map(
            delta_meta_ref,
            "Δ people (Meta ref): WP pattern at Meta total − Meta",
            "04_delta_people_meta_total.png",
        )
        print(f"  Saved: {out_dir / '04_delta_people_wp_total.png'}")
        print(f"  Saved: {out_dir / '04_delta_people_meta_total.png'}")


if __name__ == "__main__":
    main()
