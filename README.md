# Residential Population Analysis

Harmonise **Meta** (Facebook Population During Crisis baseline) and **WorldPop** counts onto the Meta quadkey grid, then ask how **poverty / deprivation** (default **GRDI**; optional Meta **RWI**) relates to digital representation bias — Meta under- or over-representing people relative to WorldPop — and how that bias would change crisis-period inferences.

The study sample is **21 cities in 8 countries**, each clipped from a Meta event extract. A second product re-runs the same analysis on the **unclipped event footprint**.

## Study sample

| Country | Code | Cities | Meta hour (Pacific) |
|---------|------|--------|---------------------|
| Philippines | PHL | Cagayan de Oro, Davao City, Zamboanga City, General Santos | 8 |
| Kenya | KEN | Nairobi, Mombasa, Kisumu, Nakuru | 16 |
| Mexico | MEX | Mexico City, Puebla, León | 0 |
| Indonesia | IDN | Medan, Banda Aceh | 8 |
| Sri Lanka | LKA | Colombo, Kandy | 8 |
| Colombia | COL | Barranquilla, Cartagena | 0 |
| Ecuador | ECU | Cuenca, Guayaquil | 0 |
| South Africa | ZAF | Cape Town, Garden Route | 16 |

Hour is chosen so the snapshot sits near evening locally. Default baseline method is **n_baseline**. Philippines is **PHL** (not PHI). Mexico City is config code `MEX_MexicoCity` → folder `MexicoCity/`.

## What the pipeline does

1. **01** Harmonise Meta, WorldPop, and poverty onto the quadkey grid (city clip).
2. **01b** Meta coverage QA on an independent city grid: published vs eligible-but-unpublished tiles (\(C_c = N_{\mathrm{published}}/N_{\mathrm{grid}}\)).
3. **02** Spatial agreement, inequality (Gini/Lorenz), residuals, hotspot overlap.
4. **04a** Allocation impact: counterfactual counts if one source’s total followed the other’s spatial pattern.
5. **04b** Crisis inference sensitivity: hold Meta crisis counts and the Meta baseline total fixed, reallocate that total with WorldPop’s pattern; direction-flip %, hotspot Jaccard, deprivation-patterned ΔF.
6. **03a–03f** Poverty models (OLS, strata, SEM τ, bivariate maps, causal estimators, robustness including Meta low-count and privacy-censoring checks).

**Technical reference:** [`pipeline/PIPELINE.md`](pipeline/PIPELINE.md) — `./run` options, Python+R step order, script ↔ file mapping, output tree. [`config/README.md`](config/README.md) is region paths; [`cross-city/README.md`](cross-city/README.md) is multi-city / cross-country tables and figures; [`data/README.md`](data/README.md) is source files.

## Two products

| Product | Command | Tables / figures | Harmonised data |
|---------|---------|------------------|-----------------|
| **Cities** (clipped) | `./run --region PHL` (or `KEN`, `MEX`, `IDN`, `LKA`, `COL`, `ECU`, `ZAF`) | `outputs/city/{COUNTRY}/{city}/`, `figure/city/{COUNTRY}/{city}/` | `data/processed/city/{COUNTRY}/{city}/` |
| **Event footprint** (PDC AOI, no city clip) | `./run --footprint KEN` | `outputs/footprints/{CODE}/`, `figure/footprints/{CODE}/` | `data/processed/footprints/` |
| **Cross-city** | `python cross-city/run_cross_city_table.py --aggregate-only` then `Rscript cross-city/figures_cross_city.R` | `outputs/cross-city/`, `figure/cross-city/` | — |
| **Cross-country** | `python cross-city/run_cross_country_table.py` then `Rscript cross-city/figures_cross_country.R` | `outputs/cross-country/`, `figure/cross-country/` | — |

