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

## Per-run folders (do not rename)

`./run --region CODE` still writes `outputs/{CODE}/`. Study cities stay at the top level:

Kenya `KEN_*` · Philippines `PHI_*` · Mexico City `MEX`, `MEX_Puebla`, `MEX_Leon` · Indonesia `IDN_Medan`, `IDN_BandaAceh` · Sri Lanka `LKA_*` · Colombia `COL_*` · Ecuador `ECU_*` · South Africa `ZAF_*`.

**Event baselines** (`IDN`, `LKA`, `COL`, `ECU`, `ZAF`) stay here too. City runs share those Meta GPKGs (`outputs/IDN/fb_baseline_median_h00.gpkg`, …). Do not move them.

`MEX` is Mexico City, not all of Mexico.

## Archived leftovers

`outputs/_archive/` — clip experiments (`*_local`), old mixed `cross-city/` dump, logs, incomplete `outputs/0` and `KEN/`, exploratory footprints figures.

Re-running `./run` on a city overwrites `outputs/{CITY}/`, not `paper/` or `_snapshots/`.

## Regenerating paper files

Cross-city figures (including the grouped SEM forest):

```bash
Rscript cross-city/figures_cross_city.R
```
