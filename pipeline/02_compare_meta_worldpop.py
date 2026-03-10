#!/usr/bin/env python3
"""
Step 2 — Compare spatial allocation (Meta vs WorldPop shares).

All analytical sections use share-based variables:
  wp_share = worldpop / worldpop.sum(), meta_share = meta / meta.sum()
  allocation_residual = log(meta_share / worldpop_share)

0. Summary Statistics (raw for context; shares for analysis)
1. Spatial Agreement: log(meta_share) vs log(worldpop_share) only
1b. Rank Agreement: Top-X overlap, Jaccard
2. Distribution Similarity: meta_share, worldpop_share (KS, EMD)
3. Inequality: Gini on shares (spatial allocation inequality)
4. Spatial Structure: Moran/LISA/Gi* on log(share)
5. Allocation residual: allocation_residual maps, peripheral vs central
6. Agreement Typology: zscore(meta_share), zscore(worldpop_share)

Requires outputs from 01_harmonise_datasets.py (with worldpop_share, meta_share).

Usage:
  conda activate geo_env_LLM
  python pipeline/02_compare_meta_worldpop.py
  python pipeline/02_compare_meta_worldpop.py -i outputs/01_harmonised_meta_worldpop.gpkg
  # With optional context for residual tests:
  python pipeline/02_compare_meta_worldpop.py --informal informal.gpkg --rural rural.gpkg --nightlight viirs.csv
  # Basemap versions of residual maps require: pip install contextily xyzservices
"""

import argparse
from pathlib import Path

import numpy as np
import scipy
if not hasattr(scipy, "inf"):
    scipy.inf = np.inf

import matplotlib
matplotlib.use("Agg")
import geopandas as gpd
import matplotlib.pyplot as plt
from scipy import stats

# Allow importing poverty_utils from pipeline/
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from poverty_utils import has_valid_centroids
from shapely.geometry import Point

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INPUT = PROJECT_ROOT / "outputs" / "01" / "harmonised_meta_worldpop.gpkg"
OUT_DIR = PROJECT_ROOT / "outputs" / "02"

# Philippines zoom: center 7.0647° N, 125.6088° E (Mindanao), buffer ±0.6°
PHILIPPINES_BBOX = (125.0088, 6.4647, 126.2088, 7.6647)  # xmin, ymin, xmax, ymax


def _get_region_bbox(region_code: str):
    """Get map bbox for region code from config. Returns (xmin, ymin, xmax, ymax) or None."""
    try:
        import region_config
        cfg = region_config.get_region_config(region_code)
        bbox = cfg.get("map_bbox")
        if bbox and len(bbox) == 4:
            return tuple(bbox)
    except (ImportError, ValueError, KeyError):
        pass
    return None


def gini_coefficient(x):
    """Gini coefficient (0 = perfect equality, 1 = maximal inequality)."""
    x = np.asarray(x)
    x = x[~np.isnan(x) & (x >= 0)]
    if len(x) == 0:
        return np.nan
    x = np.sort(x)
    n = len(x)
    cumx = np.cumsum(x)
    return (2 * np.sum((np.arange(1, n + 1)) * x) - (n + 1) * np.sum(x)) / (n * np.sum(x))


def lorenz_curve(x):
    """Return (cumulative share of population, cumulative share of value) for Lorenz curve."""
    x = np.asarray(x)
    x = x[~np.isnan(x) & (x >= 0)]
    x = np.sort(x)
    n = len(x)
    if n == 0:
        return np.array([0]), np.array([0])
    cumx = np.cumsum(x)
    return np.arange(1, n + 1) / n, cumx / cumx[-1]


def _load_context(gdf_valid, path: Path, key_col="quadkey"):
    """Load auxiliary context and join to gdf by quadkey."""
    path = Path(path)
    if not path.exists():
        return None
    import pandas as pd
    if path.suffix.lower() in (".gpkg", ".geojson", ".shp"):
        aux = gpd.read_file(path)
    else:
        aux = pd.read_csv(path)
    if key_col not in aux.columns or key_col not in gdf_valid.columns:
        return None
    # Drop geometry from aux to avoid merge conflicts
    cols = [c for c in aux.columns if c != key_col and c != "geometry"]
    if not cols:
        return None
    return gdf_valid.merge(aux[[key_col] + cols], on=key_col, how="left")


def _detect_region(gdf):
    """Auto-detect region from data centroid. Returns region code (PHI, KEN, ...) or 'full'."""
    bounds = gdf.total_bounds
    clon = (bounds[0] + bounds[2]) / 2
    clat = (bounds[1] + bounds[3]) / 2
    try:
        import region_config
        for code, cfg in region_config.load_regions().items():
            if code == "data_root" or not isinstance(cfg, dict):
                continue
            lon_r = cfg.get("lon_range", [])
            lat_r = cfg.get("lat_range", [])
            if len(lon_r) == 2 and len(lat_r) == 2:
                if lon_r[0] <= clon <= lon_r[1] and lat_r[0] <= clat <= lat_r[1]:
                    return code
    except (ImportError, FileNotFoundError):
        pass
    if 118 <= clon <= 127 and 5 <= clat <= 20:
        return "PHI"  # backward compat
    return "full"


def _get_map_gdf(gdf, region, region_bbox=None):
    """Return clipped GeoDataFrame for map plotting when region has bbox. Calculations use full gdf.
    When region_bbox is None (e.g. clip_shape set in config): return full gdf — data extent is used.
    When region_bbox is provided: clip to that bbox."""
    if region_bbox is None:
        return gdf
    bbox_tuple = region_bbox if isinstance(region_bbox, (tuple, list)) and len(region_bbox) == 4 else _get_region_bbox(region) if region and region != "full" else None
    if not bbox_tuple:
        return gdf
    from shapely.geometry import box
    bbox = box(*bbox_tuple)
    return gdf[gdf.intersects(bbox)].copy()