`./run --all` is every selected **city**. It does not write footprints. Shared city Meta baselines live in `data/baselines/{COUNTRY}/fb_baseline_median_h{00|08|16}.gpkg`. ISO3-only keys with `clip_shape` unset (`IDN`, `LKA`, `COL`, `ECU`, `ZAF`) are data donors, not a city run: use `./run --region IDN` for Medan and Banda Aceh, or `./run --footprint IDN` for the event AOI.

Quote live tables from `outputs/cross-city/` (regenerated). Those folders are gitignored.

## Prerequisites

- **Python 3.9+** (conda recommended: `conda activate geo_env_LLM`)
- **R 4.0+** for pipeline, cross-city, and cross-country plotting

### Python packages

```bash
pip install -r requirements.txt
```

Main dependencies: geopandas, rasterio, rasterstats, pandas, numpy, scipy, matplotlib, statsmodels, libpysal, esda, spreg.

### R packages

```r
install.packages(c("sf", "ggplot2", "dplyr", "patchwork", "biscale", "cowplot", "tidyr"))
```

## Quick start

### 1. Per-city pipeline

`./run` is the entry point (Bash wrapper around `pipeline/run_all.sh`). Missing Meta baseline GPKGs are built from the PDC zip first. Order: 01 → 01b → 02 → 04a → 04b → 03a–03f, with matching `*_plots.R` (03d is R-only).

```bash
# All selected cities in a country
./run --region PHL
./run --region KEN
./run --region MEX          # Mexico City, Puebla, León
./run --region IDN          # Medan, Banda Aceh
./run --region LKA          # Colombo, Kandy
./run --region COL          # Barranquilla, Cartagena
./run --region ECU          # Cuenca, Guayaquil
./run --region ZAF          # Cape Town, Garden Route

# Event Meta footprint — one country at a time (no city clip)
./run --footprint KEN
./run --footprint IDN
python pipeline/qa_footprints.py --footprint KEN
bash pipeline/run_footprint_prep.sh KEN --prep-only   # labels only

# Every selected city in every country
./run --all
./run --all --no-basemap

# Options
./run --region KEN --ref-hour 8
./run --region KEN --poverty-source rwi
./run --region KEN --clip-source geob
./run --region PHL --start-from 03b
```

Manual Python/R lines: [`pipeline/PIPELINE.md`](pipeline/PIPELINE.md#manual-step-by-step-order).

### 2. Cross-city comparison

After city runs (or `./run --all`):

```bash
python cross-city/run_cross_city_table.py --aggregate-only
python cross-city/run_cross_city_table.py --regions PHL,KEN,MEX,IDN,LKA,COL,ECU,ZAF
Rscript cross-city/figures_cross_city.R
```

Tables include Table 1 (Meta vs WorldPop), Table 1b (coverage \(C_c\)), Table 2 (SEM τ), Table 2b–2d (Meta-count / censoring robustness), Table 4c (crisis inference sensitivity). Figures: `figure/cross-city/`.

### 3. Cross-country comparison (event footprints)

After `./run --footprint COUNTRY` for each country:

```bash
python cross-city/run_cross_country_table.py
Rscript cross-city/figures_cross_country.R
```

Tables in `outputs/cross-country/`; figures in `figure/cross-country/` (no residual-map panel). Details: [`cross-city/README.md`](cross-city/README.md).

## Data defaults

Poverty defaults to **GRDI v1.10** at `data/raw/povmap-grdi-v1-10.tif` (gitignored). WorldPop country rasters live in `data/raw/worldpop/` (also gitignored). Per-region Meta RWI CSVs stay in `config/regions.json` under `poverty` for `--poverty-source rwi`.

```bash
python pipeline/01_harmonise_datasets.py --region KEN_Nairobi
python pipeline/01_harmonise_datasets.py --region KEN_Nairobi --poverty-source rwi
python pipeline/01_harmonise_datasets.py --worldpop /path/to.tif --meta /path/to.gpkg --poverty /path/to/poverty.tif
python pipeline/01_harmonise_datasets.py --filter-by both --filter-min 50
```

## License

No `LICENSE` file is included yet. Add one before public release or redistribution if you need explicit terms.
