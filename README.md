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

Run from the project root. **Before the first run**, build the Meta baseline (if using PDC data):

```bash
# Build Meta baseline GPKG (preprocesses raw PDC in memory if pdc_raw_dir is in config)
python data_prep/build_fb_baseline_median.py --region PHI

# Or with raw dir / CSV explicitly:
python data_prep/build_fb_baseline_median.py -i /path/to/raw/PDC/folder -o outputs/fb_baseline_median_PHI.gpkg
python data_prep/build_fb_baseline_median.py -i outputs/PDC_Philippines_Basyang.csv -o outputs/fb_baseline_median_PHI.gpkg
```

Then run the full pipeline:

```bash
# Run full pipeline (use ./run to avoid "zsh: number expected" on zsh)
./run --region PHI
# Or: bash ./pipeline/run_all.sh --region PHI

# Other regions: KEN_Nairobi, KEN_Mombasa (Kenya), MEX (Mexico)
./run --region KEN_Nairobi
./run --region MEX --no-basemap
```

Or run step by step:

```bash
# 1. Harmonise (WorldPop + Meta + Poverty)
python pipeline/01_harmonise_datasets.py

# 2. Compare Meta vs WorldPop (residuals, Table 1 & 2)
python pipeline/02_compare_meta_worldpop.py

# 3a. Regression (Spearman, OLS, VIF, Moran's I)
python pipeline/03a_regression.py

# 3b. Stratified analysis + inequality
python pipeline/03b_stratified.py

# 3c. Spatial regression (SLM, SEM)
python pipeline/03c_spatial_regression.py

# 3d. Bivariate map: Poverty × Residual
Rscript pipeline/03d_bivariate_map_poverty_residual.R
```

**Note:** Scripts 03a, 03b, and 03d require `poverty_mean` in the 02 output. Run 01 with poverty (default); use `--no-poverty` only if skipping poverty analysis.

## Pipeline

| Script | Purpose | Input (default) | Output |
|--------|---------|-----------------|--------|
| **01** | Harmonise + descriptive maps | WorldPop, Meta, Poverty rasters | `outputs/01/` |
| **02** | Compare Meta vs WorldPop, residuals | `01/harmonised_meta_worldpop.gpkg` | `outputs/02/` |
| **03a** | Spearman, OLS, VIF, Moran's I | `02/harmonised_with_residual.gpkg` | `outputs/03a_regression/` |
| **03b** | Stratified + Gini by poverty quintile | `02/harmonised_with_residual.gpkg` | `outputs/03b_stratified/` |
| **03c** | Spatial regression (SLM, SEM) | `02/harmonised_with_residual.gpkg` | `outputs/03c_spatial_regression/` |
| **03d** | Bivariate map: Poverty × Residual (R) | `02/harmonised_with_residual.gpkg` | `outputs/03d_bivariate/` |

## Outputs

```
outputs/
├── 01/
│   ├── harmonised_meta_worldpop.gpkg
│   ├── 01_data_overview.png
│   ├── 01_bivariate_worldpop_meta.png
│   └── 01_bivariate_worldpop_meta_basemap.png
├── 02/
│   ├── harmonised_with_residual.gpkg
│   ├── Table1_meta_worldpop_metrics.csv
│   ├── 02_rank_agreement.csv
│   ├── 02_distribution_histogram_kde.png
│   ├── 02_lorenz_curves.png
│   ├── 02_lisa_worldpop.png, 02_lisa_meta.png
│   ├── 02_hotspot_overlap_map.png, 02_hotspot_overlap.csv
│   ├── 02_agreement_typology.png
│   └── ...
├── 03a_regression/
│   ├── Table2_regression.csv
│   ├── Table2b_VIF.csv
│   └── Table2b_heteroskedasticity.csv
├── 03b_stratified/
│   ├── Table_interaction.csv
│   ├── Table3_poverty_strata.csv
│   ├── Table4_gini_by_quintile.csv
│   └── ...
├── 03c_spatial_regression/
│   ├── Table_model_comparison.csv
│   ├── Table3_SLM_SEM_coefficients.csv
│   ├── slm_residual_map.png
│   └── sem_residual_map.png
└── 03d_bivariate/
    ├── 03d_bivariate_poverty_residual.png
    └── 03d_bivariate_poverty_residual_basemap.png
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