def run_comparison(input_gpkg: Path, out_dir: Path, args=None):
    out_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.read_file(input_gpkg)

    # Define shares (create if missing for backwards compatibility)
    wp_raw = gdf["worldpop_count"].values if "worldpop_count" in gdf.columns else gdf["worldpop_raw"].values
    meta_raw = gdf["meta_baseline"].values if "meta_baseline" in gdf.columns else gdf["meta_raw"].values
    if "worldpop_share" in gdf.columns and "meta_share" in gdf.columns:
        wp_share = gdf["worldpop_share"].values
        meta_share = gdf["meta_share"].values
    else:
        wp_sum = np.nansum(np.where(wp_raw > 0, wp_raw, 0))
        meta_sum = np.nansum(np.where(meta_raw > 0, meta_raw, 0))
        wp_share = np.where(wp_raw > 0, wp_raw / (wp_sum + 1e-10), 0)
        meta_share = np.where(meta_raw > 0, meta_raw / (meta_sum + 1e-10), 0)
        gdf["worldpop_share"] = wp_share
        gdf["meta_share"] = meta_share

    # Filter to valid pairs (both share > 0) for log-based analyses
    valid = (wp_share > 0) & (meta_share > 0)
    wp_s = wp_share[valid]
    meta_s = meta_share[valid]
    wp_v = wp_raw[valid]  # raw for context only
    meta_v = meta_raw[valid]
    gdf_valid = gdf[valid].copy()
    # Project once and reuse (avoids repeated CRS transforms)
    gdf_proj = gdf_valid.to_crs("EPSG:32737")

    print("=" * 60)
    # Region for map zoom (calculations use full data)
    region = getattr(args, "region", None) if args else None
    region_bbox = getattr(args, "region_bbox", None) if args else None
    if region is None:
        region = _detect_region(gdf_valid)
    if region and region != "full":
        gdf_map_init = _get_map_gdf(gdf_valid, region, region_bbox)
        label = getattr(args, "region_label", None) or region
        print(f"  Region: {label} — maps zoomed to bbox; {len(gdf_map_init)} quadkeys in view")

    print("STEP 2: Compare Spatial Allocation (share-based)")
    print("=" * 60)
    print(f"Total quadkeys: {len(gdf)}, valid (both share > 0): {valid.sum()}")

    if valid.sum() == 0:
        print("\n*** ERROR: No valid quadkeys (both WorldPop and Meta share > 0). ***")
        print("  Cannot run comparison. Check that:")
        print("  1. Meta baseline GPKG exists and has data for this region")
        print("  2. WorldPop raster covers the region")
        print("  3. Harmonised data from step 01 has overlapping non-zero cells")
        import sys
        sys.exit(1)

    # -------------------------------------------------------------------------
    # 0. Summary Statistics
    # -------------------------------------------------------------------------
    print("\n--- 0. Summary Statistics ---")

    def _summary_stats(arr, name):
        arr = np.asarray(arr)
        arr = arr[~np.isnan(arr) & (arr >= 0)]
        if len(arr) == 0:
            return {"mean": np.nan, "median": np.nan, "min": np.nan, "max": np.nan, "std": np.nan}
        return {
            "mean": float(np.mean(arr)),
            "median": float(np.median(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "std": float(np.std(arr)),
        }

    stats_wp = _summary_stats(wp_v, "WorldPop")
    stats_meta = _summary_stats(meta_v, "Meta")
    total_wp_sum = float(wp_v.sum())
    total_meta_sum = float(meta_v.sum())

    print("Per grid cell (valid pairs) — raw counts (context only):")
    for lbl, s in [("WorldPop", stats_wp), ("Meta", stats_meta)]:
        print(f"  {lbl}: mean={s['mean']:.1f}, median={s['median']:.1f}, min={s['min']:.1f}, max={s['max']:.1f}, std={s['std']:.1f}")
    print(f"Raw totals (context only): WorldPop={total_wp_sum:,.0f}, Meta={total_meta_sum:,.0f}")
    print("  → Subsequent analysis uses normalized spatial shares (worldpop_share, meta_share).")

    import pandas as pd
    tbl_stats = pd.DataFrame([
        {"Source": "WorldPop", "Mean": round(stats_wp["mean"], 3), "Median": round(stats_wp["median"], 3), "Min": round(stats_wp["min"], 3), "Max": round(stats_wp["max"], 3), "Std": round(stats_wp["std"], 3), "Total": total_wp_sum},
        {"Source": "Meta", "Mean": round(stats_meta["mean"], 3), "Median": round(stats_meta["median"], 3), "Min": round(stats_meta["min"], 3), "Max": round(stats_meta["max"], 3), "Std": round(stats_meta["std"], 3), "Total": total_meta_sum},
    ])
    tbl_stats.to_csv(out_dir / "02_summary_statistics.csv", index=False, float_format="%.3f")
    print(f"  Saved: {out_dir / '02_summary_statistics.csv'}")

    # Population density (per km²) — need area (reuse gdf_proj)
    area_km2 = gdf_proj.geometry.area.values / 1e6
    area_km2 = np.maximum(area_km2, 1e-6)  # avoid div by zero
    density_wp = wp_v / area_km2
    density_meta = meta_v / area_km2

    skew_wp = stats.skew(density_wp)
    skew_meta = stats.skew(density_meta)
    use_log = abs(skew_wp) > 1 or abs(skew_meta) > 1
    print(f"Population density skewness: WorldPop={skew_wp:.2f}, Meta={skew_meta:.2f} → {'log-scale' if use_log else 'linear'} histograms")

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    for ax, dens, label, color in [(axes[0], density_wp, "WorldPop", "steelblue"), (axes[1], density_meta, "Meta", "coral")]:
        dens_valid = dens[dens > 0]
        if use_log and len(dens_valid) > 0:
            ax.hist(np.log10(dens_valid + 1), bins=40, alpha=0.7, color=color, edgecolor="white", linewidth=0.3)
            ax.set_xlabel("log₁₀(density + 1) [per km²]")
        else:
            ax.hist(dens_valid, bins=40, alpha=0.7, color=color, edgecolor="white", linewidth=0.3)
            ax.set_xlabel("Population density [per km²]")
        ax.set_ylabel("Count")
        ax.set_title(f"{label} — population density per grid cell")
        ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "02_density_histogram.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_dir / '02_density_histogram.png'}")

    # Overlapped version: linear and log scale side by side, with KDE on right Y-axis
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    dens_wp_valid = density_wp[density_wp > 0]
    dens_meta_valid = density_meta[density_meta > 0]
    all_dens = np.concatenate([dens_wp_valid, dens_meta_valid])
    bins_lin = np.linspace(all_dens.min(), all_dens.max(), 41) if len(all_dens) > 0 else 40
    x_wp_log = np.log10(dens_wp_valid + 1) if len(dens_wp_valid) > 0 else np.array([])
    x_meta_log = np.log10(dens_meta_valid + 1) if len(dens_meta_valid) > 0 else np.array([])
    x_all_log = np.concatenate([x_wp_log, x_meta_log])
    bins_log = np.linspace(x_all_log.min(), x_all_log.max(), 41) if len(x_all_log) > 0 else 40

    def _add_hist_kde(ax, data_wp, data_meta, bins, xlabel, x_eval_wp, x_eval_meta):
        """Histogram (left Y) + KDE (right Y) for both sources."""
        ax.hist(data_wp, bins=bins, alpha=0.6, label="WorldPop", color="steelblue", edgecolor="white", linewidth=0.3)
        ax.hist(data_meta, bins=bins, alpha=0.6, label="Meta", color="coral", edgecolor="white", linewidth=0.3)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Count", color="gray")
        ax.tick_params(axis="y", labelcolor="gray")
        ax2 = ax.twinx()
        if len(data_wp) > 1:
            kde_wp = stats.gaussian_kde(data_wp, bw_method="scott")
            ax2.plot(x_eval_wp, kde_wp(x_eval_wp), color="steelblue", lw=2, linestyle="--", alpha=0.9)
        if len(data_meta) > 1:
            kde_meta = stats.gaussian_kde(data_meta, bw_method="scott")
            ax2.plot(x_eval_meta, kde_meta(x_eval_meta), color="coral", lw=2, linestyle="--", alpha=0.9)
        ax2.set_ylabel("KDE (density)", color="black")
        ax2.tick_params(axis="y", labelcolor="black")
        ax.legend(loc="upper right", fontsize=8)
        ax.grid(True, alpha=0.3)

    # Left: linear scale
    x_lin = np.linspace(all_dens.min(), all_dens.max(), 200) if len(all_dens) > 0 else np.linspace(0, 1, 200)
    _add_hist_kde(axes[0], dens_wp_valid, dens_meta_valid, bins_lin, "Population density [per km²]", x_lin, x_lin)
    axes[0].set_title("Population density (linear)")

    # Right: log scale
    x_log = np.linspace(x_all_log.min(), x_all_log.max(), 200) if len(x_all_log) > 0 else np.linspace(0, 1, 200)
    _add_hist_kde(axes[1], x_wp_log, x_meta_log, bins_log, "log₁₀(density + 1) [per km²]", x_log, x_log)
    axes[1].set_title("Population density (log)")

    plt.suptitle("Population density per grid cell (overlapped)")
    plt.tight_layout()
    plt.savefig(out_dir / "02_density_histogram_overlapped.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_dir / '02_density_histogram_overlapped.png'}")

    # CDF and KS test: spatial probability distribution p_i = x_i / sum(x_i)
    def _prob_dist(x):
        """Convert to spatial probability: p_i = x_i / sum(x_i)."""
        x = np.asarray(x, dtype=float)
        x = x[~np.isnan(x) & (x >= 0)]
        if len(x) == 0:
            return x
        return x / (x.sum() + 1e-10)

    dens_wp_prob = _prob_dist(dens_wp_valid)
    dens_meta_prob = _prob_dist(dens_meta_valid)
    x_wp_log_prob = _prob_dist(x_wp_log + 1e-10)   # log10(d+1) ≥ 0
    x_meta_log_prob = _prob_dist(x_meta_log + 1e-10)

    ks_dens_lin, p_dens_lin = stats.ks_2samp(dens_wp_prob, dens_meta_prob)
    ks_dens_log, p_dens_log = stats.ks_2samp(x_wp_log_prob, x_meta_log_prob)

    fig, axes = plt.subplots(1, 2, figsize=(10, 4))

    def _concentration_curve(x, weights):
        """Concentration curve: sort by x, y = cumulative share of weights. Returns (x_sorted, cum_share)."""
        x, w = np.asarray(x), np.asarray(weights)
        order = np.argsort(x)
        x_s = x[order]
        w_s = w[order]
        cum = np.cumsum(w_s)
        return x_s, cum / (cum[-1] + 1e-10)

    def _percentile_value(x_sorted, y_sorted, p):
        """Value at which cumulative share reaches p (e.g. 0.5 = median, 0.8 = 80%)."""
        idx = np.searchsorted(y_sorted, p, side="left")
        idx = min(idx, len(x_sorted) - 1)
        return x_sorted[idx]

    def _plot_cdf_ks(ax, data_wp, data_meta, weights_wp, weights_meta, xlabel, ks_stat, p_val, title,
                    x_wp_raw, x_meta_raw):
        """Plot concentration curve (CDF of population share) with 50% and 80% vertical lines."""
        x_wp, cdf_wp = _concentration_curve(x_wp_raw, weights_wp)
        x_meta, cdf_meta = _concentration_curve(x_meta_raw, weights_meta)
        ax.plot(x_wp, cdf_wp, color="steelblue", lw=2, label="WorldPop")
        ax.plot(x_meta, cdf_meta, color="coral", lw=2, label="Meta")
        # KS: max vertical distance
        x_all = np.sort(np.unique(np.concatenate([x_wp, x_meta])))
        if len(x_all) > 0:
            cdf_wp_i = np.interp(x_all, x_wp, cdf_wp)
            cdf_meta_i = np.interp(x_all, x_meta, cdf_meta)
            idx_max = np.argmax(np.abs(cdf_wp_i - cdf_meta_i))
            ax.axvline(x_all[idx_max], color="gray", linestyle=":", alpha=0.7)
        # Median (50%) and 80% concentration vertical lines
        med_wp = _percentile_value(x_wp, cdf_wp, 0.5)
        med_meta = _percentile_value(x_meta, cdf_meta, 0.5)
        p80_wp = _percentile_value(x_wp, cdf_wp, 0.8)
        p80_meta = _percentile_value(x_meta, cdf_meta, 0.8)
        ax.axvline(med_wp, color="steelblue", linestyle="--", alpha=0.6, linewidth=1)
        ax.axvline(med_meta, color="coral", linestyle="--", alpha=0.6, linewidth=1)
        ax.axvline(p80_wp, color="steelblue", linestyle="-", alpha=0.4, linewidth=0.8)
        ax.axvline(p80_meta, color="coral", linestyle="-", alpha=0.4, linewidth=0.8)
        ax.axhline(0.5, color="gray", linestyle=":", alpha=0.4)
        ax.axhline(0.8, color="gray", linestyle=":", alpha=0.4)
        ax.set_xlabel(xlabel)
        ax.set_ylabel("Cumulative share of population")
        ax.set_title(title)
        ax.set_ylim(0, 1)
        p_str = f"<0.001" if p_val < 0.001 else f"{p_val:.3f}"
        interp_txt = (f"50%: Meta={med_meta:.2g}, WP={med_wp:.2g}\n"
                      f"80%: Meta={p80_meta:.2g}, WP={p80_wp:.2g}\n"
                      f"KS (D)={ks_stat:.3f}, p={p_str}")
        ax.text(0.98, 0.02, interp_txt, transform=ax.transAxes,
                fontsize=8, verticalalignment="bottom", horizontalalignment="right",
                bbox=dict(boxstyle="round", facecolor="wheat", alpha=0.5))
        ax.legend()
        ax.grid(True, alpha=0.3)
        return med_wp, med_meta, p80_wp, p80_meta

    # Concentration curve: x = density (or log), weights = share of population (p_i)
    _plot_cdf_ks(axes[0], dens_wp_prob, dens_meta_prob, dens_wp_prob, dens_meta_prob,
                "Population density [per km²]", ks_dens_lin, p_dens_lin, "Concentration (linear)",
                dens_wp_valid, dens_meta_valid)
    _plot_cdf_ks(axes[1], dens_wp_prob, dens_meta_prob, dens_wp_prob, dens_meta_prob,
                "log₁₀(density + 1) [per km²]", ks_dens_log, p_dens_log, "Concentration (log)",
                x_wp_log, x_meta_log)

    plt.suptitle("Concentration curves: WorldPop vs Meta — 80% of Meta pop below X vs Y in WorldPop (Kolmogorov–Smirnov)")
    plt.tight_layout()
    plt.savefig(out_dir / "02_density_cdf_ks.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_dir / '02_density_cdf_ks.png'}")
    print(f"  KS statistic (D) — density linear (pᵢ=xᵢ/Σxᵢ): {ks_dens_lin:.4f}, p={p_dens_lin:.2e}")
    print(f"  KS statistic (D) — density log (pᵢ=xᵢ/Σxᵢ):   {ks_dens_log:.4f}, p={p_dens_log:.2e}")

    # -------------------------------------------------------------------------
    # 1. Spatial Agreement — log(meta_share) vs log(worldpop_share) only
    # -------------------------------------------------------------------------
    print("\n--- 1. Spatial Agreement (share-based) ---")
    log_wp = np.log(wp_s + 1e-10)
    log_meta = np.log(meta_s + 1e-10)
    r_spearman_log, p_spearman_log = stats.spearmanr(log_wp, log_meta)
    r_pearson_log, p_pearson_log = stats.pearsonr(log_wp, log_meta)
    print(f"  log(meta_share) vs log(worldpop_share): Spearman ρ = {r_spearman_log:.4f}, Pearson r = {r_pearson_log:.4f}")
    print("  (Positive = similar spatial allocation pattern)")

    # Log-log hexbin plot
    slope, intercept = np.polyfit(log_meta, log_wp, 1)
    x_line = np.array([log_meta.min(), log_meta.max()])
    y_reg = slope * x_line + intercept

    fig, ax = plt.subplots(figsize=(6, 6))
    hb = ax.hexbin(log_meta, log_wp, gridsize=25, cmap="Blues", mincnt=1, edgecolors="none")
    lim_lo = min(log_meta.min(), log_wp.min())
    lim_hi = max(log_meta.max(), log_wp.max())
    ax.plot([lim_lo, lim_hi], [lim_lo, lim_hi], "k--", lw=1.5, alpha=0.7, label="1:1 line")
    ax.plot(x_line, y_reg, "r-", lw=1.5, alpha=0.9, label="Regression")
    ax.set_xlabel("log(meta_share)")
    ax.set_ylabel("log(worldpop_share)")
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    txt = (f"log(wp_share) = a + b·log(meta_share)\n"
           f"Slope b = {slope:.3f}\n"
           f"Spearman ρ = {r_spearman_log:.3f}\n"
           f"Pearson r = {r_pearson_log:.3f}")
    ax.text(0.05, 0.95, txt, transform=ax.transAxes, fontsize=10, verticalalignment="top",
            bbox=dict(boxstyle="round", facecolor="white", alpha=0.8))
    ax.legend(loc="lower right")
    plt.colorbar(hb, ax=ax, label="Count")
    plt.tight_layout()
    plt.savefig(out_dir / "02_scatter_meta_vs_worldpop.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_dir / '02_scatter_meta_vs_worldpop.png'}")

    # -------------------------------------------------------------------------
    # 1b. Rank Agreement — Top-X overlap, Jaccard, Precision/Recall/F1
    # -------------------------------------------------------------------------
    print("\n--- 1b. Rank Agreement ---")
    print("  (Reference: WorldPop top-X. Meta top-X = predicted. Precision/Recall/F1 for Meta identifying WP high-density cells.)")
    n_cells = len(wp_v)
    rank_wp = np.argsort(np.argsort(-wp_v))  # 0 = highest WP
    rank_meta = np.argsort(np.argsort(-meta_v))  # 0 = highest Meta
    top_x_pcts = [0.05, 0.10, 0.20, 0.25]
    jaccard_vals = []
    for pct in top_x_pcts:
        k = max(1, int(n_cells * pct))
        set_wp = set(np.where(rank_wp < k)[0])  # reference (ground truth)
        set_meta = set(np.where(rank_meta < k)[0])  # predicted
        inter = len(set_wp & set_meta)
        union = len(set_wp | set_meta)
        jaccard = inter / union if union > 0 else np.nan
        precision = inter / k if k > 0 else np.nan  # TP / |predicted| = overlap / k
        recall = inter / k if k > 0 else np.nan    # TP / |reference| = overlap / k (same k)
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else np.nan
        jaccard_vals.append({"Top_X_pct": pct, "k": k, "Overlap": inter, "Jaccard": jaccard,
                            "Precision": precision, "Recall": recall, "F1": f1})
        print(f"  Top {pct*100:.0f}% (k={k}): overlap={inter}, Jaccard={jaccard:.4f}, Precision={precision:.4f}, Recall={recall:.4f}, F1={f1:.4f}")
    pd.DataFrame(jaccard_vals).to_csv(out_dir / "02_rank_agreement.csv", index=False)
    print(f"  Saved: {out_dir / '02_rank_agreement.csv'}")

    # -------------------------------------------------------------------------
    # 2. Distribution Similarity (meta_share vs worldpop_share)
    # -------------------------------------------------------------------------
    print("\n--- 2. Distribution Similarity ---")

    # Use shares directly (already normalized to sum=1)
    wp_norm = (wp_s - wp_s.min()) / (wp_s.max() - wp_s.min() + 1e-10)
    meta_norm = (meta_s - meta_s.min()) / (meta_s.max() - meta_s.min() + 1e-10)

    # Histograms
    fig, axes = plt.subplots(1, 2, figsize=(10, 4))
    axes[0].hist(wp_norm, bins=30, alpha=0.7, label="WorldPop", color="steelblue", density=True)
    axes[0].hist(meta_norm, bins=30, alpha=0.7, label="Meta", color="coral", density=True)
    axes[0].set_xlabel("Normalized value")
    axes[0].set_ylabel("Density")
    axes[0].set_title("Histograms (normalized)")
    axes[0].legend()

    # KDE
    x = np.linspace(0, 1, 200)
    kde_wp = stats.gaussian_kde(wp_norm, bw_method="scott")
    kde_meta = stats.gaussian_kde(meta_norm, bw_method="scott")
    axes[1].plot(x, kde_wp(x), label="WorldPop", color="steelblue", lw=2)
    axes[1].plot(x, kde_meta(x), label="Meta", color="coral", lw=2)
    axes[1].set_xlabel("Normalized value")
    axes[1].set_ylabel("Density")
    axes[1].set_title("Kernel density curves")
    axes[1].legend()
    plt.tight_layout()
    plt.savefig(out_dir / "02_distribution_histogram_kde.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_dir / '02_distribution_histogram_kde.png'}")

    # KS test
    # ks_stat, ks_pval = stats.ks_2samp(wp_norm, meta_norm)    # normalized shares
    ks_stat, ks_pval = stats.ks_2samp(wp_s, meta_s)    # spatial shares
    print(f"Kolmogorov–Smirnov: statistic = {ks_stat:.4f}, p-value = {ks_pval:.2e}")
    print("  (H0: same distribution; low p = distributions differ)")

    # Earth Mover's Distance (Wasserstein)
    emd = stats.wasserstein_distance(wp_norm, meta_norm)
    print(f"Earth Mover's Distance (Wasserstein): {emd:.4f}")
    print("  (0 = identical; higher = more dissimilar)")

    # -------------------------------------------------------------------------
    # 3. Inequality (Gini on shares — spatial allocation inequality)
    # -------------------------------------------------------------------------
    print("\n--- 3. Inequality (share-based) ---")

    gini_wp = gini_coefficient(wp_s)
    gini_meta = gini_coefficient(meta_s)
    delta_gini = gini_meta - gini_wp

    print(f"Gini (WorldPop): {gini_wp:.4f}")
    print(f"Gini (Meta):     {gini_meta:.4f}")
    print(f"ΔGini (Meta - WorldPop): {delta_gini:.4f}")
    print("  (spatial allocation inequality; positive ΔGini = Meta more unequal)")

    # Lorenz curves (shares)
    fig, ax = plt.subplots(figsize=(6, 6))
    pop_wp, val_wp = lorenz_curve(wp_s)
    pop_meta, val_meta = lorenz_curve(meta_s)
    ax.plot(np.concatenate([[0], pop_wp]), np.concatenate([[0], val_wp]), label="WorldPop", color="steelblue", lw=2)
    ax.plot(np.concatenate([[0], pop_meta]), np.concatenate([[0], val_meta]), label="Meta", color="coral", lw=2)
    ax.plot([0, 1], [0, 1], "k--", alpha=0.5, label="Perfect equality")
    ax.set_xlabel("Cumulative share of quadkeys (by count)")
    ax.set_ylabel("Cumulative share of allocation")
    ax.set_title("Lorenz curves (shares)")
    ax.legend()
    ax.set_aspect("equal")
    ax.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.savefig(out_dir / "02_lorenz_curves.png", dpi=150, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {out_dir / '02_lorenz_curves.png'}")

    # Headline Lorenz: "Top X% of cells contain Y% of allocation"
    n_cells = len(wp_s)
    wp_sorted_desc = np.sort(wp_s)[::-1]
    meta_sorted_desc = np.sort(meta_s)[::-1]
    lorenz_headlines = []
    for pct in [0.10, 0.20, 0.50]:
        k = max(1, int(np.ceil(pct * n_cells)))
        y_wp = float(wp_sorted_desc[:k].sum())
        y_meta = float(meta_sorted_desc[:k].sum())
        delta_y = y_meta - y_wp
        lorenz_headlines.append({
            "X_pct": f"Top {pct*100:.0f}% of cells",
            "Y_WP": round(y_wp, 4),
            "Y_Meta": round(y_meta, 4),
            "Delta_Y_Meta_minus_WP": round(delta_y, 4),
        })
        print(f"  Top {pct*100:.0f}% of cells: WP={y_wp:.4f}, Meta={y_meta:.4f}, ΔY={delta_y:.4f}")
    pd.DataFrame(lorenz_headlines).to_csv(out_dir / "02_lorenz_headlines.csv", index=False)
    print(f"  Saved: {out_dir / '02_lorenz_headlines.csv'}")

    # Top-heavy concentration: share in top 1%, 5%, 10%
    top_share_rows = []
    for pct in [0.01, 0.05, 0.10]:
        k = max(1, int(np.ceil(pct * n_cells)))
        top_wp = float(wp_sorted_desc[:k].sum())
        top_meta = float(meta_sorted_desc[:k].sum())
        top_share_rows.append({
            "Top_pct": pct,
            "N_cells": k,
            "Share_WP": round(top_wp, 4),
            "Share_Meta": round(top_meta, 4),
        })
    # Theil index (0 = equality; higher = more inequality)
    def theil_index(x):
        x = np.asarray(x)
        x = x[x > 0]
        if len(x) == 0:
            return np.nan
        n = len(x)
        mu = x.mean()
        return float(np.mean((x / mu) * np.log(x / mu + 1e-15)))
    theil_wp = theil_index(wp_s)
    theil_meta = theil_index(meta_s)
    top_share_rows.append({"Top_pct": "Theil_index", "N_cells": "", "Share_WP": round(theil_wp, 4), "Share_Meta": round(theil_meta, 4)})
    pd.DataFrame(top_share_rows).to_csv(out_dir / "02_top_share_concentration.csv", index=False)
    print(f"  Top-share concentration: 1%={top_share_rows[0]['Share_WP']:.4f}/{top_share_rows[0]['Share_Meta']:.4f}, 5%={top_share_rows[1]['Share_WP']:.4f}/{top_share_rows[1]['Share_Meta']:.4f}, 10%={top_share_rows[2]['Share_WP']:.4f}/{top_share_rows[2]['Share_Meta']:.4f}")
    print(f"  Theil index: WP={theil_wp:.4f}, Meta={theil_meta:.4f}")
    print(f"  Saved: {out_dir / '02_top_share_concentration.csv'}")

    # -------------------------------------------------------------------------
    # 4. Spatial Structure — Moran's I, LISA, Gi* on log(share)
    # -------------------------------------------------------------------------
    print("\n--- 4. Spatial Structure (log share) ---")
    log_wp = np.log(wp_s)
    log_meta = np.log(meta_s)
    try:
        from libpysal.weights import KNN
        from esda.moran import Moran, Moran_Local
        from esda.getisord import G_Local

        # Drop invalid geometries (empty centroids cause KNN.from_dataframe to fail)
        valid_geom = has_valid_centroids(gdf_proj)
        if not valid_geom.all():
            gdf_valid = gdf_valid.loc[valid_geom].reset_index(drop=True)
            gdf_proj = gdf_proj.loc[valid_geom].reset_index(drop=True)
            wp_s = gdf_valid["worldpop_share"].values
            meta_s = gdf_valid["meta_share"].values
            log_wp = np.log(wp_s)
            log_meta = np.log(meta_s)
        # KNN (k=6) — extract coords explicitly (from_dataframe can fail with Point geometries)
        xs = gdf_proj.geometry.centroid.x.values.astype(float)
        ys = gdf_proj.geometry.centroid.y.values.astype(float)
        valid_coords = np.isfinite(xs) & np.isfinite(ys)
        if not valid_coords.all():
            gdf_valid = gdf_valid.loc[valid_coords].reset_index(drop=True)
            gdf_proj = gdf_proj.loc[valid_coords].reset_index(drop=True)
            wp_s = gdf_valid["worldpop_share"].values
            meta_s = gdf_valid["meta_share"].values
            log_wp = np.log(wp_s)
            log_meta = np.log(meta_s)
            xs = gdf_proj.geometry.centroid.x.values.astype(float)
            ys = gdf_proj.geometry.centroid.y.values.astype(float)
        coords = np.column_stack([xs, ys])
        w = KNN.from_array(coords, k=6)
        w.transform = "r"

        moran_wp = Moran(log_wp, w)
        moran_meta = Moran(log_meta, w)
        print(f"  Moran's I (WorldPop): {moran_wp.I:.4f}, p={moran_wp.p_sim:.4f}")
        print(f"  Moran's I (Meta):     {moran_meta.I:.4f}, p={moran_meta.p_sim:.4f}")

        lisa_wp = Moran_Local(log_wp, w)
        lisa_meta = Moran_Local(log_meta, w)
        gdf_valid["lisa_q_wp"] = lisa_wp.q
        gdf_valid["lisa_p_wp"] = lisa_wp.p_sim
        gdf_valid["lisa_q_meta"] = lisa_meta.q
        gdf_valid["lisa_p_meta"] = lisa_meta.p_sim
        gdf_valid["lisa_sig_wp"] = np.where(gdf_valid["lisa_p_wp"] < 0.05, gdf_valid["lisa_q_wp"], 0)
        gdf_valid["lisa_sig_meta"] = np.where(gdf_valid["lisa_p_meta"] < 0.05, gdf_valid["lisa_q_meta"], 0)

        gdf_map = _get_map_gdf(gdf_valid, region, region_bbox)
        for label, col in [("WorldPop", "lisa_sig_wp"), ("Meta", "lisa_sig_meta")]:
            fig, ax = plt.subplots(figsize=(8, 8))
            gdf_map.plot(ax=ax, column=col, categorical=True, legend=True, cmap="RdYlBu_r",
                         legend_kwds={"title": "LISA (1=HH,2=LH,3=LL,4=HL,0=ns)"})
            ax.set_title(f"LISA — {label}")
            ax.set_axis_off()
            plt.tight_layout()
            plt.savefig(out_dir / f"02_lisa_{label.lower()}.png", dpi=150, bbox_inches="tight")
            plt.close()
        print(f"  Saved: 02_lisa_worldpop.png, 02_lisa_meta.png")

        gi_wp = G_Local(log_wp, w, transform="r", star=True)
        gi_meta = G_Local(log_meta, w, transform="r", star=True)

        def _hotspot_class(zs, p_sim):
            out = np.zeros(len(zs), dtype=int)
            out[(zs > 0) & (p_sim < 0.05)] = 1
            out[(zs < 0) & (p_sim < 0.05)] = -1
            return out

        gdf_valid["hotspot_wp"] = _hotspot_class(gi_wp.Zs, gi_wp.p_sim)
        gdf_valid["hotspot_meta"] = _hotspot_class(gi_meta.Zs, gi_meta.p_sim)
        both_hot = (gdf_valid["hotspot_wp"] == 1) & (gdf_valid["hotspot_meta"] == 1)
        both_cold = (gdf_valid["hotspot_wp"] == -1) & (gdf_valid["hotspot_meta"] == -1)
        wp_only = (gdf_valid["hotspot_wp"] == 1) & (gdf_valid["hotspot_meta"] != 1)
        meta_only = (gdf_valid["hotspot_meta"] == 1) & (gdf_valid["hotspot_wp"] != 1)
        overlap_class = np.zeros(len(gdf_valid), dtype=int)
        overlap_class[both_hot] = 1
        overlap_class[both_cold] = -1
        overlap_class[wp_only] = 2
        overlap_class[meta_only] = 3
        gdf_valid["hotspot_overlap"] = overlap_class

        denom = both_hot.sum() + wp_only.sum() + meta_only.sum()
        jaccard_hotspot = both_hot.sum() / denom if denom > 0 else np.nan
        print(f"  Hotspot overlap: both={both_hot.sum()}, both_cold={both_cold.sum()}, WP_only={wp_only.sum()}, Meta_only={meta_only.sum()}")
        print(f"  Jaccard_hotspot = both / (both + WP_only + Meta_only) = {jaccard_hotspot:.4f}")
        hotspot_df = pd.DataFrame([
            {"Category": "Both hotspot", "Count": both_hot.sum()},
            {"Category": "Both coldspot", "Count": both_cold.sum()},
            {"Category": "WorldPop-only hotspot", "Count": wp_only.sum()},
            {"Category": "Meta-only hotspot", "Count": meta_only.sum()},
        ])
        hotspot_df.to_csv(out_dir / "02_hotspot_overlap.csv", index=False)
        pd.DataFrame([{"Jaccard_hotspot": jaccard_hotspot}]).to_csv(out_dir / "02_hotspot_jaccard.csv", index=False)
        print(f"  Saved: 02_hotspot_overlap.csv")

        gdf_map = _get_map_gdf(gdf_valid, region, region_bbox)
        from matplotlib.colors import ListedColormap
        fig, ax = plt.subplots(figsize=(8, 8))
        cmap_overlap = ListedColormap(["#4575b4", "#f0f0f0", "#d73027", "#fc8d59", "#998ec3"])
        gdf_map.plot(ax=ax, column="hotspot_overlap", categorical=True, legend=True, cmap=cmap_overlap,
                     legend_kwds={"title": "-1=both cold, 0=other, 1=both hot, 2=WP only, 3=Meta only"})
        ax.set_title("Hotspot overlap (Getis-Ord Gi*)")
        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(out_dir / "02_hotspot_overlap_map.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: 02_hotspot_overlap_map.png")
    except ImportError as e:
        print(f"  Skipped (install libpysal, esda): {e}")
    except Exception as e:
        print(f"  Spatial structure skipped: {e}")

    # -------------------------------------------------------------------------
    # 5. Allocation Residual — CORE DV
    # allocation_log_ratio = log(meta_share / worldpop_share)
    # -------------------------------------------------------------------------
    print("\n--- 5. Allocation Residual ---")

    allocation_log_ratio = np.log(meta_s / wp_s)

    print("allocation_residual = log(meta_share / worldpop_share):")
    print("  mean = {:.4f}, std = {:.4f}".format(allocation_log_ratio.mean(), allocation_log_ratio.std()))
    print("  (positive = Meta allocates a larger spatial share than WorldPop; negative = Meta allocates  a smaller spatial share than WorldPop)")

    # Store in GeoDataFrame — single canonical column for downstream
    gdf_valid = gdf_valid.copy()
    gdf_valid["allocation_residual"] = allocation_log_ratio

    gdf_map = _get_map_gdf(gdf_valid, region)
    def _residual_map(gdf, col, title, fname, vmin=None, vmax=None):
        if len(gdf) == 0:
            print(f"  Skipped {fname}: no features in map extent")
            return
        v = gdf[col].values
        if vmin is None or vmax is None:
            lim = max(abs(np.nanmin(v)), abs(np.nanmax(v)), 1e-6)
            vmin = vmin if vmin is not None else -lim
            vmax = vmax if vmax is not None else lim
        fig, ax = plt.subplots(figsize=(8, 8))
        gdf.plot(ax=ax, column=col, legend=True, cmap="RdBu_r", legend_kwds={"shrink": 0.6},
                 vmin=vmin, vmax=vmax)
        ax.set_title(title)
        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(out_dir / fname, dpi=150, bbox_inches="tight")
        plt.close()

    # Allocation residual map only
    map_configs = [
        ("allocation_residual", "Allocation residual: log(meta_share / worldpop_share)", "02_allocation_log_ratio.png", None, None),
    ]
    for col, title, fname, vmin, vmax in map_configs:
        _residual_map(gdf_map, col, title, fname, vmin, vmax)
    print("  Saved residual maps.")

    # Basemap versions (Sentinel-2 or satellite)
    try:
        if len(gdf_map) == 0:
            print("  Skipped basemap: no features in map extent")
        else:
            import contextily as ctx
            gdf_3857 = gdf_map.to_crs("EPSG:3857")
            # Try Sentinel-2 cloudless (EOX), fallback to Esri World Imagery
            basemap_sources = []
            try:
                from xyzservices import TileProvider
                s2_provider = TileProvider(
                    url="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/webmercator/{z}/{x}/{y}.jpeg",
                    attribution="Sentinel-2 cloudless by EOX (s2maps.eu)"
                )
                basemap_sources.append(("Sentinel-2", s2_provider))
            except Exception:
                pass
            if not basemap_sources:
                try:
                    basemap_sources.append(("Esri World Imagery", ctx.providers.Esri.WorldImagery))
                except Exception:
                    pass
            if not basemap_sources:
                basemap_sources.append(("OSM", ctx.providers.OpenStreetMap.Mapnik))

            basemap_name, basemap_source = basemap_sources[0]
            xmin, ymin, xmax, ymax = gdf_3857.total_bounds
            for col, title, fname, vmin, vmax in map_configs:
                v = gdf_map[col].values
                if vmin is None or vmax is None:
                    lim = max(abs(np.nanmin(v)), abs(np.nanmax(v)), 1e-6)
                    vmin, vmax = -lim, lim
                fig, ax = plt.subplots(figsize=(8, 8))
                ax.set_xlim(xmin, xmax)
                ax.set_ylim(ymin, ymax)
                ax.set_aspect("equal")
                ctx.add_basemap(ax, source=basemap_source, crs=gdf_3857.crs, zoom=12, alpha=0.9)
                gdf_3857.plot(ax=ax, column=col, legend=True, cmap="RdBu_r", legend_kwds={"shrink": 0.6},
                             vmin=vmin, vmax=vmax, alpha=0.65, edgecolor="white", linewidth=0.3)
                ax.set_title(f"{title} ({basemap_name} basemap)")
                ax.set_axis_off()
                plt.tight_layout()
                basemap_fname = fname.replace(".png", "_basemap.png")
                plt.savefig(out_dir / basemap_fname, dpi=150, bbox_inches="tight")
                plt.close()
            print(f"  Saved basemap versions: *_basemap.png ({basemap_name})")
    except ImportError:
        print("  (Install contextily for basemap versions: pip install contextily)")
    except Exception as e:
        print(f"  (Basemap failed: {e})")

    # Save gdf with residual for downstream use
    out_gpkg = out_dir / "harmonised_with_residual.gpkg"
    gdf_valid.to_file(out_gpkg, driver="GPKG")
    print(f"  Saved: {out_gpkg}")


    # Peripheral vs central (part of 5)

    # Compute peripheral zones: distance from centroid to study-area centroid (in metres)
    # Use centroid mean (faster than unary_union for many polygons)
    centroids = gdf_proj.geometry.centroid
    centroid_study = Point(centroids.x.mean(), centroids.y.mean())
    gdf_valid["dist_centroid"] = gdf_proj.geometry.centroid.distance(centroid_study)
    gdf_valid["Distance"] = gdf_valid["dist_centroid"]
    gdf_valid["area_km2"] = gdf_proj.geometry.area / 1e6
    gdf_valid["PopulationDensity"] = gdf_valid["worldpop_count"] / gdf_valid["area_km2"].clip(lower=1e-6)
    # Binary: peripheral = top 25% by distance
    gdf_valid["peripheral"] = gdf_valid["dist_centroid"] >= gdf_valid["dist_centroid"].quantile(0.75)

    # Test: Are allocation residuals larger in peripheral zones?
    res_peripheral = gdf_valid[gdf_valid["peripheral"]]["allocation_residual"].values
    res_central = gdf_valid[~gdf_valid["peripheral"]]["allocation_residual"].values
    t_peripheral, p_peripheral = stats.ttest_ind(res_peripheral, res_central)
    mw_stat, p_mannwhitney = stats.mannwhitneyu(res_peripheral, res_central, alternative="two-sided")
    mean_periph = res_peripheral.mean()
    mean_cent = res_central.mean()
    print(f"Peripheral zones (top 25% by distance from centroid):")
    print(f"  Mean allocation_residual (peripheral): {mean_periph:.4f}")
    print(f"  Mean allocation_residual (central):   {mean_cent:.4f}")
    print(f"  t-test p-value: {p_peripheral:.4f}")
    print(f"  Mann–Whitney U p-value: {p_mannwhitney:.4f}")
    diff = mean_periph - mean_cent
    print(f"  Difference (peripheral − central): {diff:.4f}")
    print("  Interpretation: negative = stronger Meta under-allocation in periphery")


    # Optional: auxiliary context (informal, rural, nightlight)
    if args:
        for path_arg, col, label in [
            (getattr(args, "informal", None), "informal", "Informal settlements"),
            (getattr(args, "rural", None), "rural", "Rural areas"),
        ]:
            if path_arg:
                merged = _load_context(gdf_valid, path_arg)
                if merged is not None and col in merged.columns:
                    run_contextual_test(merged, col, label)
        # Nightlight: treat as continuous; test high vs low (median split)
        nl_path = getattr(args, "nightlight", None) if args else None
        if nl_path:
            merged = _load_context(gdf_valid, nl_path)
            if merged is not None:
                cand = [c for c in merged.columns if "night" in c.lower() or "viirs" in c.lower() or c == "nightlight"]
                nc = cand[0] if cand else None
                if nc:
                    merged["low_nightlight"] = merged[nc] < merged[nc].median()
                    run_contextual_test(merged, "low_nightlight", "Low vs high nightlight")

    # -------------------------------------------------------------------------
    # 6. Agreement Typology — HH/LL/HL/LH (zscore of shares)
    # -------------------------------------------------------------------------
    print("\n--- 6. Agreement Typology (zscore shares) ---")
    from matplotlib.colors import ListedColormap

    z_wp = (wp_s - wp_s.mean()) / (wp_s.std() + 1e-10)
    z_meta = (meta_s - meta_s.mean()) / (meta_s.std() + 1e-10)

    # Version A: Median split (robust, balanced)
    med_wp = np.median(z_wp)
    med_meta = np.median(z_meta)
    typology_med = np.zeros(len(wp_s), dtype=int)  # 1=HH, 2=LH, 3=LL, 4=HL
    typology_med[(z_wp >= med_wp) & (z_meta >= med_meta)] = 1
    typology_med[(z_wp < med_wp) & (z_meta >= med_meta)] = 2
    typology_med[(z_wp < med_wp) & (z_meta < med_meta)] = 3
    typology_med[(z_wp >= med_wp) & (z_meta < med_meta)] = 4
    gdf_valid["agreement_typology_median"] = typology_med
    print(f"  Median split: HH={(typology_med==1).sum()}, LH={(typology_med==2).sum()}, LL={(typology_med==3).sum()}, HL={(typology_med==4).sum()}")

    # Version B: Quartile split (focuses on strong disagreements)
    q75_wp, q25_wp = np.percentile(z_wp, 75), np.percentile(z_wp, 25)
    q75_meta, q25_meta = np.percentile(z_meta, 75), np.percentile(z_meta, 25)
    typology_q = np.zeros(len(wp_s), dtype=int)  # 0=other, 1=HH, 2=LH, 3=LL, 4=HL
    typology_q[(z_wp >= q75_wp) & (z_meta >= q75_meta)] = 1
    typology_q[(z_wp <= q25_wp) & (z_meta >= q75_meta)] = 2
    typology_q[(z_wp <= q25_wp) & (z_meta <= q25_meta)] = 3
    typology_q[(z_wp >= q75_wp) & (z_meta <= q25_meta)] = 4
    gdf_valid["agreement_typology_quartile"] = typology_q
    print(f"  Quartile split: HH={(typology_q==1).sum()}, LH={(typology_q==2).sum()}, LL={(typology_q==3).sum()}, HL={(typology_q==4).sum()}, other={(typology_q==0).sum()}")

    # Sensitivity table: area and pop shares by class (for both versions)
    # Use wp_s, meta_s (aligned with filtered gdf_valid) — wp_v/meta_v may have different length after spatial filter
    gdf_proj_typ = gdf_valid.to_crs("EPSG:32737")
    area_cells = gdf_proj_typ.geometry.area.values / 1e6  # km²
    total_area = area_cells.sum()
    total_wp_s = wp_s.sum()
    total_meta_s = meta_s.sum()

    def _sensitivity_rows(typ_arr, label):
        rows = []
        for cls, name in [(1, "HH"), (2, "LH"), (3, "LL"), (4, "HL")]:
            mask = typ_arr == cls
            n = mask.sum()
            area_share = area_cells[mask].sum() / total_area if total_area > 0 else np.nan
            wp_share = wp_s[mask].sum() / total_wp_s if total_wp_s > 0 else np.nan
            meta_share = meta_s[mask].sum() / total_meta_s if total_meta_s > 0 else np.nan
            rows.append({"Version": label, "Class": name, "N_cells": n, "Area_share": area_share, "WP_pop_share": wp_share, "Meta_pop_share": meta_share})
        if "quartile" in label:
            mask_other = typ_arr == 0
            rows.append({"Version": label, "Class": "other", "N_cells": mask_other.sum(), "Area_share": area_cells[mask_other].sum()/total_area if total_area > 0 else np.nan,
                       "WP_pop_share": wp_s[mask_other].sum()/total_wp_s if total_wp_s > 0 else np.nan, "Meta_pop_share": meta_s[mask_other].sum()/total_meta_s if total_meta_s > 0 else np.nan})
        return rows

    sens_rows = _sensitivity_rows(typology_med, "median") + _sensitivity_rows(typology_q, "quartile")
    sens_df = pd.DataFrame(sens_rows)
    sens_df.to_csv(out_dir / "02_agreement_typology_sensitivity.csv", index=False)
    print(f"  Saved: 02_agreement_typology_sensitivity.csv")

    gdf_map = _get_map_gdf(gdf_valid, region)
    # Map A: median split
    if len(gdf_map) == 0:
        print("  Skipped agreement typology maps: no features in map extent")
    else:
        fig, ax = plt.subplots(figsize=(8, 8))
        cmap_typ = ListedColormap(["#d73027", "#fc8d59", "#91cf60", "#1a9850"])
        gdf_map.plot(ax=ax, column="agreement_typology_median", categorical=True, legend=True, cmap=cmap_typ,
                     legend_kwds={"title": "1=HH, 2=LH, 3=LL, 4=HL"})
        ax.set_title("Agreement typology (median split)")
        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(out_dir / "02_agreement_typology_median.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: 02_agreement_typology_median.png")

        # Map B: quartile split (use 5 colors: other=gray)
        fig, ax = plt.subplots(figsize=(8, 8))
        cmap_q = ListedColormap(["#d73027", "#fc8d59", "#91cf60", "#1a9850", "#e0e0e0"])
        gdf_map.plot(ax=ax, column="agreement_typology_quartile", categorical=True, legend=True, cmap=cmap_q,
                     legend_kwds={"title": "1=HH, 2=LH, 3=LL, 4=HL, 0=other"})
        ax.set_title("Agreement typology (quartile split — strong disagreements)")
        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(out_dir / "02_agreement_typology_quartile.png", dpi=150, bbox_inches="tight")
        plt.close()
        print(f"  Saved: 02_agreement_typology_quartile.png")

    # Keep legacy column for downstream compatibility
    gdf_valid["agreement_typology"] = typology_med

    # Save gdf with all columns (residuals, spatial structure, typology) for downstream
    gdf_valid.to_file(out_dir / "harmonised_with_residual.gpkg", driver="GPKG")

    # -------------------------------------------------------------------------
    # Summary & Table 1
    # -------------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)
    print(f"Spearman ρ (log shares): {r_spearman_log:.4f}")
    print(f"Pearson r (log shares):  {r_pearson_log:.4f}")
    print(f"KS p-value: {ks_pval:.2e}")
    print(f"EMD: {emd:.4f}")
    print(f"Gini WP / Meta / ΔGini: {gini_wp:.4f} / {gini_meta:.4f} / {delta_gini:.4f}")
    print(f"Mean allocation_residual: {allocation_log_ratio.mean():.4f}")
    print(f"Peripheral vs central allocation residual: t-test p={p_peripheral:.4f}, Mann–Whitney p={p_mannwhitney:.4f}")


    # Table 1 — Meta vs WorldPop comparison metrics
    def _stars(p):
        if p < 0.001: return "***"
        if p < 0.01: return "**"
        if p < 0.05: return "*"
        return ""
    import pandas as pd
    tbl1 = pd.DataFrame([
        ("Number of quadkeys", valid.sum(), "—"),
        ("Spearman ρ (log shares)", f"{r_spearman_log:.3f}", "log(meta_share) vs log(wp_share)"),
        ("Pearson r (log shares)", f"{r_pearson_log:.3f}", "log(meta_share) vs log(wp_share)"),
        ("KS statistic", f"{ks_stat:.3f}", "shares normalized [0,1]"),
        ("KS p-value", "< 0.001" if ks_pval < 0.001 else f"{ks_pval:.3f}", "shares normalized [0,1]"),
        ("Earth Mover's Distance", f"{emd:.3f}", "shares normalized [0,1]"),
        ("Gini (WorldPop)", f"{gini_wp:.3f}", "spatial shares"),
        ("Gini (Meta baseline)", f"{gini_meta:.3f}", "spatial shares"),
        ("ΔGini (Meta − WP)", f"{delta_gini:.3f}", "spatial shares"),
        ("Mean allocation_residual", f"{allocation_log_ratio.mean():.3f}", "log(meta_share/wp_share)"),
    ], columns=["Metric", "Value", "Input"])

    tbl1.to_csv(out_dir / "Table1_meta_worldpop_metrics.csv", index=False)
    print(f"\n  Saved: {out_dir / 'Table1_meta_worldpop_metrics.csv'}")



def run_contextual_test(gdf_valid, context_col, label):
    """T-test: are residuals different in context vs not?"""
    if context_col not in gdf_valid.columns:
        return
    mask = gdf_valid[context_col].astype(bool)
    if mask.sum() < 3 or (~mask).sum() < 3:
        print(f"  {label}: insufficient samples, skipping")
        return
    res_in = gdf_valid[mask]["allocation_residual"].values
    res_out = gdf_valid[~mask]["allocation_residual"].values
    t, p = stats.ttest_ind(res_in, res_out)
    print(f"  {label}: mean residual (in)={res_in.mean():.4f}, (out)={res_out.mean():.4f}, p={p:.4f}")


def parse_args():
    p = argparse.ArgumentParser(description="Compare Meta and WorldPop (post-harmonisation)")
    p.add_argument("-i", "--input", type=Path, default=None, help="01 harmonised GPKG (default: from --region or outputs/01/)")
    p.add_argument("-o", "--output-dir", type=Path, default=None, help="Output root (default: outputs/ or outputs/{region}/)")
    p.add_argument("--region", type=str, default=None,
                   help="Region code from config (PHI, KEN, MEX). Sets I/O paths and map zoom. Auto-detect if not set.")
    # p.add_argument("--normalize", action="store_true", default=True, help="Global-scaling: add scaled_log_ratio, scaled_relative (default: True)")
    # p.add_argument("--no-normalize", dest="normalize", action="store_false", help="Skip global-scaling normalization")
    p.add_argument("--informal", type=Path, default=None, help="GPKG/CSV with quadkey + informal (0/1)")
    p.add_argument("--rural", type=Path, default=None, help="GPKG/CSV with quadkey + rural (0/1)")
    p.add_argument("--nightlight", type=Path, default=None, help="GPKG/CSV with quadkey + nightlight value")
    return p.parse_args()


def main():
    args = parse_args()

    # Resolve input/output from --region
    if args.region:
        try:
            import region_config
            cfg = region_config.get_region_config(args.region)
            # When clip_shape is set: use data extent for maps (data is already clipped)
            args.region_bbox = None if cfg.get("clip_shape") else cfg.get("map_bbox")
            args.region_label = cfg.get("map_bbox_label") or cfg.get("name") or args.region
            if args.input is None:
                args.input = region_config.get_output_dir(args.region, "01") / "harmonised_meta_worldpop.gpkg"
            out_dir = region_config.get_output_dir(args.region, "02")
        except (ImportError, ValueError) as e:
            raise SystemExit(f"Invalid --region {args.region}: {e}")
    else:
        args.region_bbox = None
        args.region_label = None
        args.input = args.input or DEFAULT_INPUT
        out_dir = (args.output_dir or PROJECT_ROOT / "outputs") / "02"

    if not args.input.exists():
        raise FileNotFoundError(f"Run 01_harmonise_datasets.py first. Missing: {args.input}")
    out_dir.mkdir(parents=True, exist_ok=True)
    run_comparison(args.input, out_dir, args)


if __name__ == "__main__":
    main()
