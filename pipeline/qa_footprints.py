#!/usr/bin/env python3
"""
Technical QA for event-footprint alignment (no modelling).

Writes tables under outputs/footprints/qa/ and maps under figure/footprints/qa/.

  python pipeline/qa_footprints.py --footprint KEN
  python pipeline/qa_footprints.py --footprints KEN,PHL
  python pipeline/qa_footprints.py
      # every configured footprint that has a geographies parquet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import geopandas as gpd
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))

import region_config
from ghsl_utils import SMOD_CLASS_COLLAPSE

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = PROJECT_ROOT / "outputs" / "footprints" / "qa"
FIG_DIR = PROJECT_ROOT / "figure" / "footprints" / "qa"

GHSL_ORDER = ["Urban centre", "Town / semi-dense", "Rural", "Water"]


def city_reproduction_specs(codes: list[str]) -> list[dict]:
    """One overlay check per study city listed on a footprint (same rule for every country)."""
    specs = []
    label_to_code = {}
    for code in region_config.list_cities():
        try:
            lab = region_config.display_label(code)
        except Exception:
            continue
        label_to_code[lab] = code
        cfg = region_config.get_region_config(code)
        if cfg.get("city_label"):
            label_to_code[str(cfg["city_label"])] = code
    for fp in codes:
        raw = (region_config.load_regions().get("footprints") or {}).get(fp) or {}
        for name in (raw.get("city_boundaries") or {}):
            old = label_to_code.get(name)
            if old:
                specs.append({"footprint": fp, "city_boundary": name, "old_region": old})
            else:
                specs.append({"footprint": fp, "city_boundary": name, "old_region": None})
    return specs


def _load_geog(code: str) -> gpd.GeoDataFrame:
    path = region_config.get_geographies_parquet(code)
    gdf = gpd.read_parquet(path)
    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")
    gdf["quadkey"] = gdf["quadkey"].astype(str)
    return gdf


def _valid_mask(a: np.ndarray, nodata) -> np.ndarray:
    m = np.isfinite(a)
    if nodata is not None:
        m &= a != nodata
    m &= a > -1e20
    return m


def raster_sum(path: Path) -> float:
    import rasterio

    total = 0.0
    with rasterio.open(path) as src:
        nodata = src.nodata
        for _, window in src.block_windows(1):
            a = src.read(1, window=window)
            m = _valid_mask(a, nodata)
            total += float(a[m].sum())
    return total


def worldpop_in_zones(gdf: gpd.GeoDataFrame, raster_path: Path) -> dict:
    """Sum WorldPop pixels overlapping aligned zones (all_touched True/False)."""
    import rasterio
    from rasterio.features import rasterize
    from rasterio.windows import from_bounds

    with rasterio.open(raster_path) as src:
        bounds = gdf.total_bounds
        window = from_bounds(*bounds, transform=src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window, boundless=True, fill_value=src.nodata if src.nodata is not None else 0)
        transform = src.window_transform(window)
        nodata = src.nodata
        shapes = [(geom, 1) for geom in gdf.geometry if geom is not None and not geom.is_empty]
        mask_at = rasterize(
            shapes, out_shape=data.shape, transform=transform, all_touched=True, fill=0, dtype="uint8"
        )
        mask_ct = rasterize(
            shapes, out_shape=data.shape, transform=transform, all_touched=False, fill=0, dtype="uint8"
        )
        valid = _valid_mask(data, nodata)
        sum_at = float(data[valid & (mask_at == 1)].sum())
        sum_ct = float(data[valid & (mask_ct == 1)].sum())
        n_pix_at = int((valid & (mask_at == 1)).sum())
        n_pix_ct = int((valid & (mask_ct == 1)).sum())
    zonal = float(gdf["worldpop_count"].fillna(0).sum())
    return {
        "worldpop_zonal_sum": zonal,
        "worldpop_raster_all_touched": sum_at,
        "worldpop_raster_centroid_touch": sum_ct,
        "rel_diff_all_touched": (zonal - sum_at) / sum_at if sum_at else np.nan,
        "rel_diff_centroid_touch": (zonal - sum_ct) / sum_ct if sum_ct else np.nan,
        "n_pixels_all_touched": n_pix_at,
        "n_pixels_centroid_touch": n_pix_ct,
    }


def smod_class_counts(arr: np.ndarray) -> dict:
    counts = {k: 0 for k in GHSL_ORDER}
    flat = arr[np.isfinite(arr) & (arr != 0)]
    for v in flat.astype(int):
        cls = SMOD_CLASS_COLLAPSE.get(int(v))
        if cls in counts:
            counts[cls] += 1
    return counts


def smod_shares_in_polygons(smod_path: Path, geoms, bounds) -> dict:
    """SMOD pixel class counts inside polygons, rasterized onto the SMOD grid."""
    import rasterio
    from rasterio.features import rasterize
    from rasterio.windows import from_bounds

    with rasterio.open(smod_path) as src:
        window = from_bounds(*bounds, transform=src.transform)
        window = window.round_offsets().round_lengths()
        data = src.read(1, window=window, boundless=True, fill_value=0)
        transform = src.window_transform(window)
        shapes = [(g, 1) for g in geoms if g is not None and not getattr(g, "is_empty", False)]
        mask = rasterize(
            shapes, out_shape=data.shape, transform=transform, all_touched=True, fill=0, dtype="uint8"
        )
        inside = data[(mask == 1) & (data != 0) & np.isfinite(data)]
    counts = smod_class_counts(inside)
    n = sum(counts.values())
    shares = {f"pct_{k}": (counts[k] / n if n else np.nan) for k in GHSL_ORDER}
    return {"n_smod_pixels": n, **counts, **shares}


def area_km2(gdf: gpd.GeoDataFrame) -> float:
    crs = gdf.estimate_utm_crs()
    return float(gdf.to_crs(crs).geometry.area.sum() / 1e6)


def qa_technical(code: str, gdf: gpd.GeoDataFrame, cfg: dict) -> dict:
    n = len(gdf)
    qk_dup = int(gdf["quadkey"].duplicated().sum())
    geom_wkb = gdf.geometry.to_wkb()
    geom_dup = int(pd.Series(geom_wkb).duplicated().sum())
    invalid = int((~gdf.geometry.is_valid).sum())
    empty = int(gdf.geometry.is_empty.sum())

    meta_na = int(gdf["meta_baseline"].isna().sum())
    wp_na = int(gdf["worldpop_count"].isna().sum())
    grdi_na = int(gdf["poverty_mean"].isna().sum()) if "poverty_mean" in gdf.columns else n
    ghsl_na = int(gdf["ghsl_class"].isna().sum()) if "ghsl_class" in gdf.columns else n

    meta_path = cfg.get("meta")
    n_meta_src = np.nan
    if meta_path and Path(meta_path).exists():
        meta_src = gpd.read_file(meta_path)
        n_meta_src = len(meta_src)

    unclassified = int((gdf["ghsl_class"].isna() | (gdf["ghsl_class"] == "")).sum()) if "ghsl_class" in gdf.columns else n
    ghsl_counts = gdf["ghsl_class"].value_counts(dropna=False).to_dict() if "ghsl_class" in gdf.columns else {}
    n_classes = sum(int(ghsl_counts.get(k, 0) or 0) for k in GHSL_ORDER)

    return {
        "footprint": code,
        "n": n,
        "n_unique_quadkeys": int(gdf["quadkey"].nunique()),
        "duplicate_quadkeys": qk_dup,
        "duplicate_geometries": geom_dup,
        "invalid_geometries": invalid,
        "empty_geometries": empty,
        "meta_na": meta_na,
        "meta_na_pct": meta_na / n if n else np.nan,
        "worldpop_na": wp_na,
        "worldpop_na_pct": wp_na / n if n else np.nan,
        "grdi_na": grdi_na,
        "grdi_na_pct": grdi_na / n if n else np.nan,
        "ghsl_na": ghsl_na,
        "ghsl_na_pct": ghsl_na / n if n else np.nan,
        "unique_quadkeys_eq_n": int(gdf["quadkey"].nunique()) == n,
        "n_meta_source": n_meta_src,
        "n_lost_in_harmonise": (n_meta_src - n) if pd.notna(n_meta_src) else np.nan,
        "n_ghsl_classified": n_classes,
        "n_unclassified": unclassified,
        "ghsl_sum_equals_n": n_classes + unclassified == n,
    }


def city_reproduction(spec: dict, gdf: gpd.GeoDataFrame) -> dict:
    city = spec["city_boundary"]
    overlay = gdf[gdf.get("city_boundary") == city].copy() if "city_boundary" in gdf.columns else gdf.iloc[0:0].copy()
    old_region = spec.get("old_region")
    old_path = None
    if old_region:
        old_path = region_config.find_artifact(old_region, "01", "harmonised_meta_worldpop.gpkg")
    row = {
        "footprint": spec["footprint"],
        "city": city,
        "old_region": old_region,
        "n_new_overlay": len(overlay),
        "old_gpkg_exists": bool(old_path and old_path.exists()),
    }
    if overlay.empty:
        return row

    def _summarise(frame, prefix):
        meta = frame["meta_baseline"] if "meta_baseline" in frame.columns else pd.Series(dtype=float)
        wp = frame["worldpop_count"] if "worldpop_count" in frame.columns else pd.Series(dtype=float)
        pov = frame["poverty_mean"] if "poverty_mean" in frame.columns else pd.Series(dtype=float)
        both = meta.notna() & wp.notna() & (wp > 0) & (meta > 0)
        log_r = np.log((meta.fillna(0) + 1) / (wp.fillna(0) + 1))
        out = {
            f"{prefix}_n": len(frame),
            f"{prefix}_meta_sum": float(meta.sum(skipna=True)),
            f"{prefix}_wp_sum": float(wp.sum(skipna=True)),
            f"{prefix}_grdi_mean": float(pov.mean()) if pov.notna().any() else np.nan,
            f"{prefix}_grdi_median": float(pov.median()) if pov.notna().any() else np.nan,
            f"{prefix}_log_ratio_mean": float(log_r[both].mean()) if both.any() else np.nan,
            f"{prefix}_log_ratio_median": float(log_r[both].median()) if both.any() else np.nan,
            f"{prefix}_log_ratio_std": float(log_r[both].std()) if both.any() else np.nan,
        }
        return out, log_r, both

    new_s, new_log, new_both = _summarise(overlay, "new")
    row.update(new_s)

    if old_path is None or not old_path.exists():
        row["status"] = "old city 01 missing" if old_region else "no matching city region"
        return row

    old = gpd.read_file(old_path)
    old["quadkey"] = old["quadkey"].astype(str)
    old_s, old_log, old_both = _summarise(old, "old")
    row.update(old_s)
    row["n_old"] = len(old)
    row["n_diff"] = row["n_new_overlay"] - row["n_old"]

    merged = overlay.merge(
        old[["quadkey", "meta_baseline", "worldpop_count", "poverty_mean"]].rename(
            columns={
                "meta_baseline": "meta_old",
                "worldpop_count": "wp_old",
                "poverty_mean": "grdi_old",
            }
        ),
        on="quadkey",
        how="outer",
        indicator=True,
    )
    row["n_matched"] = int((merged["_merge"] == "both").sum())
    row["n_only_new"] = int((merged["_merge"] == "left_only").sum())
    row["n_only_old"] = int((merged["_merge"] == "right_only").sum())
    both = merged[merged["_merge"] == "both"].copy()
    if len(both):
        row["max_abs_diff_meta"] = float((both["meta_baseline"] - both["meta_old"]).abs().max())
        row["max_abs_diff_wp"] = float((both["worldpop_count"] - both["wp_old"]).abs().max())
        if "poverty_mean" in both.columns and "grdi_old" in both.columns:
            row["max_abs_diff_grdi"] = float((both["poverty_mean"] - both["grdi_old"]).abs().max())
        row["meta_sum_matched_new"] = float(both["meta_baseline"].sum())
        row["meta_sum_matched_old"] = float(both["meta_old"].sum())
        row["wp_sum_matched_new"] = float(both["worldpop_count"].sum())
        row["wp_sum_matched_old"] = float(both["wp_old"].sum())
        new_lr = np.log((both["meta_baseline"].fillna(0) + 1) / (both["worldpop_count"].fillna(0) + 1))
        old_lr = np.log((both["meta_old"].fillna(0) + 1) / (both["wp_old"].fillna(0) + 1))
        row["residual_mean_diff"] = float(new_lr.mean() - old_lr.mean())
        if len(both) > 10 and new_lr.notna().sum() > 10:
            ks = stats.ks_2samp(new_lr.dropna(), old_lr.dropna())
            row["residual_ks_stat"] = float(ks.statistic)
            row["residual_ks_p"] = float(ks.pvalue)
        values_ok = (
            row["n_diff"] == 0
            and row["n_matched"] == row["n_old"]
            and row["max_abs_diff_meta"] < 1e-4
            and row["max_abs_diff_wp"] < 1e-2
        )
        row["status"] = "PASS" if values_ok else "CHECK"
    else:
        row["status"] = "no overlapping quadkeys"
    return row


def ghsl_cell_table(code: str, gdf: gpd.GeoDataFrame) -> pd.DataFrame:
    rows = []
    for cls in GHSL_ORDER + [None]:
        if cls is None:
            sub = gdf[gdf["ghsl_class"].isna()]
            label = "Unclassified"
        else:
            sub = gdf[gdf["ghsl_class"] == cls]
            label = cls
        if sub.empty and cls is None:
            continue
        meta = sub["meta_baseline"]
        wp = sub["worldpop_count"]
        pov = sub["poverty_mean"] if "poverty_mean" in sub.columns else pd.Series(dtype=float)
        both = meta.notna() & wp.notna() & (wp > 0) & (meta > 0)
        diff = meta - wp
        ratio = np.where((wp > 0) & wp.notna() & meta.notna(), meta / wp, np.nan)
        rho = np.nan
        if both.sum() >= 5:
            rho, _ = stats.spearmanr(meta[both], wp[both])
        rows.append(
            {
                "footprint": code,
                "settlement": label,
                "n": len(sub),
                "meta_total": float(meta.sum(skipna=True)),
                "worldpop_total": float(wp.sum(skipna=True)),
                "grdi_mean": float(pov.mean()) if len(sub) and pov.notna().any() else np.nan,
                "grdi_median": float(pov.median()) if len(sub) and pov.notna().any() else np.nan,
                "diff_meta_wp": float(diff.sum(skipna=True)),
                "ratio_totals": float(meta.sum(skipna=True) / wp.sum(skipna=True)) if wp.sum(skipna=True) else np.nan,
                "median_ratio": float(pd.Series(ratio).median()) if len(sub) else np.nan,
                "mad": float(np.nanmedian(np.abs(meta - wp))) if len(sub) else np.nan,
                "spearman_rho": float(rho) if rho == rho else np.nan,
            }
        )
    return pd.DataFrame(rows)


def representativeness(code: str, gdf: gpd.GeoDataFrame, cfg: dict, cons: dict) -> dict:
    smod = cfg.get("ghsl_smod")
    national_wp = raster_sum(cfg["worldpop"])
    fp_wp = float(gdf["worldpop_count"].fillna(0).sum())
    fp_area = area_km2(gdf)

    cell_counts = {k: int((gdf["ghsl_class"] == k).sum()) for k in GHSL_ORDER}
    n = len(gdf)
    row = {
        "footprint": code,
        "n_cells": n,
        "footprint_area_km2": fp_area,
        "footprint_worldpop": fp_wp,
        "national_worldpop": national_wp,
        "pop_share": fp_wp / national_wp if national_wp else np.nan,
    }
    for k in GHSL_ORDER:
        row[f"cells_{k}"] = cell_counts[k]
        row[f"cell_pct_{k}"] = cell_counts[k] / n if n else np.nan

    if smod and Path(smod).exists():
        fp_smod = smod_shares_in_polygons(smod, gdf.geometry, gdf.total_bounds)
        for k in GHSL_ORDER:
            row[f"fp_smod_pct_{k}"] = fp_smod.get(f"pct_{k}", np.nan)
        # Same national comparator for every country: WorldPop raster extent, land pixels via WP>0.
        import rasterio
        from rasterio.enums import Resampling
        from rasterio.warp import reproject
        from rasterio.windows import from_bounds

        with rasterio.open(cfg["worldpop"]) as wp, rasterio.open(smod) as sm:
            window = from_bounds(*wp.bounds, transform=sm.transform)
            window = window.round_offsets().round_lengths()
            smod_win = sm.read(1, window=window, boundless=True, fill_value=0)
            dest = np.zeros(smod_win.shape, dtype="float32")
            reproject(
                source=rasterio.band(wp, 1),
                destination=dest,
                src_transform=wp.transform,
                src_crs=wp.crs,
                dst_transform=sm.window_transform(window),
                dst_crs=sm.crs,
                resampling=Resampling.average,
                src_nodata=wp.nodata,
                dst_nodata=0,
            )
            land = dest > 0
            counts = smod_class_counts(smod_win[land])
            n_pix = sum(counts.values())
            for k in GHSL_ORDER:
                row[f"nat_smod_pct_{k}"] = counts[k] / n_pix if n_pix else np.nan
                row[f"smod_pp_diff_{k}"] = row[f"fp_smod_pct_{k}"] - row[f"nat_smod_pct_{k}"]
    row.update({f"cons_{k}": v for k, v in cons.items()})
    return row


def plot_ghsl_map(code: str, gdf: gpd.GeoDataFrame, dest: Path) -> None:
    colors = {
        "Urban centre": "#c0392b",
        "Town / semi-dense": "#e67e22",
        "Rural": "#27ae60",
        "Water": "#2980b9",
    }
    from matplotlib.patches import Patch

    fig, ax = plt.subplots(figsize=(8, 7))
    for cls, color in colors.items():
        sub = gdf[gdf["ghsl_class"] == cls]
        if sub.empty:
            continue
        sub.plot(ax=ax, color=color, linewidth=0)
    ax.set_title(f"{code}: GHSL class on Meta footprint")
    ax.set_xlabel("Longitude")
    ax.set_ylabel("Latitude")
    ax.legend(
        handles=[Patch(facecolor=colors[k], edgecolor="none", label=k) for k in colors],
        loc="lower left",
        frameon=True,
        fontsize=8,
    )
    ax.set_aspect("equal")
    fig.tight_layout()
    fig.savefig(dest, dpi=140, bbox_inches="tight")
    plt.close(fig)


def main():
    p = argparse.ArgumentParser(description="QA tables for footprint alignment")
    p.add_argument(
        "--footprint",
        type=str,
        default=None,
        help="One footprint code (e.g. KEN). Same idea as ./run --region for cities.",
    )
    p.add_argument(
        "--footprints",
        type=str,
        default=None,
        help="Comma-separated codes. Default: every configured footprint that has a geographies parquet.",
    )
    args = p.parse_args()
    if args.footprint and args.footprints:
        raise SystemExit("Use --footprint COUNTRY or --footprints A,B — not both.")
    if args.footprint:
        codes = [args.footprint.strip()]
    elif args.footprints:
        codes = [c.strip() for c in args.footprints.split(",") if c.strip()]
    else:
        codes = region_config.footprints_with_geographies()
        if not codes:
            raise SystemExit(
                "No geographies parquet found. Run one country first, e.g.\n"
                "  bash pipeline/run_footprint_prep.sh KEN\n"
                "  python pipeline/qa_footprints.py --footprint KEN"
            )
    for c in codes:
        try:
            region_config.reject_legacy_phi(c)
        except ValueError as e:
            raise SystemExit(str(e))
    available = region_config.list_footprints()
    unknown = [c for c in codes if c not in available]
    if unknown:
        raise SystemExit(f"Unknown footprint {unknown}. Available: {region_config.list_footprints()}")
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tech_rows, cons_rows, city_rows, ghsl_parts, rep_rows = [], [], [], [], []

    for code in codes:
        print(f"\n=== {code} ===")
        cfg = region_config.get_footprint_config(code)
        gdf = _load_geog(code)
        tech = qa_technical(code, gdf, cfg)
        tech_rows.append(tech)
        print(f"  n={tech['n']} dup_qk={tech['duplicate_quadkeys']} GHSL NA={tech['ghsl_na']}")

        print("  WorldPop conservation...")
        cons = worldpop_in_zones(gdf, cfg["worldpop"])
        cons["footprint"] = code
        cons["meta_source_n"] = tech["n_meta_source"]
        cons["meta_aligned_n"] = tech["n"]
        cons_rows.append(cons)
        print(f"    zonal={cons['worldpop_zonal_sum']:.0f} raster_all_touched={cons['worldpop_raster_all_touched']:.0f}")

        print("  Representativeness (national WorldPop + SMOD)...")
        rep = representativeness(code, gdf, cfg, cons)
        rep_rows.append(rep)

        ghsl_parts.append(ghsl_cell_table(code, gdf))
        FIG_DIR.mkdir(parents=True, exist_ok=True)
        map_path = FIG_DIR / f"{code}_ghsl_map.png"
        plot_ghsl_map(code, gdf, map_path)
        print(f"  map → {map_path}")

    for spec in city_reproduction_specs(codes):
        if spec["footprint"] not in codes:
            continue
        gdf = _load_geog(spec["footprint"])
        row = city_reproduction(spec, gdf)
        city_rows.append(row)
        print(f"  city {spec['city_boundary']}: {row.get('status')} n_new={row.get('n_new_overlay')} n_old={row.get('n_old')}")

    tech_df = pd.DataFrame(tech_rows)
    cons_df = pd.DataFrame(cons_rows)
    city_df = pd.DataFrame(city_rows)
    ghsl_df = pd.concat(ghsl_parts, ignore_index=True)
    rep_df = pd.DataFrame(rep_rows)

    tech_df.to_csv(OUT_DIR / "qa_technical.csv", index=False)
    cons_df.to_csv(OUT_DIR / "qa_conservation.csv", index=False)
    city_df.to_csv(OUT_DIR / "qa_city_reproduction.csv", index=False)
    ghsl_df.to_csv(OUT_DIR / "qa_by_ghsl_class.csv", index=False)
    rep_df.to_csv(OUT_DIR / "qa_representativeness.csv", index=False)

    payload = {
        "technical": tech_df.replace({np.nan: None}).to_dict(orient="records"),
        "conservation": cons_df.replace({np.nan: None}).to_dict(orient="records"),
        "cities": city_df.replace({np.nan: None}).to_dict(orient="records"),
        "by_ghsl": ghsl_df.replace({np.nan: None}).to_dict(orient="records"),
        "representativeness": rep_df.replace({np.nan: None}).to_dict(orient="records"),
    }
    with open(OUT_DIR / "qa_results.json", "w") as f:
        json.dump(payload, f, indent=2, default=str)

    print(f"\nWrote {OUT_DIR}")


if __name__ == "__main__":
    main()
