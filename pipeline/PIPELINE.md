# Analysis Pipeline

Run from project root. Scripts use default paths; `-i` can be omitted.

## Run all at once

```bash
./pipeline/run_all.sh
# Or with options:
./pipeline/run_all.sh --no-basemap               # Skip basemap tiles (avoids memory limit)
./pipeline/run_all.sh --region philippines        # Force Philippines zoom for maps
./pipeline/run_all.sh --skip-harmonise            # Skip step 1 (use existing harmonised data)
```

## Script structure

| Script | Purpose | Input (default) | Output |
|--------|---------|-----------------|--------|
| **01** | Harmonise + descriptive maps | WorldPop, Meta, Poverty | `01/` |
| **02** | Compare Meta vs WorldPop: spatial agreement, rank agreement, distribution, inequality, spatial structure, residuals, typology | `01/harmonised_meta_worldpop.gpkg` | `02/` |
| **03a** | Associational models: Residual ~ Poverty + Distance + Density (covariate-adjusted), diagnostics (VIF, heteroskedasticity) | `02/harmonised_with_residual.gpkg` | `03a_regression/` |
| **03b** | Stratified + Gini by poverty quintile | `02/harmonised_with_residual.gpkg` | `03b_stratified/` |
| **03c** | Spatial regression (SLM, SEM) with causal T: Y=ρWY+τT+Xβ+ε, τ comparison | `02/harmonised_with_residual.gpkg` | `03c_spatial_regression/` |
| **03d** | Bivariate map: Poverty × Residual (R) | `02/harmonised_with_residual.gpkg` | `03d_bivariate/` |
| **03e** | Causal setup + 3 estimators: (1) covariate-adjusted regression, (2) IPW, (3) Doubly Robust/Double ML | `02/harmonised_with_residual.gpkg` | `03e_causal/` |
| **03f** | Sensitivity analyses: baseline SEM, continuous poverty, top/bottom quintile, drop top 5% density, drop central 10% | `02/harmonised_with_residual.gpkg` | `03f_robustness/` |

**Note:** 03a, 03b, and the R bivariate map require `poverty_mean` in the 02 output. Run 01 with poverty (default); use `--no-poverty` only if skipping poverty analysis.

## Run order

```bash
# 1. Harmonise (WorldPop + Meta + Poverty; all use default paths)
python pipeline/01_harmonise_datasets.py

# 2. Compare Meta vs WorldPop (global total scaling: Meta scaled to match WorldPop totals)
python pipeline/02_compare_meta_worldpop.py
Rscript pipeline/02_plots.R   # Nature-style figures

# 3a. Associational models: Residual ~ Poverty + Distance + Density, diagnostics
python pipeline/03a_regression.py
Rscript pipeline/03a_plots.R   # Nature-style figures

# 3b. Stratified + inequality
python pipeline/03b_stratified.py
Rscript pipeline/03b_plots.R   # Nature-style figures

# 3c. Spatial regression (SLM, SEM only)
python pipeline/03c_spatial_regression.py
Rscript pipeline/03c_plots.R   # Nature-style residual maps

# 3d. Bivariate map: Poverty × Residual (R)
Rscript pipeline/03d_bivariate_map_poverty_residual.R   # --residual-var for alternatives

# 3e. Causal setup: Treatment, Outcome, Controls, Estimand
python pipeline/03e_causal.py
Rscript pipeline/03e_plots.R   # Nature-style forest plot

# 3f. Sensitivity analyses (SEM under various filters)
python pipeline/03f_robustness.py
Rscript pipeline/03f_plots.R   # Nature-style forest plot
```

## Output organisation

All outputs are nested under their script number:

