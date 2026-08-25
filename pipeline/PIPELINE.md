# Analysis pipeline (technical reference)

**Use this file for:** how to run the full pipeline, resume from a step, **manual** Python/R order (same as the shell wrapper), script purposes, and the full **output file tree**. The [README](../README.md) is the short onboarding page; it defers here for technical detail.

**Other docs:** [Region & data paths → `config/README.md`](../config/README.md) · [Cross-city tables/figures → `cross-city/README.md`](../cross-city/README.md)

---

## Run the full pipeline (single entry point)

From the **repository root**, use the wrapper (always Bash — avoids zsh issues with some arguments):

```bash
./run --region PHI
./run --region MEX
./run --region IDN --all
```

This is equivalent to:

```bash
bash pipeline/run_all.sh --region PHI
```

The `run` script in the repo root is a thin wrapper: `exec bash pipeline/run_all.sh "$@"`.

### Wrapper options

| Option | Meaning |
|--------|---------|
| `--region COUNTRY` | All **selected cities** in that country. `PHI`, `KEN`, `MEX` (Mexico City + Puebla + León), `IDN` (Medan + Banda Aceh), `LKA`, `COL`, `ECU`, `ZAF`. |
| `--region COUNTRY --all` | Unclipped Meta **extract** (all cells in the event AOI). Configured for `IDN`, `LKA`, `COL`, `ECU`, `ZAF` only. |
| `--all` | All selected cities in every country (no event extracts). |
| `--one CODE` | Resume a single output folder (e.g. `KEN_Nairobi`). Not the usual entry point. |
| `--ref-hour HOUR` | Meta baseline hour: **0**, **8**, or **16**. Uses `outputs/{REGION}/fb_baseline_median_h{00|08|16}.gpkg`. If that file is missing, `./run` builds it from the PDC zip before step 01. |
| `--poverty-source SOURCE` | Poverty layer for step 01: **`grdi`** (default, `data/raw/povmap-grdi-v1-10.tif`) or **`rwi`** (per-region Meta RWI CSV in `regions.json`). Re-run from 01 after switching. |
| `--clip-source SOURCE` | City boundary for step 01: **`local`** (default, `clip_shape` file), **`osm`** (OSMnx/Nominatim), or **`geob`** (geoBoundaries). See [`config/README.md`](../config/README.md). Re-run from 01 after switching. `--clip-refresh` ignores the download cache. |
| `--no-basemap` | Skip basemap tiles in R maps (less memory / no network). Forwarded to R scripts that support it. |
| `--start-from STEP` | Skip all steps **before** `STEP` and run from there through **03f**. Valid: `01`, `02`, `04`, `03a`, `03b`, `03c`, `03d`, `03e`, `03f`. |

