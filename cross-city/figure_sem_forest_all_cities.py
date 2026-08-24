#!/usr/bin/env python3
"""Forest plot of SEM τ (poverty top quartile) with 95% CIs, grouped by country."""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "outputs" / "cross-city"

# Study cities only (not event-level extracts, not *_local).
GROUPS = [
    (
        "Kenya",
        [
            ("Nairobi", "KEN_Nairobi"),
            ("Mombasa", "KEN_Mombasa"),
            ("Kisumu", "KEN_Kisumu"),
            ("Nakuru", "KEN_Nakuru"),
        ],
    ),
    (
        "Philippines",
        [
            ("Cagayan de Oro", "PHI_CagayandeOroCity"),
            ("Davao City", "PHI_DavaoCity"),
            ("Zamboanga City", "PHI_ZamboangaCity"),
            ("General Santos", "PHI_GeneralSantosCity"),
        ],
    ),
    (
        "Mexico",
        [
            ("Mexico City", "MEX"),
            ("Puebla", "MEX_Puebla"),
            ("León", "MEX_Leon"),
        ],
    ),
    (
        "Indonesia",
        [
            ("Medan", "IDN_Medan"),
            ("Banda Aceh", "IDN_BandaAceh"),
        ],
    ),
    (
        "Sri Lanka",
        [
            ("Colombo", "LKA_Colombo"),
            ("Kandy", "LKA_Kandy"),
        ],
    ),
    (
        "Colombia",
        [
            ("Barranquilla", "COL_Barranquilla"),
            ("Cartagena", "COL_Cartagena"),
        ],
    ),
    (
        "Ecuador",
        [
            ("Cuenca", "ECU_Cuenca"),
            ("Guayaquil", "ECU_Guayaquil"),
        ],
    ),
    (
        "South Africa",
        [
            ("Cape Town", "ZAF_CapeTown"),
            ("Garden Route", "ZAF_GardenRoute"),
        ],
    ),
]

COUNTRY_COLOR = {
    "Kenya": "#3D5A40",
    "Philippines": "#C45C6A",
    "Mexico": "#4A6FA5",
    "Indonesia": "#B8860B",
    "Sri Lanka": "#6B4C9A",
    "Colombia": "#C47A3A",
    "Ecuador": "#2A9D8F",
    "South Africa": "#7A4450",
}


def load_sem_rows() -> pd.DataFrame:
    rows = []
    missing = []
    for country, cities in GROUPS:
        for city, region in cities:
            path = ROOT / "outputs" / region / "03c_spatial_regression" / "Table_tau_comparison.csv"
            if not path.exists():
                missing.append(region)
                continue
            d = pd.read_csv(path)
            sem = d[d["Model"].str.contains("SEM", case=False)]
            if sem.empty:
                missing.append(region)
                continue
            r = sem.iloc[0]
            tau = float(r["tau"])
            se = float(r["SE"])
            p = float(r["p_value"])
            rows.append(
                {
                    "Country": country,
                    "City": city,
                    "Region": region,
                    "tau": tau,
                    "SE": se,
                    "p": p,
                    "CI_lo": tau - 1.96 * se,
                    "CI_hi": tau + 1.96 * se,
                    "exp_tau": float(r["exp_tau"]),
                    "sig": p < 0.05,
                }
            )
    if missing:
        raise FileNotFoundError("Missing SEM tables: " + ", ".join(missing))
    return pd.DataFrame(rows)


def plot_forest(df: pd.DataFrame, path: Path) -> None:
    plt.rcParams.update(
        {
            "font.size": 10,
            "axes.spines.top": False,
            "axes.spines.right": False,
            "figure.facecolor": "white",
            "axes.facecolor": "white",
        }
    )

    items = []
    for country, _ in GROUPS:
        sub = df[df["Country"] == country]
        if sub.empty:
            continue
        items.append(("header", country, None))
        for _, row in sub.iterrows():
            items.append(("city", country, row))

    n_headers = sum(1 for t, _, _ in items if t == "header")
    n_cities = sum(1 for t, _, _ in items if t == "city")
    height = 0.36 * (n_cities + n_headers) + 1.7
    fig, ax = plt.subplots(figsize=(8.4, height))

    y = 0.0
    yticks, ylabels, ycolors, yweights = [], [], [], []
    xmax = df["CI_hi"].max()
    xmin = df["CI_lo"].min()
    pad = 0.08 * (xmax - xmin if xmax > xmin else 1)

    ax.axvline(0, color="0.55", ls="--", lw=0.8, zorder=1)

    first_group = True
    for kind, country, row in items:
        if kind == "header":
            if not first_group:
                y -= 0.45
            first_group = False
            yticks.append(y)
            ylabels.append(country)
            ycolors.append(COUNTRY_COLOR[country])
            yweights.append("bold")
            y -= 0.95
            continue

        color = COUNTRY_COLOR[country]
        ax.errorbar(
            row["tau"],
            y,
            xerr=[[row["tau"] - row["CI_lo"]], [row["CI_hi"] - row["tau"]]],
            fmt="none",
            ecolor="0.35",
            elinewidth=1.05,
            capsize=2.5,
            zorder=2,
        )
        ax.scatter(
            row["tau"],
            y,
            s=38,
            c=color if row["sig"] else "white",
            edgecolors=color,
            linewidths=1.1,
            zorder=3,
        )
        yticks.append(y)
        ylabels.append("  " + row["City"])
        ycolors.append("0.15")
        yweights.append("normal")
        p_txt = f"p={row['p']:.3f}" if row["p"] >= 0.001 else "p<0.001"
        ax.text(
            row["CI_hi"] + pad * 0.35,
            y,
            f"{row['tau']:.2f}  {p_txt}",
            va="center",
            fontsize=7.5,
            color="0.3",
        )
        y -= 1.0

    ax.set_yticks(yticks)
    ax.set_yticklabels(ylabels)
    for tick, color, weight in zip(ax.get_yticklabels(), ycolors, yweights):
        tick.set_color(color)
        tick.set_fontweight(weight)
    ax.set_ylim(y + 0.45, 0.55)
    ax.set_xlim(xmin - pad * 0.4, xmax + pad * 4.2)
    ax.set_xlabel("SEM τ  (high-poverty quartile vs rest), 95% CI")
    ax.set_title("Poverty effect on Meta vs WorldPop allocation, by city")
    ax.plot([], [], marker="o", color="0.3", linestyle="None", label="p < 0.05")
    ax.plot(
        [],
        [],
        marker="o",
        markerfacecolor="white",
        markeredgecolor="0.3",
        linestyle="None",
        label="p ≥ 0.05",
    )
    ax.legend(loc="upper right", frameon=False, fontsize=8)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=220)
    plt.close()
    print("Saved", path)


def main() -> None:
    df = load_sem_rows()
    csv_path = OUT / "Table_sem_tau_all_cities.csv"
    OUT.mkdir(parents=True, exist_ok=True)
    df.to_csv(csv_path, index=False)
    print("Saved", csv_path)
    plot_forest(df, OUT / "Figure_sem_forest_all_cities.png")


if __name__ == "__main__":
    main()
