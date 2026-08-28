#!/usr/bin/env python3
"""
04b — Crisis inference sensitivity.

Hold the observed Meta crisis count C_i fixed and the Meta baseline *total* fixed.
Replace only the baseline geography with WorldPop's spatial pattern, then ask
whether inferred increase/decrease (and crisis hotspots) change.

Change definition (no baseline-to-crisis metric exists elsewhere in the pipeline):

  G_i = log((C_i + 1) / (B_i + 1))

  B_i^Meta  = meta_baseline on the step-02 grid
  B_i^WP    = (sum_j B_j^Meta) * s_i^WP
  C_i       = median n_crisis at the same reference hour (maps / headline F, J)

Headline F and Jaccard are crisis-dependent. |G_Meta − G_WP| is not (C cancels);
that quantity is kept only as a supplementary baseline-divergence metric.

Temporal check: recompute F_t, J_10,t^+, J_10,t^- on each crisis day at the
reference hour (Table4d).

Outputs:
  Table4c_crisis_inference_sensitivity.csv
  Table4d_crisis_snapshots.csv
  04b_crisis_inference.gpkg  (per-cell G, S, sign-change class; for 04b_plots.R)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(Path(__file__).resolve().parent))

OUT_SUBDIR = "04b_crisis_inference"
CHANGE_DEFINITION = "log((C+1)/(B+1))"


def _top_k_jaccard(scores_a: np.ndarray, scores_b: np.ndarray, k_frac: float = 0.10) -> tuple[float, int]:
    """Jaccard of the top-k cells by descending score (same rule as 03b)."""
    nloc = len(scores_a)
    if nloc < 2:
        return float("nan"), 0
    kk = max(1, min(int(round(k_frac * nloc)), nloc))
    top_a = set(np.argsort(-scores_a)[:kk].tolist())
    top_b = set(np.argsort(-scores_b)[:kk].tolist())
    uni = top_a | top_b
    if not uni:
        return float("nan"), kk
    return len(top_a & top_b) / len(uni), kk


def _g_and_flip(c: np.ndarray, b_meta: np.ndarray, b_wp: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    g_meta = np.log((c + 1.0) / (b_meta + 1.0))
    g_wp = np.log((c + 1.0) / (b_wp + 1.0))
    flipped = np.sign(g_meta) != np.sign(g_wp)
    return g_meta, g_wp, flipped


def _f_and_jaccard(c: np.ndarray, b_meta: np.ndarray, b_wp: np.ndarray) -> tuple[float, float, float, int]:
    """F (%), J10+, J10−, n on cells with finite C and baselines."""
    ok = np.isfinite(c) & np.isfinite(b_meta) & np.isfinite(b_wp)
    n = int(np.sum(ok))
    if n < 2:
        return float("nan"), float("nan"), float("nan"), n
    g_meta, g_wp, flipped = _g_and_flip(c[ok], b_meta[ok], b_wp[ok])
    f_pct = 100.0 * float(np.mean(flipped))
    j_inc, _ = _top_k_jaccard(g_meta, g_wp, 0.10)
    j_dec, _ = _top_k_jaccard(-g_meta, -g_wp, 0.10)
    return f_pct, j_inc, j_dec, n


def _series_summary(x: np.ndarray) -> dict:
    x = np.asarray(x, dtype=float)
    x = x[np.isfinite(x)]
    if len(x) == 0:
        return {
            "median": float("nan"),
            "min": float("nan"),
            "max": float("nan"),
            "iqr_lo": float("nan"),
            "iqr_hi": float("nan"),
        }
    return {
        "median": float(np.median(x)),
        "min": float(np.min(x)),
        "max": float(np.max(x)),
        "iqr_lo": float(np.percentile(x, 25)),
        "iqr_hi": float(np.percentile(x, 75)),
    }


def _time_label(date_start: str, date_end: str) -> str:
    if not date_start:
        return ""
    if not date_end or date_start == date_end:
        return str(date_start)
    return f"{date_start}/{date_end}"


def _inference_class(g_meta: np.ndarray, g_wp: np.ndarray) -> np.ndarray:
    sm = np.sign(g_meta)
    sw = np.sign(g_wp)
    out = np.full(len(g_meta), "other", dtype=object)
    out[(sm > 0) & (sw > 0)] = "increase_both"
    out[(sm < 0) & (sw < 0)] = "decrease_both"
    out[(sm > 0) & (sw < 0)] = "increase_to_decrease"
    out[(sm < 0) & (sw > 0)] = "decrease_to_increase"
    return out


def parse_args():
    p = argparse.ArgumentParser(description="04b — Crisis inference sensitivity")
    p.add_argument("-i", "--input", type=Path, default=None, help="harmonised_with_residual.gpkg from step 02")
    p.add_argument("-o", "--output-dir", type=Path, default=None)
    p.add_argument("--region", type=str, default=None)
    import region_config

    region_config.add_footprint_arg(p)
    p.add_argument("--ref-hour", type=int, default=None, choices=[0, 8, 16])
    p.add_argument("--force-rebuild-crisis", action="store_true", help="Rebuild the country n_crisis cache")
    return p.parse_args()


def main():
    args = parse_args()
    import region_config
    from pdc_crisis import load_or_build_crisis_tables

    if getattr(args, "region", None) and getattr(args, "footprint", None):
        raise SystemExit("Use --region (city) or --footprint (event AOI), not both.")

    if args.footprint:
        code = region_config.require_footprint(args.footprint)
        inp = region_config.footprint_geo_dir(code, "02") / "harmonised_with_residual.gpkg"
        out_dir = region_config.footprint_step_paths(code, OUT_SUBDIR)
        cfg = region_config.get_footprint_config(code)
        country = region_config.country_display_name(code)
        city = region_config.display_label(code, cfg)
        region_code = code
        footprint = True
    elif args.region:
        args.region = region_config.require_city_region(args.region)
        inp = region_config.geo_dir(args.region, "02") / "harmonised_with_residual.gpkg"
        out_dir = region_config.step_paths(args.region, OUT_SUBDIR)
        cfg = region_config.get_region_config(args.region)
        country = region_config.country_display_name(args.region)
        city = region_config.display_label(args.region, cfg)
        region_code = args.region
        footprint = False
    else:
        inp = args.input or (PROJECT_ROOT / "outputs" / "02" / "harmonised_with_residual.gpkg")
        out_root = args.output_dir or (PROJECT_ROOT / "outputs")
        out_dir = Path(out_root) / OUT_SUBDIR
        out_dir.mkdir(parents=True, exist_ok=True)
        country = ""
        city = ""
        region_code = ""
        footprint = False
        cfg = {}

    if args.input is not None:
        inp = args.input
    if not inp.exists():
        raise FileNotFoundError(f"Missing input: {inp}. Run step 02 first.")

    import geopandas as gpd

    gdf = gpd.read_file(inp)
    if "quadkey" not in gdf.columns:
        raise ValueError(f"Expected quadkey column in {inp}")
    wp_col = "worldpop_count" if "worldpop_count" in gdf.columns else "worldpop_raw"
    meta_col = "meta_baseline" if "meta_baseline" in gdf.columns else "meta_raw"
    if wp_col not in gdf.columns or meta_col not in gdf.columns:
        raise ValueError(f"Expected {wp_col!r} and {meta_col!r} in {inp}")

    gdf = gdf.copy()
    gdf["quadkey"] = gdf["quadkey"].astype(str)
    b_meta = gdf[meta_col].astype(float).fillna(0).values
    wp = gdf[wp_col].astype(float).fillna(0).values
    t_meta = float(np.nansum(b_meta))
    t_wp = float(np.nansum(wp))
    if t_meta <= 0 or t_wp <= 0:
        raise ValueError(f"Non-positive totals: sum(meta)={t_meta}, sum(worldpop)={t_wp}")
    s_wp = wp / t_wp
    b_wp = s_wp * t_meta
    if not np.isclose(float(np.nansum(b_wp)), t_meta, rtol=1e-6, atol=1e-3):
        print(
            f"  Note: sum(B_WP)={float(np.nansum(b_wp)):.6g} vs sum(B_Meta)={t_meta:.6g}",
            file=sys.stderr,
        )

    lookup_code = region_code or (args.footprint or args.region)
    if not lookup_code:
        raise SystemExit("04b needs --region or --footprint to load the PDC crisis extract.")
    crisis, snapshots = load_or_build_crisis_tables(
        lookup_code,
        footprint=footprint,
        ref_hour=args.ref_hour,
        force=args.force_rebuild_crisis,
    )
    crisis = crisis.copy()
    crisis["quadkey"] = crisis["quadkey"].astype(str)
    date_start = str(crisis["date_start"].iloc[0]) if "date_start" in crisis.columns and len(crisis) else ""
    date_end = str(crisis["date_end"].iloc[0]) if "date_end" in crisis.columns and len(crisis) else ""
    time_lab = _time_label(date_start, date_end)

    gdf = gdf.merge(crisis[["quadkey", "n_crisis_median"]], on="quadkey", how="left")
    c = gdf["n_crisis_median"].astype(float).values
    valid = np.isfinite(c) & np.isfinite(b_meta) & np.isfinite(b_wp)
    n_grid = len(gdf)
    n = int(np.sum(valid))
    if n < 2:
        raise ValueError(f"Need ≥2 cells with observed crisis counts (matched {n} / {n_grid}).")

    g_meta = np.full(n_grid, np.nan)
    g_wp = np.full(n_grid, np.nan)
    gm, gw, flip_ok = _g_and_flip(c[valid], b_meta[valid], b_wp[valid])
    g_meta[valid] = gm
    g_wp[valid] = gw
    s_i = np.abs(g_meta - g_wp)
    flipped = np.zeros(n_grid, dtype=bool)
    flipped[valid] = flip_ok
    n_flipped = int(np.sum(flipped[valid]))
    direction_flip_pct = 100.0 * n_flipped / n

    j_inc, k_inc = _top_k_jaccard(g_meta[valid], g_wp[valid], 0.10)
    j_dec, k_dec = _top_k_jaccard(-g_meta[valid], -g_wp[valid], 0.10)

    if "poverty_mean" not in gdf.columns:
        high = np.zeros(n_grid, dtype=bool)
        q75 = float("nan")
        print("  No poverty_mean; socioeconomic columns set to NA.", file=sys.stderr)
    else:
        pov = gdf["poverty_mean"].astype(float).values
        q75 = float(np.nanpercentile(pov[valid], 75))
        high = np.isfinite(pov) & (pov >= q75)

    high_v = high[valid]
    flip_v = flipped[valid]
    s_v = s_i[valid]
    n_high = int(np.sum(high_v))
    n_other = int(np.sum(~high_v))
    med_s_high = float(np.nanmedian(s_v[high_v])) if n_high else float("nan")
    med_s_other = float(np.nanmedian(s_v[~high_v])) if n_other else float("nan")
    delta_s = med_s_high - med_s_other
    # Crisis-dependent socioeconomic contrast: P(flip | T), not |G_Meta − G_WP|.
    f_high = 100.0 * float(np.mean(flip_v[high_v])) if n_high else float("nan")
    f_other = 100.0 * float(np.mean(flip_v[~high_v])) if n_other else float("nan")
    delta_f = f_high - f_other
    rr_f = (f_high / f_other) if (np.isfinite(f_other) and f_other > 0) else float("nan")

    inf_cls = np.full(n_grid, "", dtype=object)
    inf_cls[valid] = _inference_class(g_meta[valid], g_wp[valid])

    # Per-day F, J at the same reference hour (C changes; baselines do not).
    qk = gdf["quadkey"].astype(str).values
    snap_rows = []
    if snapshots is not None and len(snapshots):
        snap = snapshots.copy()
        snap["quadkey"] = snap["quadkey"].astype(str)
        city_qk = set(qk.tolist())
        snap = snap[snap["quadkey"].isin(city_qk)]
        b_by_qk = pd.DataFrame({"quadkey": qk, "B_meta": b_meta, "B_wp": b_wp})
        for date, sub in snap.groupby("date", sort=True):
            m = b_by_qk.merge(sub[["quadkey", "n_crisis"]], on="quadkey", how="left")
            f_t, j_inc_t, j_dec_t, n_t = _f_and_jaccard(
                m["n_crisis"].astype(float).values,
                m["B_meta"].astype(float).values,
                m["B_wp"].astype(float).values,
            )
            if n_t < 2:
                continue
            snap_rows.append(
                {
                    "country": country,
                    "city": city,
                    "region": region_code,
                    "date": str(date),
                    "n": n_t,
                    "direction_flip_pct": f_t,
                    "jaccard_increase_top10": j_inc_t,
                    "jaccard_decrease_top10": j_dec_t,
                }
            )
    snap_df = pd.DataFrame(snap_rows)
    tbl4d_path = out_dir / "Table4d_crisis_snapshots.csv"
    if len(snap_df):
        snap_df.to_csv(tbl4d_path, index=False)
        f_sum = _series_summary(snap_df["direction_flip_pct"].values)
        ji_sum = _series_summary(snap_df["jaccard_increase_top10"].values)
        jd_sum = _series_summary(snap_df["jaccard_decrease_top10"].values)
        n_snapshots = int(len(snap_df))
    else:
        f_sum = ji_sum = jd_sum = _series_summary(np.array([]))
        n_snapshots = 0

    row = {
        "country": country,
        "city": city,
        "region": region_code,
        "time": time_lab,
        "n": n,
        "n_grid": n_grid,
        "n_flipped": n_flipped,
        "direction_flip_pct": direction_flip_pct,
        "jaccard_increase_top10": j_inc,
        "jaccard_decrease_top10": j_dec,
        "k_top10": k_inc,
        "flip_pct_high_deprivation": f_high,
        "flip_pct_other": f_other,
        "delta_F": delta_f,
        "rr_F": rr_f,
        "n_high_deprivation": n_high,
        "n_snapshots": n_snapshots,
        "median_F_t": f_sum["median"],
        "F_t_min": f_sum["min"],
        "F_t_max": f_sum["max"],
        "F_t_iqr_lo": f_sum["iqr_lo"],
        "F_t_iqr_hi": f_sum["iqr_hi"],
        "median_J_inc_t": ji_sum["median"],
        "median_J_dec_t": jd_sum["median"],
        "median_sensitivity_high_deprivation": med_s_high,
        "median_sensitivity_other": med_s_other,
        "delta_S": delta_s,
        "q75_poverty": q75,
        "change_definition": CHANGE_DEFINITION,
        "total_meta_baseline": t_meta,
        "sum_B_wp": float(np.nansum(b_wp)),
    }
    tbl_path = out_dir / "Table4c_crisis_inference_sensitivity.csv"
    pd.DataFrame([row]).to_csv(tbl_path, index=False)

    out_gdf = gdf.copy()
    out_gdf["B_meta"] = b_meta
    out_gdf["B_wp"] = b_wp
    out_gdf["C"] = c
    out_gdf["G_meta"] = g_meta
    out_gdf["G_wp"] = g_wp
    out_gdf["S"] = s_i
    out_gdf["flipped"] = flipped.astype(int)
    out_gdf["high_deprivation"] = high.astype(int)
    out_gdf["inference_change"] = inf_cls
    keep = [
        "quadkey",
        "B_meta",
        "B_wp",
        "C",
        "G_meta",
        "G_wp",
        "S",
        "flipped",
        "high_deprivation",
        "inference_change",
        "poverty_mean",
        "geometry",
    ]
    keep = [c for c in keep if c in out_gdf.columns]
    gpkg_path = out_dir / "04b_crisis_inference.gpkg"
    out_gdf[keep].to_file(gpkg_path, driver="GPKG")

    print("=" * 60)
    print("04b — Crisis inference sensitivity")
    print("=" * 60)
    print(f"  {country} / {city}  time={time_lab}")
    print(f"  Cells with crisis: {n} / {n_grid}")
    print(f"  Direction flip F: {direction_flip_pct:.2f}%  ({n_flipped} cells)")
    print(f"  J_10+ (increase hotspots): {j_inc:.3f}")
    print(f"  J_10- (decrease hotspots): {j_dec:.3f}")
    print(f"  F | high deprivation: {f_high:.2f}%   F | other: {f_other:.2f}%   ΔF: {delta_f:.2f} pp")
    if n_snapshots:
        print(
            f"  Snapshots ({n_snapshots} days): median F_t={f_sum['median']:.2f}%  "
            f"range {f_sum['min']:.1f}–{f_sum['max']:.1f}%   "
            f"median J+={ji_sum['median']:.3f}  median J-={jd_sum['median']:.3f}"
        )
        print(f"  Saved: {tbl4d_path}")
    print(f"  ΔS (supplement; C cancels): {delta_s:.4f}")
    print(f"  Saved: {tbl_path}")
    print(f"  Saved: {gpkg_path}")


if __name__ == "__main__":
    main()