**Execution order** (same in the wrapper and in [Manual step-by-step order](#manual-step-by-step-order) below):

`01` (harmonise) → `01_plot_descriptive.R` → `02` (compare) → `02_plots.R` → `04` (impact) → `03a` + `03a_plots.R` → `03b` + `03b_plots.R` → `03c` + `03c_plots.R` → `03d` (R only) → `03e` + `03e_plots.R` → `03f` + `03f_plots.R`.

**Output layout:** With `--region REGION`, outputs go under `outputs/{REGION}/`. If you call `run_all.sh` **without** `--region` (not typical for multi-city work), scripts use the flat layout `outputs/01/`, `outputs/02/`, etc. See [config/README.md](../config/README.md).

**Poverty-dependent steps:** 03a, 03b, 03d, 03e, and 03f require `poverty_mean` from step 01. Default poverty layer is **GRDI** (higher = more deprived). Pass `--poverty-source rwi` to use Meta RWI instead (`poverty_mean = -RWI`). Use `--no-poverty` on harmonise only if you skip those analyses.

---

## Script index (Python + R)

| Order | Python | R (publication-style / maps) |
|-------|--------|------------------------------|
| 01 | `01_harmonise_datasets.py` | `01_plot_descriptive.R` |
| 02 | `02_compare_meta_worldpop.py` | `02_plots.R` |
| 04 | `04_impact.py` | — |
| 03a | `03a_regression.py` | `03a_plots.R` |
| 03b | `03b_stratified.py` | `03b_plots.R` |
| 03c | `03c_spatial_regression.py` | `03c_plots.R` |
| 03d | — | `03d_bivariate_map_poverty_residual.R` |
| 03e | `03e_causal.py` | `03e_plots.R` |
| 03f | `03f_robustness.py` | `03f_plots.R` |

Step **02** figures come from `02_plots.R` (`*_r.png`). Python 02 writes tables and the GPKG only, plus an optional allocation residual basemap. Other R plot outputs keep the `_r.png` suffix. `01_plot_descriptive.R` writes the `01_*.png` maps in `01/`.

---

## Script structure (inputs & outputs)

| Step | Purpose | Default input | Default output dir |
|------|---------|---------------|----------------------|
| **01** | Harmonise | Rasters + baseline GPKG | GPKG → `data/processed/.../01/`; maps → `figure/.../01/` |
| **02** | Compare Meta vs WorldPop | 01 GPKG | CSVs → `outputs/.../02/`; maps → `figure/.../02/` |
| **04** | Allocation impact | 02 GPKG | `outputs/.../04_impact/` + `figure/.../04_impact/` |
| **03a** | Residual ~ poverty OLS | 02 GPKG | `outputs/.../03a_regression/` |
| **03b** | Strata / Gini | 02 GPKG | `outputs/.../03b_stratified/` |
| **03c** | SLM, SEM τ | 02 GPKG | τ tables in `outputs/.../03c_spatial_regression/` |
| **03d** | Bivariate map | 02 GPKG | `figure/.../03d_bivariate/` |
| **03e** | Causal estimators | 02 GPKG | `outputs/.../03e_causal/` |
| **03f** | Robustness SEM | 02 GPKG | `outputs/.../03f_robustness/` |

---

## Manual step-by-step order

Use the same order as `./run`. Set `REGION` and paths to match your run; with `--region`, `GPKG_01` and `GPKG_02` are `outputs/$REGION/01/harmonised_meta_worldpop.gpkg` and `outputs/$REGION/02/harmonised_with_residual.gpkg`, and `OUT=outputs/$REGION`.

```bash
REGION=PHI_CagayandeOroCity
OUT=outputs/$REGION
G01=$OUT/01/harmonised_meta_worldpop.gpkg
G02=$OUT/02/harmonised_with_residual.gpkg

# 01 + descriptive R (default poverty: GRDI; add --poverty-source rwi for Meta RWI)
python pipeline/01_harmonise_datasets.py --region $REGION
Rscript pipeline/01_plot_descriptive.R -i "$G01" --region $REGION

# 02 + plots
python pipeline/02_compare_meta_worldpop.py --region $REGION
Rscript pipeline/02_plots.R -i "$G02" --region $REGION

# 04 impact (optional flags on script: --plot-map, --save-gpkg)
python pipeline/04_impact.py --region $REGION

# 03a–03f
python pipeline/03a_regression.py -i "$G02" -o "$OUT"
Rscript pipeline/03a_plots.R -i "$OUT/03a_regression" --region $REGION

python pipeline/03b_stratified.py -i "$G02" -o "$OUT"
Rscript pipeline/03b_plots.R -i "$OUT/03b_stratified" --region $REGION

python pipeline/03c_spatial_regression.py -i "$G02" -o "$OUT"
Rscript pipeline/03c_plots.R -i "$OUT/03c_spatial_regression" --region $REGION

Rscript pipeline/03d_bivariate_map_poverty_residual.R -i "$G02" -o "$OUT/03d_bivariate" --region $REGION

python pipeline/03e_causal.py -i "$G02" -o "$OUT"
Rscript pipeline/03e_plots.R -i "$OUT/03e_causal" --region $REGION

python pipeline/03f_robustness.py -i "$G02" -o "$OUT"
Rscript pipeline/03f_plots.R -i "$OUT/03f_robustness" --region $REGION
```

**Flags useful in ad-hoc runs:** e.g. `Rscript pipeline/03d_bivariate_map_poverty_residual.R … --residual-var …` for alternate residual columns; pass `--no-basemap` / `--ref-hour` consistently when mirroring `./run`.

---

## Publication-style R figures

Plots for **02** and **03a–03f** use a consistent figure style; filenames often end with `_r.png`.

| Script | Role |
|--------|------|
| `02_plots.R` | Density, scatter, Lorenz, CDF, allocation map, typology, LISA, hotspot (`02_*_r.png`) |
| `03a_plots.R` | Residual distribution |
| `03b_plots.R` | Marginal effects, strata, Gini by quintile |
| `03c_plots.R` | SLM/SEM residual choropleths (`*_residual_map_r.png`) |
| `03e_plots.R` | Forest plot of causal τ estimates |
| `03f_plots.R` | Forest plot of robustness specifications |

**Standalone alternatives:** `python pipeline/01_harmonise_datasets.py --plot` can trigger plotting from Python instead of/in addition to `01_plot_descriptive.R`.

---

## Output organisation

CSVs, figures, and GPKGs are split. Folders are created as needed.

```
outputs/{COUNTRY}/{city}/     # tables only, e.g. outputs/KEN/Nairobi/03c_spatial_regression/Table_tau_comparison.csv
outputs/{COUNTRY}/full/       # unclipped extract (--region IDN --all)
figure/{COUNTRY}/{city}/      # PNGs, same step subfolders
figure/{COUNTRY}/full/
data/processed/{COUNTRY}/{city|full}/   # harmonised GPKGs
data/baselines/{COUNTRY}/     # shared Meta baseline GPKG
data/raw/                    # WorldPop, GRDI, boundaries, GHSL (source files)
```

Mexico City is `outputs/MEX/MexicoCity/` (`MEX` in config). Event extracts use the `full` folder, not a city name.

Example:

```
outputs/KEN/Nairobi/02/Table1_meta_worldpop_metrics.csv
figure/KEN/Nairobi/02/02_lorenz_curves_r.png
data/processed/KEN/Nairobi/02/harmonised_with_residual.gpkg
data/baselines/KEN/fb_baseline_median_h00.gpkg
```

Cross-city tables: `outputs/cross-city/`. Cross-city figures: `figure/cross-city/`.
