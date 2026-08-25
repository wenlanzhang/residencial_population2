# Residential Population Analysis

Analysis pipeline comparing **Meta** and **WorldPop** residential population estimates, with **poverty / deprivation** (default: **GRDI**; optional: Meta **RWI**) as an explanatory variable for digital representation bias.

## Overview

This project harmonises Meta Facebook baseline and WorldPop population rasters to a common quadkey grid, compares their spatial distributions, and investigates how poverty relates to residual bias (Meta underrepresentation relative to WorldPop).

The pipeline includes:

- Harmonisation to the Meta quadkey grid
- **Script 02:** Summary stats, spatial agreement (Pearson/Spearman, log-log regression), rank agreement (Top-X overlap, Jaccard), distribution similarity (KS, EMD), inequality (Gini, Lorenz), spatial structure (Moran's I, LISA, Gi*, hotspot overlap), residuals, agreement typology (HH/LL/HL/LH)
- **Script 04:** Person-level allocation impact — counterfactual counts if one source’s total were spread with the other’s spatial pattern (summary table; optional maps and per-cell GPKG)
- **Script 03a:** Associational models — Residual ~ Poverty + Distance + Density (covariate-adjusted), diagnostics (VIF, heteroskedasticity)
- **Script 03b:** Stratified analysis, Gini by poverty quintile, interactions
- **Script 03c:** Spatial regression (SLM, SEM), including treatment effects (τ) vs OLS
- **Script 03d:** Bivariate maps (Poverty × Residual) in R
- **Script 03e:** Causal setup — treatment/outcome definitions, multiple estimators (regression, IPW, doubly robust)
- **Script 03f:** Robustness — SEM and related checks under alternative specifications

**Technical reference (single place):** `[pipeline/PIPELINE.md](pipeline/PIPELINE.md)` — `./run` options, Python+R step order with commands, script ↔ file mapping, output tree, publication-style figures. `config/README.md` explains `regions.json`; `cross-city/README.md` explains multi-city tables and figures.

## Prerequisites

- **Python 3.9+** (with conda recommended: `conda activate geo_env_LLM`)
- **R 4.0+** for pipeline and cross-city plotting



### Python packages

```bash
pip install -r requirements.txt
```

Main dependencies: geopandas, rasterio, rasterstats, pandas, numpy, scipy, matplotlib, statsmodels, libpysal, esda, spreg.

### R packages

```r
install.packages(c("sf", "ggplot2", "dplyr", "patchwork", "biscale", "cowplot"))
```

Cross-city scripts also need `tidyr`: see `cross-city/README.md`.

## Quick Start



### 1. Run the pipeline

**The one entry point** (Bash wrapper, zsh-safe) is `./run`, which calls `pipeline/run_all.sh`. If the Meta baseline GPKG is missing, it is built from the PDC zip first, then every Python step and the matching R script run in the same order as the [manual recipe in](pipeline/PIPELINE.md#manual-step-by-step-order) `pipeline/PIPELINE.md` (01 → 02 → 04 → 03a–03f, with 01/02/03a–c/03e/03f each followed by their `*_plots.R` where applicable; 03d is R-only).

```bash
# All selected cities in a country (clipped in step 01)
./run --region PHI
./run --region KEN
./run --region MEX          # Mexico City, Puebla, León
./run --region IDN          # Medan, Banda Aceh (not the unclipped extract)

# Unclipped Meta extract — all cells in the event AOI (slow). PHI/KEN/MEX have no extract region.
./run --region IDN --all
./run --region LKA --all
./run --region COL --all
./run --region ECU --all
./run --region ZAF --all

# Every selected city in every country
./run --all
./run --all --no-basemap

# Options (apply to the country run)
./run --region KEN --ref-hour 8
./run --region KEN --poverty-source rwi
./run --region KEN --clip-source geob
./run --region PHI --start-from 03b
```

To run scripts **manually** (or to see every `Rscript` line the wrapper uses), use only `pipeline/PIPELINE.md` **[→ Manual step-by-step order](pipeline/PIPELINE.md#manual-step-by-step-order)** so the list is not duplicated here.

### 2. Cross-city comparison

After running per-region pipelines (or `./run --all`):

```bash
python cross-city/run_cross_city_table.py --aggregate-only
python cross-city/run_cross_city_table.py --regions PHI,KEN,MEX
python cross-city/run_cross_city_table.py --include-full
```

**Figures:** `Rscript cross-city/figures_cross_city.R` (PNGs in `figure/cross-city/`).

Tables, figure filenames, and options: `cross-city/README.md`.

## Data defaults

Poverty defaults to **GRDI v1.10** at `data/raw/povmap-grdi-v1-10.tif` (global GeoTIFF; place the file there, it is gitignored). WorldPop country rasters live in `data/raw/worldpop/` (also gitignored). Per-region Meta RWI CSVs stay in `config/regions.json` under `poverty` for `--poverty-source rwi`.

Override defaults from `config/regions.json` with CLI flags, e.g.:

```bash
python pipeline/01_harmonise_datasets.py --region KEN_Nairobi
python pipeline/01_harmonise_datasets.py --region KEN_Nairobi --poverty-source rwi
python pipeline/01_harmonise_datasets.py --worldpop /path/to.tif --meta /path/to.gpkg --poverty /path/to/poverty.tif
python pipeline/01_harmonise_datasets.py --filter-by both --filter-min 50
```



## License

No `LICENSE` file is included yet. Add one before public release or redistribution if you need explicit terms.