```
outputs/
├── 01/
│   ├── harmonised_meta_worldpop.gpkg
│   ├── 01_data_overview.png         # optional (--plot or Rscript 01_plot_descriptive.R)
│   ├── 01_bivariate_worldpop_meta.png
│   └── 01_bivariate_worldpop_meta_basemap.png   # optional (requires network for tiles)
├── 02/
│   ├── harmonised_with_residual.gpkg
│   ├── 02_distribution_histogram_kde.png
│   ├── 02_lorenz_curves.png
│   ├── 02_rank_agreement.csv
│   ├── 02_lisa_worldpop.png, 02_lisa_meta.png
│   ├── 02_hotspot_overlap_map.png, 02_hotspot_overlap.csv
│   ├── 02_agreement_typology_median.png, 02_agreement_typology_quartile.png
│   ├── Table1_meta_worldpop_metrics.csv
│   └── 02_*_r.png (Nature-style from 02_plots.R, same names with _r suffix)
├── 03a_regression/
│   ├── Table2_regression.csv
│   ├── Table2b_VIF.csv
│   ├── Table2b_heteroskedasticity.csv
│   ├── regression_coefficients.csv
│   └── 03a_residual_distribution_r.png # from 03a_plots.R
├── 03b_stratified/
│   ├── Table_interaction.csv
│   ├── marginal_effects_poverty_r.png  # from 03b_plots.R
│   ├── Table3_poverty_strata.csv
│   ├── Table4_gini_by_quintile.csv
│   ├── residual_by_poverty_strata_r.png
│   └── gini_by_poverty_quintile_r.png
├── 03c_spatial_regression/
│   ├── Table_spatial_regression_full.csv
│   ├── Table3_SLM_SEM_coefficients.csv
│   ├── Table_tau_comparison.csv                 # τ across OLS, SLM, SEM
│   ├── Table_model_comparison.csv
│   ├── Table_Moran_residuals_diagnostic.csv
│   ├── 03c_residuals_for_plots.gpkg             # for 03c_plots.R
│   ├── slm_residual_map_r.png                   # from 03c_plots.R
│   └── sem_residual_map_r.png                   # from 03c_plots.R
├── 03d_bivariate/
│   ├── 03d_bivariate_poverty_residual.png       # Poverty × Residual
│   └── 03d_bivariate_poverty_residual_basemap.png   # optional
├── 03e_causal/
│   ├── 03e_causal_definitions.csv               # Treatment, Outcome, Controls, Estimand
│   ├── 03e_treatment_summary.csv                 # N, cutoff, τ_naive
│   ├── 03e_estimators.csv                       # τ, robust SE, exp(τ) for 3 estimators
│   ├── 03e_estimators_forest_r.png              # from 03e_plots.R
│   └── 03e_causal_analysis.gpkg                 # T, Y, log_pop_density added
└── 03f_robustness/
    ├── Table_robustness_summary.csv              # τ, SE, p-value by specification
    └── 03f_robustness_forest_r.png              # from 03f_plots.R
```

## Optional

- **01_plot_descriptive.R** — Descriptive figures (data overview + bivariate, saved separately): `Rscript pipeline/01_plot_descriptive.R` (or `python pipeline/01_harmonise_datasets.py --plot`)
- **03d_bivariate_map_poverty_residual.R** — Poverty × Residual (from 02): `Rscript pipeline/03d_bivariate_map_poverty_residual.R`

## Nature-style figures (R)

Plots for 02 and 03a–03f are produced by R scripts with a clean, publication-ready style. R outputs use the `_r` suffix (e.g. `02_density_histogram_r.png`) so they do not overwrite Python figures.
- **02_plots.R** — Density histograms, scatter, distribution, Lorenz, CDF, allocation map, typology, LISA, hotspot
- **03a_plots.R** — Residual distribution (histogram + KDE)
- **03b_plots.R** — Marginal effects, boxplot by stratum, Gini by quintile
- **03c_plots.R** — SLM/SEM residual choropleth maps
- **03e_plots.R** — Forest plot of causal estimators (τ)
- **03f_plots.R** — Forest plot of robustness specifications
