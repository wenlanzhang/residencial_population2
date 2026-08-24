#!/usr/bin/env python3
"""11-city geob comparison figures from cross-city tables + 03c tau CSVs."""

from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "cross-city"
T1 = pd.read_csv(OUT / "Table1_cross_city_table.csv")
T2 = pd.read_csv(OUT / "Table2_poverty_effect_spatially_corrected.csv")
TR = pd.read_csv(OUT / "Table_rank_instability_cross_city.csv")

CITY_TO_REG = {
    "Nairobi": "KEN_Nairobi",
    "Mombasa": "KEN_Mombasa",
    "Kisumu": "KEN_Kisumu",
    "Nakuru": "KEN_Nakuru",
    "Cagayan de Oro": "PHI_CagayandeOroCity",
    "Davao City": "PHI_DavaoCity",
    "Zamboanga City": "PHI_ZamboangaCity",
    "General Santos": "PHI_GeneralSantosCity",
    "Mexico City": "MEX",
    "Puebla": "MEX_Puebla",
    "León": "MEX_Leon",
}
COUNTRY = {
    "Nairobi": "Kenya",
    "Mombasa": "Kenya",
    "Kisumu": "Kenya",
    "Nakuru": "Kenya",
    "Cagayan de Oro": "Philippines",
    "Davao City": "Philippines",
    "Zamboanga City": "Philippines",
    "General Santos": "Philippines",
    "Mexico City": "Mexico",
    "Puebla": "Mexico",
    "León": "Mexico",
}
COUNTRY_COLOR = {"Kenya": "#3D5A40", "Philippines": "#C45C6A", "Mexico": "#4A6FA5"}
ORDER = list(CITY_TO_REG.keys())


def _country_colors(cities):
    return [COUNTRY_COLOR[COUNTRY[c]] for c in cities]


def _sem_with_se():
    rows = []
    for city, reg in CITY_TO_REG.items():
        path = ROOT / "outputs" / reg / "03c_spatial_regression" / "Table_tau_comparison.csv"
        d = pd.read_csv(path)
        sem = d[d["Model"].str.contains("SEM", case=False)].iloc[0]
        t2 = T2[T2["City"] == city].iloc[0]
        rows.append(
            {
                "City": city,
                "tau": float(sem["tau"]),
                "SE": float(sem["SE"]),
                "p": t2["SEM p-value"],
                "exp_tau": float(sem["exp_tau"]),
            }
        )
    return pd.DataFrame(rows)


def _style():
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )


def fig_spearman():
    df = T1.set_index("City").loc[ORDER]
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    y = np.arange(len(ORDER))
    ax.barh(y, df["Spearman ρ"].values, color=_country_colors(ORDER), height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(ORDER)
    ax.invert_yaxis()
    ax.set_xlabel("Spearman ρ  (log Meta share vs log WorldPop share)")
    ax.set_xlim(0.5, 1.0)
    ax.set_title("Spatial agreement across 11 cities")
    for i, c in enumerate(ORDER):
        ax.text(df.loc[c, "Spearman ρ"] + 0.008, i, f"{df.loc[c, 'Spearman ρ']:.2f}", va="center", fontsize=8)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=col, label=name) for name, col in COUNTRY_COLOR.items()
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False)
    fig.tight_layout()
    path = OUT / "Figure_11city_spearman.png"
    fig.savefig(path, dpi=200)
    plt.close()
    print("Saved", path)


def fig_forest():
    df = _sem_with_se().set_index("City").loc[ORDER].reset_index()
    fig, ax = plt.subplots(figsize=(8.4, 5.4))
    y = np.arange(len(df))
    colors = _country_colors(df["City"])
    ax.axvline(0, color="0.55", ls="--", lw=0.8)
    ax.errorbar(
        df["tau"],
        y,
        xerr=1.96 * df["SE"],
        fmt="none",
        ecolor="0.35",
        elinewidth=1.1,
        capsize=3,
        zorder=2,
    )
    ax.scatter(df["tau"], y, c=colors, s=42, zorder=3, edgecolors="white", linewidths=0.4)
    ax.set_yticks(y)
    ax.set_yticklabels(df["City"])
    ax.invert_yaxis()
    ax.set_xlabel("SEM τ  (poverty top quartile vs rest)")
    ax.set_title("Poverty effect after spatial correction")
    for i, row in df.iterrows():
        ax.text(
            row["tau"] + 1.96 * row["SE"] + 0.03,
            i,
            f"p={row['p']}",
            va="center",
            fontsize=7.5,
            color="0.3",
        )
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=col, label=name) for name, col in COUNTRY_COLOR.items()
    ]
    ax.legend(handles=handles, loc="lower left", frameon=False)
    ax.set_xlim(-1.6, 0.55)
    fig.tight_layout()
    path = OUT / "Figure_11city_sem_forest.png"
    fig.savefig(path, dpi=200)
    plt.close()
    print("Saved", path)


def fig_scatter():
    m = T1.merge(T2, on="City").merge(TR[["City", "jaccard_top_10pct"]], on="City")
    m["country"] = m["City"].map(COUNTRY)
    fig, ax = plt.subplots(figsize=(7.4, 5.4))
    ax.axhline(0, color="0.55", ls="--", lw=0.8)
    ax.axvline(0.75, color="0.85", ls=":", lw=0.7)
    for country, col in COUNTRY_COLOR.items():
        sub = m[m["country"] == country]
        ax.scatter(sub["Spearman ρ"], sub["SEM τ"], c=col, s=55, label=country, zorder=3)
        for _, r in sub.iterrows():
            ax.annotate(r["City"], (r["Spearman ρ"], r["SEM τ"]), textcoords="offset points", xytext=(5, 4), fontsize=7.5)
    ax.set_xlabel("Spearman ρ  (spatial agreement)")
    ax.set_ylabel("SEM τ  (poverty effect)")
    ax.set_title("Agreement vs poverty bias")
    ax.legend(frameon=False, loc="lower left")
    fig.tight_layout()
    path = OUT / "Figure_11city_spearman_vs_tau.png"
    fig.savefig(path, dpi=200)
    plt.close()
    print("Saved", path)


def fig_jaccard():
    df = TR.set_index("City").loc[ORDER]
    fig, ax = plt.subplots(figsize=(8.2, 5.2))
    y = np.arange(len(ORDER))
    ax.barh(y, df["jaccard_top_10pct"].values, color=_country_colors(ORDER), height=0.7)
    ax.set_yticks(y)
    ax.set_yticklabels(ORDER)
    ax.invert_yaxis()
    ax.set_xlabel("Jaccard overlap of top 10% cells (Meta vs WorldPop)")
    ax.set_xlim(0, 1.08)
    ax.set_title("Hotspot overlap")
    for i, c in enumerate(ORDER):
        ax.text(df.loc[c, "jaccard_top_10pct"] + 0.02, i, f"{df.loc[c, 'jaccard_top_10pct']:.2f}", va="center", fontsize=8)
    handles = [
        plt.Rectangle((0, 0), 1, 1, color=col, label=name) for name, col in COUNTRY_COLOR.items()
    ]
    ax.legend(handles=handles, loc="lower right", frameon=False)
    fig.tight_layout()
    path = OUT / "Figure_11city_hotspot_jaccard.png"
    fig.savefig(path, dpi=200)
    plt.close()
    print("Saved", path)


if __name__ == "__main__":
    _style()
    fig_spearman()
    fig_forest()
    fig_scatter()
    fig_jaccard()
