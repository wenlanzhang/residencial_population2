# Cross-city comparison

Horizontal run across **all selected study cities** (21 cities in PHL, KEN, MEX, IDN, LKA, COL, ECU, ZAF) that have data: aggregate existing per-city outputs (or run 01, 02, 03c first), then summary tables. Every city uses the same country/city folders.

**Per-region pipeline and `./run` options:** [`pipeline/PIPELINE.md`](../pipeline/PIPELINE.md).

## Units

| Unit | How you get it | Folder |
|------|----------------|--------|
| Selected **city** (clipped) | default | `outputs/city/{COUNTRY}/{city}/`, `figure/city/{COUNTRY}/{city}/` |
| Meta event **footprint** | `./run --footprint COUNTRY` | `outputs/footprints/{CODE}/` |

Cross-city aggregation writes:

- tables → `outputs/cross-city/`
- figures → `figure/cross-city/`

Cross-country aggregation (one row per footprint) writes:

- tables → `outputs/cross-country/`
- figures → `figure/cross-country/`

Cities or countries without step-02/03c outputs are skipped with a warning.

## Output tables

### Table 1 — Meta vs WorldPop comparison

Columns include **Country**, **City**, **Region** (config code), then:

| N cells (total) | Total WorldPop | … | N cells (valid) | Valid WorldPop | Valid area (km²) | Spearman ρ | … |
|-----------------|----------------|---|-----------------|----------------|------------------|------------|---|

- **N cells (total)** / **Total WorldPop** / **Total Meta (FB)** / **Total area (km²)**: Step **01** harmonised grid (all quadkeys, **including zeros**)
- **N cells (valid)** / **Valid WorldPop** / **Valid Meta (FB)** / **Valid area (km²)**: Step **02** analysis grid (both shares > 0; zeros excluded)
- **Valid WorldPop (% of total)** / **Valid Meta (% of total)**: Valid-cell population ÷ harmonised total (step 01) × 100 for each source
- **Total area (% of city)**: Total harmonised grid area ÷ city boundary × 100 (the polygon used in step 01: local `clip_shape`, OSM, or geoBoundaries).
- **Valid area (% of harmonised grid)**: Valid area ÷ total harmonised area × 100
- **Valid area (% of city)**: Valid area ÷ city boundary × 100
- **Spearman ρ / Pearson r**: Correlation of log(meta_share) vs log(wp_share) on the valid grid
- **ΔGini (Meta−WP)**: Gini(Meta) − Gini(WorldPop); positive = Meta more unequal
- **Top 10% WP / Top 10% Meta**: Share of allocation in top 10% of cells (WorldPop, Meta)
- **Δ Top 10%**: Top 10% Meta − Top 10% WP
- **Mean Residual**: Mean of log(meta_share / wp_share)

Step **01** GeoPackages keep all cells; step **02** and downstream scripts use the filtered analysis grid. The cross-city table reports **both** scopes side by side.

### Table 1b — Meta coverage of the eligible city grid (01b)

One row per city from `outputs/city/{COUNTRY}/{city}/01b_coverage/Table_meta_coverage.csv`. \(C_c = N_{\mathrm{published}}/N_{\mathrm{grid}}\) on an independently defined city grid (published vs eligible-but-unpublished tiles). Also median WorldPop and GRDI on published vs missing tiles.

### Table 2 — Poverty Effect (Spatially Corrected)

| Country | City | Region | OLS τ | SEM τ | exp(SEM τ) | SEM p-value |
|---------|------|--------|-------|-------|------------|-------------|

- **OLS τ**: Treatment effect (T = poverty top quartile) from covariate-adjusted OLS
- **SEM τ**: Treatment effect from Spatial Error Model (spatially corrected)
- **exp(SEM τ)**: Multiplicative effect on Meta/WP ratio per unit T
- **SEM p-value**: Significance of SEM τ

### Tables 2b–2d — Meta-count and censoring robustness (03f)

Aggregated from each city’s `outputs/city/{COUNTRY}/{city}/03f_robustness/`:

| File | Contents |
|------|----------|
| `Table2b_meta_count_sensitivity.csv` | SEM τ under Meta low-count filters |
| `Table2c_meta_count_composition.csv` | Composition of Meta count bins (GRDI, residual, density) |
| `Table2d_meta_censoring_sensitivity.csv` | Missing-cell privacy-censoring sensitivity |

### Table 4c — Crisis inference sensitivity (04b)

