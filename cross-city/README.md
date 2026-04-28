# Cross-city comparison

Horizontal run across multiple regions: steps 01, 02, 03c, then summary tables.

**Per-region pipeline (full 01→…→03f) and `./run` options:** [`pipeline/PIPELINE.md`](../pipeline/PIPELINE.md).

## Output tables

### Table 1 — Meta vs WorldPop comparison

| City | N Cells | Spearman ρ | Pearson r | ΔGini (Meta−WP) | Top 10% WP | Top 10% Meta | Δ Top 10% | Mean Residual |
|------|---------|------------|-----------|-----------------|------------|--------------|-----------|---------------|
| Nairobi | xxx | ... | ... | ... | ... | ... | ... | ... |
| Mexico City | xxx | ... | ... | ... | ... | ... | ... | ... |
| ... | ... | ... | ... | ... | ... | ... | ... | ... |

- **N Cells**: Number of valid quadkeys (both WorldPop and Meta share > 0)
- **Spearman ρ / Pearson r**: Correlation of log(meta_share) vs log(wp_share)
- **ΔGini (Meta−WP)**: Gini(Meta) − Gini(WorldPop); positive = Meta more unequal
- **Top 10% WP / Top 10% Meta**: Share of allocation in top 10% of cells (WorldPop, Meta)
- **Δ Top 10%**: Top 10% Meta − Top 10% WP
- **Mean Residual**: Mean of log(meta_share / wp_share)

### Table 2 — Poverty Effect (Spatially Corrected)

| City | OLS τ | SEM τ | exp(SEM τ) | SEM p-value |
|------|-------|-------|------------|-------------|
| Nairobi | -0.30 | -0.39 | 0.67 | <0.001 |
| Mexico | 0.13 | 0.05 | 1.06 | 0.31 |

- **OLS τ**: Treatment effect (T = poverty top quartile) from covariate-adjusted OLS
- **SEM τ**: Treatment effect from Spatial Error Model (spatially corrected)
- **exp(SEM τ)**: Multiplicative effect on Meta/WP ratio per unit T
- **SEM p-value**: Significance of SEM τ

Interpretation: Strong case (τ significant, negative); Moderate case (τ marginal); Null case (τ non-significant).

## Usage

```bash
# Run 01 + 02 + 03c for all regions, then aggregate
python cross-city/run_cross_city_table.py

# Only aggregate from existing outputs (skip running steps)
python cross-city/run_cross_city_table.py --aggregate-only

# Limit to specific regions (supports prefixes: PHI, KEN)
python cross-city/run_cross_city_table.py --regions PHI,KEN,MEX
python cross-city/run_cross_city_table.py --regions KEN_Nairobi,KEN_Mombasa,MEX,PHI_CagayandeOroCity

# With reference hour (uses fb_baseline_median_h08.gpkg). Build baseline first with same hour.
python cross-city/run_cross_city_table.py --ref-hour 8

# Custom output directory
python cross-city/run_cross_city_table.py -o outputs/cross-city/
```

## Figures (R)

```bash
Rscript cross-city/figures_cross_city.R
```

Produces: **Figure1_spatial_agreement.png** (spatial agreement / log-log), **Figure_concentration_ratio.png**, **Figure2_lorenz_curves.png**, **Figure3_residual_maps.png** (and optional per-city / row variants), **Figure4_sem_forest.png**, **Figure5_cross_city_scatter.png** (and optional **Figure4_5_combined.png**). Requires: sf, ggplot2, dplyr, tidyr, patchwork.

## Prerequisites

- **Meta baseline GPKGs** must be built first. See main README:
  ```bash
  python data_prep/build_fb_baseline_median.py --all
  # Or with reference hour: python data_prep/build_fb_baseline_median.py --all --ref-hour 8
  ```
- Step 01, 02, 03c outputs must exist for each region (or run without `--aggregate-only` to generate them)
