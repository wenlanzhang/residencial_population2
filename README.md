# Residential Population Analysis

Analysis pipeline comparing **Meta** and **WorldPop** residential population estimates, with **poverty (MPI)** as an explanatory variable for digital representation bias.

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

**Technical reference (single place):** **[`pipeline/PIPELINE.md`](pipeline/PIPELINE.md)** — `./run` options, Python+R step order with commands, script ↔ file mapping, output tree, publication-style figures. **`config/README.md`** explains `regions.json`; **`cross-city/README.md`** explains multi-city tables and figures.

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

Cross-city scripts also need `tidyr`: see **`cross-city/README.md`**.

## Quick Start

### 1. Build Meta baseline (required before first run)

The pipeline uses Meta PDC (Population During Crisis) data. Build the baseline GPKG first:

```bash
# Single region or country prefix (PHI = both Philippines cities, KEN = both Kenya cities)
python data_prep/build_fb_baseline_median.py --region PHI_CagayandeOroCity
python data_prep/build_fb_baseline_median.py --region PHI
python data_prep/build_fb_baseline_median.py --region KEN

# All regions at once
python data_prep/build_fb_baseline_median.py --all

# With a specific reference hour (0, 8, or 16). Default is 0 (midnight) from config.
python data_prep/build_fb_baseline_median.py --region KEN_Nairobi --ref-hour 8
python data_prep/build_fb_baseline_median.py --all --ref-hour 8
```

**Output:** `outputs/{REGION}/fb_baseline_median_h{00|08|16}.gpkg`

**Reference hour:** Each region has `pdc_ref_hour` in `config/regions.json` (default 0). Use `--ref-hour` to override when building. When running the pipeline, pass `--ref-hour` to use that baseline (e.g. `./run --region KEN_Nairobi --ref-hour 8` uses `fb_baseline_median_h08.gpkg`).

**Manual paths (no config):**
```bash
python data_prep/build_fb_baseline_median.py -i /path/to/raw/PDC/folder -o outputs/fb_baseline_median.gpkg
python data_prep/build_fb_baseline_median.py -i outputs/PDC_Philippines_Basyang.csv -o outputs/fb_baseline_median.gpkg
```

### 2. Run the pipeline

**The one entry point** (Bash wrapper, zsh-safe) is **`./run`**, which calls `pipeline/run_all.sh`. It runs every Python step and the matching R script in the same order as the [manual recipe in `pipeline/PIPELINE.md`](pipeline/PIPELINE.md#manual-step-by-step-order) (01 → 02 → 04 → 03a–03f, with 01/02/03a–c/03e/03f each followed by their `*_plots.R` where applicable; 03d is R-only).

```bash
# Single region
./run --region PHI_CagayandeOroCity
# Or: bash ./pipeline/run_all.sh --region PHI_CagayandeOroCity

# Reference hour (build baseline with the same hour first)
./run --region PHI_CagayandeOroCity --ref-hour 8
./run --all --ref-hour 8

./run --all
./run --all --no-basemap          # Skip basemap tiles

./run --region PHI                # Philippines cities
./run --region KEN --no-basemap    # Nairobi + Mombasa

./run --region KEN_Nairobi
./run --region MEX --no-basemap

# Resume: 01, 02, 04, 03a, 03b, 03c, 03d, 03e, or 03f — see PIPELINE.md
./run --region PHI_CagayandeOroCity --start-from 03b
./run --region PHI_CagayandeOroCity --start-from 03f
```

To run scripts **manually** (or to see every `Rscript` line the wrapper uses), use only **[`pipeline/PIPELINE.md` → Manual step-by-step order](pipeline/PIPELINE.md#manual-step-by-step-order)** so the list is not duplicated here.

### 3. Cross-city comparison

After running per-region pipelines (or `./run --all`):

```bash
python cross-city/run_cross_city_table.py
python cross-city/run_cross_city_table.py --aggregate-only
python cross-city/run_cross_city_table.py --regions KEN_Nairobi,KEN_Mombasa,MEX,PHI_CagayandeOroCity
python cross-city/run_cross_city_table.py -o outputs/cross-city/
```

**Figures:** `Rscript cross-city/figures_cross_city.R -o outputs/cross-city/`

Tables, figure filenames, and options: **`cross-city/README.md`**.

## Data defaults

Override defaults from `config/regions.json` with CLI flags, e.g.:

```bash
python pipeline/01_harmonise_datasets.py --worldpop /path/to.tif --meta /path/to.gpkg --poverty /path/to/poverty.tif
python pipeline/01_harmonise_datasets.py --filter-by both --filter-min 50
```

## License

No `LICENSE` file is included yet. Add one before public release or redistribution if you need explicit terms.