One row per city from `outputs/city/{COUNTRY}/{city}/04b_crisis_inference/Table4c_crisis_inference_sensitivity.csv`.

| country | city | time | n | direction_flip_pct | jaccard_increase_top10 | jaccard_decrease_top10 | median_sensitivity_high_deprivation | median_sensitivity_other |
|---------|------|------|---|--------------------|------------------------|------------------------|-------------------------------------|--------------------------|

- **direction_flip_pct**: Share of cells whose inferred increase/decrease sign flips when the Meta baseline total is reallocated with WorldPop's spatial pattern (crisis counts held fixed)
- **jaccard_increase_top10 / jaccard_decrease_top10**: Overlap of the top 10% strongest inferred increases (decreases)
- **flip_pct_high_deprivation / flip_pct_other / delta_F**: P(flip | high deprivation), P(flip | other), and the difference in percentage points
- **median_F_t, F_t_min, F_t_max**: Flip rate across individual crisis days at the reference hour (not the median count)
- **delta_S**: Supplementary only — |G_Meta − G_WP| does not depend on C

Per-city maps: `figure/city/{COUNTRY}/{city}/04b_crisis_inference/04b_crisis_sensitivity_maps.png` (Cape Town is the worked example).

## Usage

```bash
# All selected cities (skip any without data when aggregating)
python cross-city/run_cross_city_table.py --aggregate-only

# Run 01 + 02 + 03c for every selected city, then aggregate
python cross-city/run_cross_city_table.py

# One or more countries (all selected cities in each)
python cross-city/run_cross_city_table.py --regions PHL,KEN,MEX

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
| **02_concentration_ratio.png** | 02 (95% bootstrap CI error bars; `outputs/cross-city/Table_concentration_ratio_ci.csv`) |
| **02_lorenz_curves.png** | 02 |
| **02_residual_maps.png** | 02 (combined panel; per-city maps are `figure/city/{COUNTRY}/{city}/02/02_allocation_log_ratio_r.png`) |
| **03b_hotspot_jaccard.png** | 03b |
| **03c_sem_forest.png** | 03c |
| **03c_spearman_vs_tau.png** | 03c |
| **03c_delta_gini_vs_tau.png** | 03c |
| **03c_forest_scatter.png** | 03c (forest + ΔGini scatter) |
| **03c_tau_vs_city_grdi.png** | 03c (τ vs median GRDI and vs within-city GRDI gap; `outputs/cross-city/Table_tau_vs_city_grdi.csv`) |
| **04b_cross_city_crisis_sensitivity.png** | 04b (median daily flip rate with IQR and min–max; J₁₀⁺ / J₁₀⁻) |
| **04b_socioeconomic_sensitivity.png** | 04b (ΔF: P(flip \| high deprivation) − P(flip \| other)) |
| **04b_baseline_divergence_socioeconomic.png** | 04b supplement (ΔS; C cancels — baseline discrepancy, not crisis inference) |

Also writes `outputs/cross-city/Table_sem_tau_all_cities.csv` and `Table_tau_vs_city_grdi.csv`. Requires: sf, ggplot2, dplyr, tidyr, patchwork (ggrepel optional for city labels).

## Cross-country (Meta event footprints)

One row per country AOI from `./run --footprint COUNTRY`. Same Table 1 / Table 2 / rank-instability metrics as cross-city, but **without** city-boundary area shares (the unit is the event footprint, not a city clip). Mexico 03c/SEM is skipped if that step did not finish.

```bash
python cross-city/run_cross_country_table.py
python cross-city/run_cross_country_table.py --footprints PHL,KEN,MEX
Rscript cross-city/figures_cross_country.R
```

- tables → `outputs/cross-country/`
- figures → `figure/cross-country/`

Same figure names as cross-city **except** there is no `02_residual_maps.png`. SEM forest CSV is `Table_sem_tau_all_countries.csv`. `02_concentration_ratio.png` includes 95% bootstrap CI error bars (`Table_concentration_ratio_ci.csv`).

## Prerequisites

- **Meta baseline GPKGs** must be built first. See main README:
  ```bash
  python data_prep/build_fb_baseline_median.py --all
  # Or with reference hour: python data_prep/build_fb_baseline_median.py --all --ref-hour 8
  ```
- Per-city step 01 / 02 / 03c outputs under `outputs/city/{COUNTRY}/{city}/` (and GPKGs under `data/processed/city/...`). Use `./run --region COUNTRY` or run the aggregator without `--aggregate-only`.
