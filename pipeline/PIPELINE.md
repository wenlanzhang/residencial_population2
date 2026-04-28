# Analysis pipeline (technical reference)

**Use this file for:** how to run the full pipeline, resume from a step, **manual** Python/R order (same as the shell wrapper), script purposes, and the full **output file tree**. The [README](../README.md) is the short onboarding page; it defers here for technical detail.

**Other docs:** [Region & data paths → `config/README.md`](../config/README.md) · [Cross-city tables/figures → `cross-city/README.md`](../cross-city/README.md)

---

## Run the full pipeline (single entry point)

From the **repository root**, use the wrapper (always Bash — avoids zsh issues with some arguments):

```bash
./run --region PHI_CagayandeOroCity
```

This is equivalent to:

```bash
bash pipeline/run_all.sh --region PHI_CagayandeOroCity
```

The `run` script in the repo root is a thin wrapper: `exec bash pipeline/run_all.sh "$@"`.

### Wrapper options

| Option | Meaning |
|--------|---------|
| `--region CODE` | One region code, or a **prefix** that expands to all matches: `PHI` → both Philippines cities; `KEN` → Nairobi + Mombasa; or full codes: `PHI_CagayandeOroCity`, `PHI_DavaoCity`, `KEN_Nairobi`, `KEN_Mombasa`, `MEX`, `PRT`. |
| `--all` | Run the pipeline for every region in `config/regions.json` (mutually exclusive with `--region`). |
| `--ref-hour HOUR` | Meta baseline hour: **0**, **8**, or **16**. Must match a built file `outputs/{REGION}/fb_baseline_median_h{00|08|16}.gpkg` (build with `data_prep/build_fb_baseline_median.py --ref-hour …`). |
| `--no-basemap` | Skip basemap tiles in R maps (less memory / no network). Forwarded to R scripts that support it. |
| `--start-from STEP` | Skip all steps **before** `STEP` and run from there through **03f**. Valid: `01`, `02`, `04`, `03a`, `03b`, `03c`, `03d`, `03e`, `03f`. |

**Execution order** (same in the wrapper and in [Manual step-by-step order](#manual-step-by-step-order) below):

`01` (harmonise) → `01_plot_descriptive.R` → `02` (compare) → `02_plots.R` → `04` (impact) → `03a` + `03a_plots.R` → `03b` + `03b_plots.R` → `03c` + `03c_plots.R` → `03d` (R only) → `03e` + `03e_plots.R` → `03f` + `03f_plots.R`.

**Output layout:** With `--region REGION`, outputs go under `outputs/{REGION}/`. If you call `run_all.sh` **without** `--region` (not typical for multi-city work), scripts use the flat layout `outputs/01/`, `outputs/02/`, etc. See [config/README.md](../config/README.md).

**Poverty-dependent steps:** 03a, 03b, 03d, 03e, and 03f require `poverty_mean` from step 01. Run 01 with poverty (default). Use `--no-poverty` on harmonise only if you skip those analyses.

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

R plot outputs are often suffixed `_r.png` so they do not overwrite Python figures. `01_plot_descriptive.R` does not use the `_r` suffix in the same way; it writes the `01_*.png` maps in `01/`.

---

## Script structure (inputs & outputs)

| Step | Purpose | Default input | Default output dir |
|------|---------|---------------|----------------------|
| **01** | Harmonise WorldPop, Meta, poverty to quadkeys; optional basemap figures | Rasters + GPKG from `config/regions.json` | `outputs/{REGION}/01/` |
| **02** | Compare Meta vs WorldPop: agreement, ranks, distributions, inequality, spatial tests, residuals, typology | `01/harmonised_meta_worldpop.gpkg` | `outputs/{REGION}/02/` |
| **04** | Person-level allocation impact (counterfactuals, L1 transfer) | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/04_impact/` |
| **03a** | Residual ~ poverty + distance + density; OLS, VIF, heteroskedasticity | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03a_regression/` |
| **03b** | Strata, Gini by poverty quintile, interactions | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03b_stratified/` |
| **03c** | SLM, SEM; treatment effect τ vs OLS | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03c_spatial_regression/` |
| **03d** | Bivariate map: poverty × residual | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03d_bivariate/` |
| **03e** | Causal definitions + estimators (regression, IPW, doubly robust) | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03e_causal/` |
| **03f** | Robustness / alternative SEM specs | `02/harmonised_with_residual.gpkg` | `outputs/{REGION}/03f_robustness/` |

---

## Manual step-by-step order

Use the same order as `./run`. Set `REGION` and paths to match your run; with `--region`, `GPKG_01` and `GPKG_02` are `outputs/$REGION/01/harmonised_meta_worldpop.gpkg` and `outputs/$REGION/02/harmonised_with_residual.gpkg`, and `OUT=outputs/$REGION`.

```bash
REGION=PHI_CagayandeOroCity
OUT=outputs/$REGION
G01=$OUT/01/harmonised_meta_worldpop.gpkg
G02=$OUT/02/harmonised_with_residual.gpkg

# 01 + descriptive R
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

With `--region`, paths are `outputs/{REGION}/…`. Example layout:

```
outputs/{REGION}/
├── 01/
│   ├── harmonised_meta_worldpop.gpkg
│   ├── 01_data_overview_raw.png, 01_data_overview_log1p.png   # from R / --plot
│   ├── 01_share_maps.png
│   ├── 01_bivariate_worldpop_meta.png
│   └── 01_bivariate_worldpop_meta_basemap.png   # optional; network for tiles
├── 02/
│   ├── harmonised_with_residual.gpkg
│   ├── Table1_meta_worldpop_metrics.csv
│   ├── 02_*.{png,csv}
│   └── 02_*_r.png   # from 02_plots.R
├── 04_impact/
│   ├── Table4_impact_population_summary.csv
│   └── optional maps / per-cell GPKG from CLI flags
├── 03a_regression/
│   ├── Table2_regression.csv, Table2b_*.csv, regression_coefficients.csv
│   └── 03a_residual_distribution_r.png
├── 03b_stratified/
│   ├── Table_interaction.csv, Table3_poverty_strata.csv, Table4_gini_by_quintile.csv
│   └── plots from 03b_plots.R
├── 03c_spatial_regression/
│   ├── Table_spatial_regression_full.csv, Table3_SLM_SEM_coefficients.csv
│   ├── Table_tau_comparison.csv, Table_model_comparison.csv
│   ├── Table_Moran_residuals_diagnostic.csv
│   ├── 03c_residuals_for_plots.gpkg
│   └── slm_residual_map_r.png, sem_residual_map_r.png
├── 03d_bivariate/
│   ├── 03d_bivariate_poverty_residual.png
│   └── 03d_bivariate_poverty_residual_basemap.png   # optional
├── 03e_causal/
│   ├── 03e_causal_definitions.csv, 03e_treatment_summary.csv, 03e_estimators.csv
│   ├── 03e_estimators_forest_r.png
│   └── 03e_causal_analysis.gpkg
└── 03f_robustness/
    ├── Table_robustness_summary.csv
    └── 03f_robustness_forest_r.png
```

Cross-city aggregation and figures: see [`cross-city/README.md`](../cross-city/README.md) and `outputs/cross-city/`.
