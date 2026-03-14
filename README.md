# Residential Population Analysis

Analysis pipeline comparing **Meta** and **WorldPop** residential population estimates, with **poverty (MPI)** as an explanatory variable for digital representation bias.

## Overview

This project harmonises Meta Facebook baseline and WorldPop population rasters to a common quadkey grid, compares their spatial distributions, and investigates how poverty relates to residual bias (Meta underrepresentation relative to WorldPop). The pipeline includes:

- Harmonisation to the Meta quadkey grid
- **Script 02:** Summary stats, spatial agreement (Pearson/Spearman, log-log regression), rank agreement (Top-X overlap, Jaccard), distribution similarity (KS, EMD), inequality (Gini, Lorenz), spatial structure (Moran's I, LISA, Gi*, hotspot overlap), residual maps, agreement typology (HH/LL/HL/LH)
- **Script 03a:** Associational models — Residual ~ Poverty + Distance + Density (covariate-adjusted), diagnostics (VIF, heteroskedasticity)
- **Script 03c:** Spatial regression (SLM, SEM) only
- Bivariate maps (Poverty × Residual)

## Prerequisites

- **Python 3.9+** (with conda recommended: `conda activate geo_env_LLM`)
- **R 4.0+** (for descriptive plots and bivariate maps)

### Python packages

```bash
pip install -r requirements.txt
```

Main dependencies: geopandas, rasterio, rasterstats, pandas, numpy, scipy, matplotlib, statsmodels, libpysal, esda, spreg.

### R packages

```r
install.packages(c("sf", "ggplot2", "dplyr", "patchwork", "biscale", "cowplot"))
```

## Quick Start

### 1. Build Meta baseline (required before first run)

The pipeline uses Meta PDC (Population During Crisis) data. Build the baseline GPKG first:

```bash
# Single region (uses config: pdc_raw_dir, pdc_processed_csv, pdc_ref_hour)
python data_prep/build_fb_baseline_median.py --region PHI_CagayandeOroCity

# All regions at once
python data_prep/build_fb_baseline_median.py --all

# With a specific reference hour (0, 8, or 16). Default is 0 (midnight) from config.
python data_prep/build_fb_baseline_median.py --region KEN_Nairobi --ref-hour 8
python data_prep/build_fb_baseline_median.py --all --ref-hour 8
```

**Output:** `outputs/{REGION}/fb_baseline_median_h{00|08|16}.gpkg`

**Reference hour:** Each region has `pdc_ref_hour` in `config/regions.json` (default 0). Use `--ref-hour` to override. If you use a non-default hour, update the `meta` path in `config/regions.json` to match (e.g. `fb_baseline_median_h08.gpkg` instead of `fb_baseline_median_h00.gpkg`).

**Manual paths (no config):**
```bash
python data_prep/build_fb_baseline_median.py -i /path/to/raw/PDC/folder -o outputs/fb_baseline_median.gpkg
python data_prep/build_fb_baseline_median.py -i outputs/PDC_Philippines_Basyang.csv -o outputs/fb_baseline_median.gpkg
```

### 2. Run the pipeline

```bash
# Single region (use ./run to avoid "zsh: number expected" on zsh)
./run --region PHI_CagayandeOroCity
# Or: bash ./pipeline/run_all.sh --region PHI_CagayandeOroCity

# All regions
./run --all
./run --all --no-basemap   # Skip basemap tiles (avoids network/memory issues)

# Other regions: KEN_Nairobi, KEN_Mombasa (Kenya), MEX (Mexico), PHI_DavaoCity
./run --region KEN_Nairobi
./run --region MEX --no-basemap

# Start from a specific step (e.g. after changing 03b)
./run --region PHI_CagayandeOroCity --start-from 03b
```

Or run step by step:

```bash
# 1. Harmonise (WorldPop + Meta + Poverty)
python pipeline/01_harmonise_datasets.py --region PHI_CagayandeOroCity

# 2. Compare Meta vs WorldPop (residuals, Table 1 & 2)
python pipeline/02_compare_meta_worldpop.py --region PHI_CagayandeOroCity

# 3a. Regression (Spearman, OLS, VIF, Moran's I)
python pipeline/03a_regression.py -i outputs/PHI_CagayandeOroCity/02/harmonised_with_residual.gpkg -o outputs/PHI_CagayandeOroCity

# 3b. Stratified analysis + inequality
python pipeline/03b_stratified.py -i outputs/PHI_CagayandeOroCity/02/harmonised_with_residual.gpkg -o outputs/PHI_CagayandeOroCity

# 3c. Spatial regression (SLM, SEM)
python pipeline/03c_spatial_regression.py -i outputs/PHI_CagayandeOroCity/02/harmonised_with_residual.gpkg -o outputs/PHI_CagayandeOroCity

# 3d. Bivariate map: Poverty × Residual
Rscript pipeline/03d_bivariate_map_poverty_residual.R -i outputs/PHI_CagayandeOroCity/02/harmonised_with_residual.gpkg -o outputs/PHI_CagayandeOroCity/03d_bivariate --region PHI_CagayandeOroCity
```

**Note:** Scripts 03a, 03b, and 03d require `poverty_mean` in the 02 output. Run 01 with poverty (default); use `--no-poverty` only if skipping poverty analysis.

### 3. Cross-city comparison

After running the pipeline for the regions you need (or `./run --all`):

```bash
# Run 01 + 02 + 03c for all regions, then aggregate into summary tables
python cross-city/run_cross_city_table.py

# Only aggregate from existing outputs (skip re-running steps)
python cross-city/run_cross_city_table.py --aggregate-only

# Limit to specific regions
python cross-city/run_cross_city_table.py --regions KEN_Nairobi,KEN_Mombasa,MEX,PHI_CagayandeOroCity

# Custom output directory
python cross-city/run_cross_city_table.py -o outputs/cross-city/
```

**Cross-city figures (R):**
```bash
Rscript cross-city/figures_cross_city.R -o outputs/cross-city/
```

Produces: Figure 1 (spatial agreement), Figure 2 (Lorenz curves), Figure 3 (residual maps), Figure 4 (SEM forest), Figure 5 (cross-city scatter). See `cross-city/README.md` for table definitions.

## Pipeline

| Script | Purpose | Input (default) | Output |
|--------|---------|-----------------|--------|
| **01** | Harmonise + descriptive maps | WorldPop, Meta, Poverty rasters | `outputs/{REGION}/01/` |
| **02** | Compare Meta vs WorldPop, residuals | `01/harmonised_meta_worldpop.gpkg` | `outputs/{REGION}/02/` |
| **03a** | Spearman, OLS, VIF, Moran's I | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03a_regression/` |
| **03b** | Stratified + Gini by poverty quintile | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03b_stratified/` |
| **03c** | Spatial regression (SLM, SEM) | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03c_spatial_regression/` |
| **03d** | Bivariate map: Poverty × Residual (R) | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03d_bivariate/` |

With `--region`, outputs go under `outputs/{REGION}/`. Cross-city tables and figures go to `outputs/cross-city/`.

## Outputs

```
outputs/
├── {REGION}/           # e.g. PHI_CagayandeOroCity, KEN_Nairobi, MEX
│   ├── 01/
│   │   ├── harmonised_meta_worldpop.gpkg
│   │   ├── 01_data_overview.png
│   │   ├── 01_bivariate_worldpop_meta.png
│   │   └── 01_bivariate_worldpop_meta_basemap.png
│   ├── 02/
│   │   ├── harmonised_with_residual.gpkg
│   │   ├── Table1_meta_worldpop_metrics.csv
│   │   ├── 02_rank_agreement.csv
│   │   ├── 02_distribution_histogram_kde.png
│   │   ├── 02_lorenz_curves.png
│   │   ├── 02_lisa_worldpop.png, 02_lisa_meta.png
│   │   ├── 02_hotspot_overlap_map.png, 02_hotspot_overlap.csv
│   │   ├── 02_agreement_typology.png
│   │   └── ...
│   ├── 03a_regression/
│   │   ├── Table2_regression.csv
│   │   ├── Table2b_VIF.csv
│   │   └── Table2b_heteroskedasticity.csv
│   ├── 03b_stratified/
│   │   ├── Table_interaction.csv
│   │   ├── Table3_poverty_strata.csv
│   │   ├── Table4_gini_by_quintile.csv
│   │   └── ...
│   ├── 03c_spatial_regression/
│   │   ├── Table_model_comparison.csv
│   │   ├── Table3_SLM_SEM_coefficients.csv
│   │   ├── slm_residual_map.png
│   │   └── sem_residual_map.png
│   └── 03d_bivariate/
│       ├── 03d_bivariate_poverty_residual.png
│       └── 03d_bivariate_poverty_residual_basemap.png
└── cross-city/
    ├── Table1_cross_city_table.csv
    ├── Table2_poverty_effect_spatially_corrected.csv
    ├── Figure1_spatial_agreement.png
    ├── Figure2_lorenz_curves.png
    ├── Figure3_residual_maps.png
    └── ...
```

## Optional Scripts

- **01_plot_descriptive.R** — Descriptive figures (data overview + bivariate): `Rscript pipeline/01_plot_descriptive.R` or `python pipeline/01_harmonise_datasets.py --plot`
- **03d_bivariate_map_poverty_residual.R** — Poverty × Residual bivariate map: `Rscript pipeline/03d_bivariate_map_poverty_residual.R`

## Data Defaults

Scripts use default paths (e.g. for Nairobi/Kenya). Override with CLI arguments:

```bash
python pipeline/01_harmonise_datasets.py --worldpop /path/to.tif --meta /path/to.gpkg --poverty /path/to/poverty.tif
python pipeline/01_harmonise_datasets.py --filter-by both --filter-min 50   # keep quadkeys where both Meta & WorldPop ≥ 50
```

## License

See project license file.
