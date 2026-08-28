#!/usr/bin/env python3
"""
01b — Meta coverage QA on an independently defined city grid.

Step 01 starts from published Meta tiles, so unpublished cells never appear.
This step builds the zoom-level city grid from the clip polygon (same tiles as
03f-D), keeps cells with WorldPop > 0 and valid GRDI, and measures how much
of that eligible grid has published Meta.

    C_c = N_published / N_grid

N_grid     = eligible cells (WP>0 and GRDI valid), independent of Meta
N_published = eligible cells with published Meta (step-01 layer, count > 0)
N_missing   = eligible cells with unpublished Meta
C_c         = Meta coverage of the eligible grid

Usage:
  python pipeline/01b_meta_coverage_qa.py --region ZAF_CapeTown

Outputs:
  outputs/.../01b_coverage/Table_meta_coverage.csv
  data/processed/.../01b_coverage/independent_grid.gpkg
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
import independent_grid
import region_config

OUT_SUBDIR = "01b_coverage"


def parse_args():
    p = argparse.ArgumentParser(description="01b — Meta coverage QA on the independent city grid")
    p.add_argument("--region", type=str, default=None)
    region_config.add_footprint_arg(p)
    return p.parse_args()


def _median(series):
    v = pd.to_numeric(series, errors="coerce")
    v = v[np.isfinite(v)]
    return float(v.median()) if len(v) else np.nan


def main():
    args = parse_args()
    if getattr(args, "footprint", None):
        print("01b skipped (city clip grid; not run on footprints)")
        return
    if not args.region:
        raise SystemExit("01b requires --region CITY (e.g. ZAF_CapeTown)")

    paths = independent_grid.resolve_city_grid_inputs(region=args.region)
    if paths is None:
        raise SystemExit(f"01b needs a city region, got {args.region!r}")

    out = region_config.step_paths(args.region, OUT_SUBDIR)

    print("=" * 60)
    print("01b — Meta coverage QA")
    print("=" * 60)
    print(f"  Region: {paths['code']}")

    grid = independent_grid.build_independent_city_grid(paths)
    grid = independent_grid.annotate_coverage(grid)
    zoom = len(str(grid["quadkey"].iloc[0])) if len(grid) else np.nan

    elig = grid.loc[grid["eligible"]].copy()
    pub = elig.loc[elig["published"]]
    miss = elig.loc[~elig["published"]]
    n_grid = int(len(elig))
    n_published = int(len(pub))
    n_missing = int(len(miss))
    c_c = (n_published / n_grid) if n_grid else np.nan

    row = {
        "region": paths["code"],
        "city": region_config.display_label(paths["code"]),
        "zoom": int(zoom) if np.isfinite(zoom) else np.nan,
        "N_grid": n_grid,
        "N_published": n_published,
        "N_missing": n_missing,
        "C_c": c_c,
        "median_WP_published": _median(pub["worldpop_count"]) if n_published else np.nan,
        "median_WP_missing": _median(miss["worldpop_count"]) if n_missing else np.nan,
        "median_GRDI_published": _median(pub["poverty_mean"]) if n_published else np.nan,
        "median_GRDI_missing": _median(miss["poverty_mean"]) if n_missing else np.nan,
    }

    if n_grid:
        print(
            f"  Eligible grid (WP>0, GRDI valid): N_grid={n_grid}, "
            f"N_published={n_published}, N_missing={n_missing}, C_c={c_c:.4f}"
        )
        if n_missing:
            print(
                f"  median WP published={row['median_WP_published']:.1f}, "
                f"missing={row['median_WP_missing']:.1f}"
            )
            print(
                f"  median GRDI published={row['median_GRDI_published']:.2f}, "
                f"missing={row['median_GRDI_missing']:.2f}"
            )
        else:
            print(f"  median WP published={row['median_WP_published']:.1f} (no unpublished eligible cells)")
    else:
        print("  Eligible grid is empty")

    tbl = pd.DataFrame([row])
    tbl_path = out / "Table_meta_coverage.csv"
    tbl.to_csv(tbl_path, index=False)
    print(f"  Saved: {tbl_path}")

    write = grid.copy()
    write["meta_missing"] = write["meta_missing"].astype(int)
    write["eligible"] = write["eligible"].astype(int)
    write["published"] = write["published"].astype(int)
    gpkg_path = out / "independent_grid.gpkg"
    write.to_file(gpkg_path, driver="GPKG")
    print(f"  Saved: {gpkg_path}")
    print("=" * 60)


if __name__ == "__main__":
    main()
