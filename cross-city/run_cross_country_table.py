#!/usr/bin/env python3
"""
Cross-country comparison: aggregate Meta-event footprint results (one row per country).

Reads existing `./run --footprint COUNTRY` outputs. Missing steps are skipped.

Tables → outputs/cross-country/. Figures → figure/cross-country/.

Usage:
  python cross-city/run_cross_country_table.py
  python cross-city/run_cross_country_table.py --footprints PHL,KEN,MEX
"""

import argparse
import sys
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = PROJECT_ROOT / "pipeline"
sys.path.insert(0, str(SCRIPTS))
sys.path.insert(0, str(PROJECT_ROOT / "cross-city"))

from run_cross_city_table import (  # noqa: E402
    extract_metrics_from_region,
    extract_poverty_effect_from_region,
    extract_rank_instability_from_region,
)


def get_footprints(footprints_arg=None):
    import region_config

    available = list(region_config.list_footprints())
    if not footprints_arg:
        return available
    requested = [r.strip() for r in footprints_arg.split(",") if r.strip()]
    unknown = [r for r in requested if r not in available]
    if unknown:
        print(f"Unknown footprint(s): {', '.join(unknown)}. Available: {', '.join(available)}")
        sys.exit(1)
    return requested


def footprint_kwargs(code: str) -> dict:
    import region_config

    return {
        "finder": region_config.find_footprint_artifact,
        "city_label": region_config.country_display_name(code),
    }


def main():
    p = argparse.ArgumentParser(
        description="Cross-country comparison: aggregate footprint 02/03b/03c outputs",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--footprints",
        type=str,
        default=None,
        help="ISO3 codes (PHL,KEN,MEX). Default: all configured footprints.",
    )
    p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Output directory (default: outputs/cross-country/).",
    )
    args = p.parse_args()

    codes = get_footprints(args.footprints)
    if not codes:
        print("No footprints to process. Check --footprints or config/regions.json.")
        sys.exit(1)

    print(f"Footprints: {', '.join(codes)}")

    rows = []
    for code in codes:
        kw = footprint_kwargs(code)
        m = extract_metrics_from_region(code, include_city_area=False, **kw)
        if m:
            rows.append(m)
        else:
            print(f"  Skipped {code}: no footprint 02 output found")

    if not rows:
        print("No metrics extracted. Run ./run --footprint COUNTRY first.")
        sys.exit(1)

    df = pd.DataFrame(rows)
    col_order = [
        "Country",
        "City",
        "Region",
        "N_Cells_total",
        "Total_WorldPop",
        "Total_Meta_FB",
        "Total_Area_km2",
        "N_Cells_valid",
        "Valid_WorldPop",
        "Valid_WorldPop_pct",
        "Valid_Meta_FB",
        "Valid_Meta_pct",
        "Valid_Area_km2",
        "Valid_Area_pct",
        "Spearman_rho",
        "Pearson_r",
        "Delta_Gini",
        "Top10_WP",
        "Top10_Meta",
        "Top10_Delta_Share",
        "Mean_Residual",
    ]
    df = df[[c for c in col_order if c in df.columns]]
    df = df.rename(
        columns={
            "N_Cells_total": "N cells (total)",
            "Total_WorldPop": "Total WorldPop",
            "Total_Meta_FB": "Total Meta (FB)",
            "Total_Area_km2": "Total area (km²)",
            "N_Cells_valid": "N cells (valid)",
            "Valid_WorldPop": "Valid WorldPop",
            "Valid_WorldPop_pct": "Valid WorldPop (% of total)",
            "Valid_Meta_FB": "Valid Meta (FB)",
            "Valid_Meta_pct": "Valid Meta (% of total)",
            "Valid_Area_km2": "Valid area (km²)",
            "Valid_Area_pct": "Valid area (% of harmonised grid)",
            "Spearman_rho": "Spearman ρ",
            "Pearson_r": "Pearson r",
            "Delta_Gini": "ΔGini (Meta−WP)",
            "Top10_WP": "Top 10% WP",
            "Top10_Meta": "Top 10% Meta",
            "Top10_Delta_Share": "Δ Top 10%",
            "Mean_Residual": "Mean Residual",
        }
    )

    out_dir = args.output or (PROJECT_ROOT / "outputs" / "cross-country")
    out_dir = out_dir if (out_dir.suffix == "" or out_dir.is_dir()) else out_dir.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    tbl1_path = out_dir / "Table1_cross_country_table.csv"
    df.to_csv(tbl1_path, index=False, float_format="%.4f")
    print(f"\nSaved: {tbl1_path}")
    print(df.to_string(index=False))

    tbl2_rows = []
    for code in codes:
        kw = footprint_kwargs(code)
        m = extract_poverty_effect_from_region(code, **kw)
        if m:
            tbl2_rows.append(m)
        else:
            print(f"  Skipped {code} for Table 2: no footprint 03c output found")

    if tbl2_rows:
        df2 = pd.DataFrame(tbl2_rows)
        keep2 = [
            c
            for c in ("Country", "City", "Region", "OLS_tau", "SEM_tau", "exp_SEM_tau", "SEM_p_fmt")
            if c in df2.columns
        ]
        df2_out = df2[keep2].copy()
        df2_out = df2_out.rename(
            columns={
                "OLS_tau": "OLS τ",
                "SEM_tau": "SEM τ",
                "exp_SEM_tau": "exp(SEM τ)",
                "SEM_p_fmt": "SEM p-value",
            }
        )
        tbl2_path = out_dir / "Table2_poverty_effect_spatially_corrected.csv"
        df2_out.to_csv(tbl2_path, index=False, float_format="%.2f")
        print(f"\nSaved: {tbl2_path}")
        print("Table 2 — Poverty Effect (Spatially Corrected)")
        print(df2_out.to_string(index=False))
    else:
        print("\nTable 2 skipped: no footprint 03c outputs.")

    rank_rows = []
    for code in codes:
        kw = footprint_kwargs(code)
        rm = extract_rank_instability_from_region(code, **kw)
        if rm:
            rank_rows.append(rm)
        else:
            print(f"  Skipped {code} for rank instability: no 03b Table_rank_instability.csv")

    if rank_rows:
        df_rank = pd.DataFrame(rank_rows)
        front = [c for c in ("Country", "City", "Region") if c in df_rank.columns]
        rest = [c for c in df_rank.columns if c not in front]
        df_rank = df_rank[front + sorted(rest)]
        rank_out = out_dir / "Table_rank_instability_cross_country.csv"
        df_rank.to_csv(rank_out, index=False, float_format="%.6f")
        print(f"\nSaved: {rank_out}")
        print("Rank instability (Meta vs WorldPop shares, 03b analysis grid)")
        print(df_rank.to_string(index=False))
    else:
        print("\nRank instability table skipped: no 03b Table_rank_instability.csv files found.")


if __name__ == "__main__":
    main()
