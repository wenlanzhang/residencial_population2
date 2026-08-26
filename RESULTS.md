# Results layout

Pipeline products live under `outputs/` (gitignored). This file is the map of what is canonical vs leftover.

## What to quote

`outputs/paper/` — frozen 2026-08-24 copy from branch `city` (`81e4839`):

| Path | Contents |
|------|----------|
| `paper/figures/Figure_sem_forest_all_cities.png` | Frozen SEM τ forest (live name: `figure/cross-city/03c_sem_forest.png`) |
| `paper/tables/Table_sem_tau_all_cities.csv` | Matching τ, SE, p, 95% CI |
| `paper/tau/{REGION}.csv` | SEM row from each city run |
| `paper/tables/Table1_*_11cities.csv` | Older 11-city Table 1 (not rebuilt for 21) |
| `paper/tables/Table2_*_11cities.csv` | Older 11-city Table 2 |

A second frozen copy is in `outputs/_snapshots/2026-08-24_city/`.

## Two products

| Product | Command | Tables / figures | Harmonised data |
|---------|---------|------------------|-----------------|
| **Cities** (clipped, full SEM/Gini stack) | `./run --region PHL` (or `KEN`, `MEX`, `IDN`, …) | `outputs/city/{COUNTRY}/{city}/`, `figure/city/{COUNTRY}/{city}/` | `data/processed/city/{COUNTRY}/{city}/` |
| **Meta event footprint** (PDC AOI, no city clip) | `./run --footprint KEN` | `outputs/footprints/{CODE}/`, QA under `outputs/footprints/qa/` | `data/processed/footprints/{CODE}/` |
| **Cross-city** | `python cross-city/run_cross_city_table.py --aggregate-only` then `Rscript cross-city/figures_cross_city.R` | `outputs/cross-city/`, `figure/cross-city/` | — |
| **Cross-country** | `python cross-city/run_cross_country_table.py` then `Rscript cross-city/figures_cross_country.R` | `outputs/cross-country/`, `figure/cross-country/` | — |

`./run --all` is every selected **city** in every country. It does not write footprints.

Philippines is **PHL** (not PHI). Mexico City is config code `MEX_MexicoCity` → folder `outputs/city/MEX/MexicoCity/`. Puebla and León are `outputs/city/MEX/Puebla/` and `outputs/city/MEX/Leon/`. `./run --region MEX` still means all Mexico cities. `./run --footprint MEX` is the earthquake AOI.

Shared city Meta baselines live in `data/baselines/{COUNTRY}/fb_baseline_median_h{00\|08\|16}.gpkg`. Footprint Meta files (when built) live under `outputs/footprints/{CODE}/meta/`.

Country keys with `clip_shape` unset (`IDN`, `LKA`, `COL`, `ECU`, `ZAF`) stay in `regions.json` as **data donors** (PDC/WorldPop paths). They are not a city: `python pipeline/01_harmonise_datasets.py --region IDN` is rejected. Use `./run --region IDN` for Medan and Banda Aceh, or `./run --footprint IDN` for the event AOI.

## Archived leftovers

`outputs/_archive/` — clip experiments (`*_local`), old mixed `cross-city/` dump, logs, incomplete `outputs/0` and `KEN/`, exploratory footprints figures.

Re-running `./run --region` overwrites that city's folders, not `paper/`, `_snapshots/`, or `outputs/footprints/`.

## Regenerating paper files

Cross-city figures (including the grouped SEM forest):

```bash
Rscript cross-city/figures_cross_city.R
```

Cross-country (footprints; no residual-map panel):

```bash
python cross-city/run_cross_country_table.py
Rscript cross-city/figures_cross_country.R
```
