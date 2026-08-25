# Cross-city comparison

Horizontal run across **all selected study cities** that have data: steps 01, 02, 03c, then summary tables. The original four/five cities are not a special case — they use the same country/city folders as everyone else.

**Per-region pipeline and `./run` options:** [`pipeline/PIPELINE.md`](../pipeline/PIPELINE.md).

## Units

| Unit | How you get it | Folder |
|------|----------------|--------|
| Selected **city** (clipped) | default | `outputs/{COUNTRY}/{city}/`, `figure/{COUNTRY}/{city}/` |
| Country **full** (all cells in the Meta extract) | `--include-full` | `outputs/{COUNTRY}/full/`, `figure/{COUNTRY}/full/` |

Cross-city aggregation writes:

- tables → `outputs/cross-city/`
- figures → `figure/cross-city/`

Cities without step-02/03c outputs are skipped with a warning.

## Output tables

### Table 1 — Meta vs WorldPop comparison

Columns include **Country**, **City**, **Region** (config code), then:

| N cells (total) | Total WorldPop | … | N cells (valid) | Valid WorldPop | Valid area (km²) | Spearman ρ | … |
|-----------------|----------------|---|-----------------|----------------|------------------|------------|---|

- **N cells (total)** / **Total WorldPop** / **Total Meta (FB)** / **Total area (km²)**: Step **01** harmonised grid (all quadkeys, **including zeros**)
- **N cells (valid)** / **Valid WorldPop** / **Valid Meta (FB)** / **Valid area (km²)**: Step **02** analysis grid (both shares > 0; zeros excluded)
- **Valid WorldPop (% of total)** / **Valid Meta (% of total)**: Valid-cell population ÷ harmonised total (step 01) × 100 for each source
- **Total area (% of city)**: Total harmonised grid area ÷ city boundary × 100 (the polygon used in step 01: local `clip_shape`, OSM, or geoBoundaries). Blank for unclipped extracts.
- **Valid area (% of harmonised grid)**: Valid area ÷ total harmonised area × 100
- **Valid area (% of city)**: Valid area ÷ city boundary × 100
- **Spearman ρ / Pearson r**: Correlation of log(meta_share) vs log(wp_share) on the valid grid
- **ΔGini (Meta−WP)**: Gini(Meta) − Gini(WorldPop); positive = Meta more unequal
- **Top 10% WP / Top 10% Meta**: Share of allocation in top 10% of cells (WorldPop, Meta)
- **Δ Top 10%**: Top 10% Meta − Top 10% WP
- **Mean Residual**: Mean of log(meta_share / wp_share)

Step **01** GeoPackages keep all cells; step **02** and downstream scripts use the filtered analysis grid. The cross-city table reports **both** scopes side by side.

### Table 2 — Poverty Effect (Spatially Corrected)

| Country | City | Region | OLS τ | SEM τ | exp(SEM τ) | SEM p-value |
|---------|------|--------|-------|-------|------------|-------------|

- **OLS τ**: Treatment effect (T = poverty top quartile) from covariate-adjusted OLS
- **SEM τ**: Treatment effect from Spatial Error Model (spatially corrected)
- **exp(SEM τ)**: Multiplicative effect on Meta/WP ratio per unit T
- **SEM p-value**: Significance of SEM τ

## Usage

```bash
# All selected cities (skip any without data when aggregating)
python cross-city/run_cross_city_table.py --aggregate-only

# Run 01 + 02 + 03c for every selected city, then aggregate
python cross-city/run_cross_city_table.py

# One or more countries (all selected cities in each)
python cross-city/run_cross_city_table.py --regions PHI,KEN,MEX

# Also add unclipped extracts (IDN/LKA/COL/ECU/ZAF → Country / full)
python cross-city/run_cross_city_table.py --aggregate-only --include-full

# With reference hour (uses fb_baseline_median_h08.gpkg). Build baseline first with same hour.
python cross-city/run_cross_city_table.py --ref-hour 8

# Poverty layer for step 01 (default: GRDI). Use Meta RWI instead:
python cross-city/run_cross_city_table.py --poverty-source rwi
```

## Figures

```bash
Rscript cross-city/figures_cross_city.R
```

Reads `outputs/cross-city/Table1_*.csv` (and Table 2 / rank-instability when present) and plots every city in them. Names follow the pipeline step that produced the statistic:

| File | Step |
|------|------|
| **02_spatial_agreement.png** | 02 |
| **02_spearman.png** | 02 |
| **02_concentration_ratio.png** | 02 |
| **02_lorenz_curves.png** | 02 |
| **02_residual_maps.png** | 02 (combined panel; per-city maps are `figure/{COUNTRY}/{city}/02/02_allocation_log_ratio_r.png`) |
| **03b_hotspot_jaccard.png** | 03b |
| **03c_sem_forest.png** | 03c |
| **03c_spearman_vs_tau.png** | 03c |
| **03c_delta_gini_vs_tau.png** | 03c |
| **03c_forest_scatter.png** | 03c (forest + ΔGini scatter) |

Also writes `outputs/cross-city/Table_sem_tau_all_cities.csv`. Requires: sf, ggplot2, dplyr, tidyr, patchwork.

Unclipped extracts are included when Table 1 was built with `--include-full`.

## Prerequisites

- **Meta baseline GPKGs** must be built first. See main README:
  ```bash
  python data_prep/build_fb_baseline_median.py --all
  # Or with reference hour: python data_prep/build_fb_baseline_median.py --all --ref-hour 8
  ```
- Per-city step 01 / 02 / 03c outputs under `outputs/{COUNTRY}/{city}/` (and GPKGs under `data/processed/...`). Use `./run --region COUNTRY` or run the aggregator without `--aggregate-only`.
