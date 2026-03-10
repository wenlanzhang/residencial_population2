#! /Users/wenlanzhang/miniconda3/envs/geo_env_LLM/bin/python
from pathlib import Path
import geopandas as gpd
import pandas as pd
import numpy as np
import rasterio
from rasterstats import zonal_stats
import matplotlib.pyplot as plt
import seaborn as sns

'''
This script scales Facebook displacement data to WorldPop population estimates.

Scales three different outflow metrics:
1. 2_outflow_max (from step 2 - CSAT method)
2. 1_outflow_accumulated_hour0 (from step 1 - accumulated shortfall at hour 0)
3. 1_outflow_max_hour0 (from step 1 - maximum shortfall at hour 0)

Figure outputs (saved to FIGURE_DIR = /Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/3/):
For each metric, generates:
- 3_displacement_percentage_comparison_{metric_name}.png: Scatter and distribution comparison of outflow percentages
- 3_displacement_cell_count_comparison_{metric_name}.png: Comparison of cells with outflow (FB vs WorldPop)

Data output (saved to OUT_DIR = /Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/3/):
- 3_displacement_scaled_to_worldpop.gpkg: GeoPackage with scaled displacement data

Key columns created:
- 3_worldpop: Zonal sum of WorldPop raster per quadkey
- 3_fb_baseline_median: Median Facebook baseline per quadkey (from reference hour rows)
- 3_scaling_ratio: WorldPop / FB baseline ratio (for low FB coverage areas where fb_baseline < MIN_FB_BASELINE_FOR_UNCAPPED, uses global fallback only if per-cell ratio > global ratio; otherwise uses per-cell ratio)
- 3_estimated_outflow_pop_from_2_outflow_max: Scaled outflow in population units (2_outflow_max * scaling_ratio)
- 3_estimated_outflow_pop_from_1_outflow_accumulated_hour0: Scaled outflow in population units (1_outflow_accumulated_hour0 * scaling_ratio)
- 3_estimated_outflow_pop_from_1_outflow_max_hour0: Scaled outflow in population units (1_outflow_max_hour0 * scaling_ratio)
- 3_estimated_excess_displacement_pop: Scaled excess displacement in population units
- 3_pct_outflow_fb_from_*: FB displacement as % of FB baseline (for each metric)
- 3_pct_outflow_worldpop_from_*: WorldPop displacement as % of WorldPop population (for each metric)
- 3_used_global_ratio: Flag indicating cells that used global fallback ratio

Input files required:
- Data/1/1_agg_outflow_accumulated.gpkg: Step 1 output (for 1_outflow_accumulated_hour0 and 1_outflow_max_hour0)
- Data/2/2_agg_displacement_by_quadkey_outflow.gpkg: Step 2 output (for 2_outflow_max)
- Data/2/2_rows_with_displacement_outflow_{Reference_HOUR}.csv: Per-row displacement data (for FB baseline)
- WorldPop_clipped_aoi.tif: WorldPop raster for zonal statistics
'''

# ---------- User inputs ----------
Reference_HOUR = 0
Source_DIR_1 = Path("/Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/1/")  # Step 1 output
Source_DIR_2 = Path("/Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/2/")  # Step 2 output
OUT_DIR = Path('/Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/3/')
DISP_GPKG = Source_DIR_2 / f"2_agg_displacement_by_quadkey_outflow.gpkg"   # aggregated python output from step 2
STEP1_GPKG = Source_DIR_1 / "1_agg_outflow_accumulated.gpkg"  # Step 1 output
REF_ROWS_CSV = Source_DIR_2 / f"2_rows_with_displacement_outflow_{Reference_HOUR}.csv"     # per-row ref-hour results (to compute FB baseline)
WORLDPOP_RASTER = Path("/Users/wenlanzhang/Downloads/PhD_UCL/Data/Waste_flood/Worldpop/WorldPop_clipped_aoi.tif")
# OUT_PREFIX = OUT_DIR / "scaled"
FIGURE_DIR = Path('/Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/3/')

# Safety params
MAX_RATIO = 50.0      # cap per-cell ratio to avoid extreme amplification from tiny FB counts
MIN_FB_BASELINE_FOR_UNCAPPED = 50  # Only cap ratio if fb_baseline_median is below this threshold
                                    # Areas with fb_baseline_median >= this value use uncapped ratio
NEIGHBORHOOD_RADIUS = 1  # in grid cells for fallback; simple approach below uses global fallback if needed


# ---------- Load displacement GDF (one row per quadkey) ----------
disp_gdf = gpd.read_file(DISP_GPKG, layer=f"2_displacement_outflow")
print("Loaded displacement GDF:", disp_gdf.shape)

# Ensure quadkey exists
if 'quadkey' not in disp_gdf.columns:
    raise ValueError("displacement GPKG must have 'quadkey' column.")

# ---------- Load step 1 output to get 1_outflow_accumulated_hour0 and 1_outflow_max_hour0 ----------
print("\nLoading step 1 output...")
step1_gdf = gpd.read_file(STEP1_GPKG, layer="1_outflow_accumulated")
print(f"Loaded step 1 GDF: {step1_gdf.shape}")

# Ensure quadkey exists
if 'quadkey' not in step1_gdf.columns:
    raise ValueError("Step 1 GPKG must have 'quadkey' column.")

# Merge step 1 columns into disp_gdf
step1_cols_to_merge = ['quadkey', '1_outflow_accumulated_hour0', '1_outflow_max_hour0']
available_cols = [col for col in step1_cols_to_merge if col in step1_gdf.columns]
if len(available_cols) > 1:  # More than just 'quadkey'
    step1_subset = step1_gdf[available_cols].copy()
    disp_gdf = disp_gdf.merge(step1_subset, on='quadkey', how='left')
    print(f"Merged step 1 columns: {[col for col in available_cols if col != 'quadkey']}")
else:
    print("⚠️  Warning: Step 1 columns not found, skipping merge")


# ---------- Zonal sum of WorldPop raster per quadkey ----------
# Prepare geometries in same CRS as raster
with rasterio.open(WORLDPOP_RASTER) as src:
    raster_crs = src.crs
print("WorldPop raster CRS:", raster_crs)

# Reproject disp_gdf to raster CRS if needed
if disp_gdf.crs != raster_crs:
    disp_gdf = disp_gdf.to_crs(raster_crs)
    print("Reprojected displacement geometries to raster CRS.")

# Compute zonal sums (pixel values assumed to be counts)
print("Computing zonal sums of WorldPop per quadkey (this can take a minute)...")
zs = zonal_stats(
    vectors=disp_gdf.geometry,
    raster=str(WORLDPOP_RASTER),
    stats=['sum'],
    nodata=None,
    all_touched=True,      # decide whether to include any pixel touched by polygon
    geojson_out=False
)
# Attach worldpop sum
worldpop_sum = np.array([v['sum'] if v['sum'] is not None else 0.0 for v in zs])
disp_gdf['3_worldpop'] = worldpop_sum
print("Zonal sum complete. worldpop stats:", pd.Series(worldpop_sum).describe())


# ---------- Compute FB baseline per quadkey from ref_rows CSV ----------
# ref_rows should contain 'quadkey' and 'baseline' columns (multiple rows per quadkey across days)
ref_rows = pd.read_csv(REF_ROWS_CSV)

# Ensure quadkey is string in both dataframes
ref_rows['quadkey'] = ref_rows['quadkey'].astype(str)
disp_gdf['quadkey'] = disp_gdf['quadkey'].astype(str)

if 'quadkey' not in ref_rows.columns or 'baseline' not in ref_rows.columns:
    raise ValueError("ref_hour_rows_with_displacement.csv must contain 'quadkey' and 'baseline' columns.")

# Compute robust baseline estimate: median baseline for each quadkey (ref hour)
fb_baseline = (
    ref_rows.groupby('quadkey')['baseline']
    .median()
    .reset_index()
    .rename(columns={'baseline': '3_fb_baseline_median'})
)
print("Computed fb_baseline for n quadkeys:", fb_baseline.shape[0])

# Merge baseline into disp_gdf (left join)
disp_gdf = disp_gdf.merge(fb_baseline, on='quadkey', how='left')

# If some quadkeys have no fb_baseline (NaN), set to 0 to handle later
disp_gdf['3_fb_baseline_median'] = disp_gdf['3_fb_baseline_median'].fillna(0.0)


# ---------- Ensure outflow_max column exists ----------
# Look for 2_outflow_max from script 2
if '2_outflow_max' not in disp_gdf.columns:
    # attempt alternative column names
    if 'outflow_max' in disp_gdf.columns:
        disp_gdf['2_outflow_max'] = disp_gdf['outflow_max']
    elif 'outflow' in disp_gdf.columns:
        disp_gdf['2_outflow_max'] = disp_gdf['outflow']
    else:
        raise ValueError("displacement GDF must contain 2_outflow_max (or outflow_max/outflow).")

# Also keep displaced_excess_max for sensitivity (used to compute estimated_excess_displacement_pop)
if '2_displaced_excess_max' not in disp_gdf.columns:
    if 'displaced_excess_max' in disp_gdf.columns:
        disp_gdf['2_displaced_excess_max'] = disp_gdf['displaced_excess_max']
    else:
        disp_gdf['2_displaced_excess_max'] = np.nan


# ---------- Compute scaling ratio and safe fallbacks ----------
# Ratio = worldpop / fb_baseline_median  (how many real people per FB 'user' baseline)
# But we handle zeros and tiny denominators.

# Global fallback ratio (total worldpop / total fb baseline) - used for cells with fb_baseline < MIN_FB_BASELINE_FOR_UNCAPPED AND per-cell ratio > global ratio
total_worldpop = disp_gdf['3_worldpop'].sum()
total_fb_baseline = disp_gdf['3_fb_baseline_median'].sum()
global_ratio = (total_worldpop / total_fb_baseline) if (total_fb_baseline > 0) else np.nan

# Diagnostic: Compare total raster sum vs quadkey sum
with rasterio.open(WORLDPOP_RASTER) as src:
    raster_data = src.read(1)
    raster_nodata = src.nodata
    if raster_nodata is not None:
        raster_data = np.where(raster_data == raster_nodata, np.nan, raster_data)
    total_raster_pop = np.nansum(raster_data)

# Print totals for verification
print("\n" + "="*60)
print("TOTAL POPULATION SUMMARY (before scaling):")
print("="*60)
print(f"Total WorldPop in entire raster:     {total_raster_pop:,.0f}")
print(f"Total WorldPop in quadkey polygons:  {total_worldpop:,.0f}")
print(f"Coverage: {100 * total_worldpop / total_raster_pop:.1f}% of raster population")
print(f"Total Facebook baseline:             {total_fb_baseline:,.0f}")
print(f"Global ratio (WorldPop / FB baseline): {global_ratio:.4f}")
print("="*60 + "\n")

# Compute per-cell ratio
def compute_ratio(row, global_ratio, max_ratio=MAX_RATIO, min_fb_for_uncapped=MIN_FB_BASELINE_FOR_UNCAPPED):
    """
    Compute scaling ratio with conditional global fallback for low FB coverage:
    - If fb_baseline_median < min_fb_for_uncapped: 
        * Calculate per-cell ratio (wp / fb)
        * Use global_ratio only if per-cell ratio > global_ratio (safety check)
        * Otherwise use per-cell ratio
    - If fb_baseline_median >= min_fb_for_uncapped: use calculated per-cell ratio (wp / fb)
    """
    fb = float(row['3_fb_baseline_median'])
    wp = float(row['3_worldpop'])
    # if both zero -> ratio 0
    if wp == 0 and fb == 0:
        return 0.0, False  # Return tuple: (ratio, used_global)
    
    # Calculate per-cell ratio
    if fb > 0:
        per_cell_ratio = wp / fb
    else:
        per_cell_ratio = np.inf if wp > 0 else 0.0
    
    # For low FB coverage areas: use global if per-cell ratio is unreasonably high
    if fb < min_fb_for_uncapped:
        if not np.isnan(global_ratio) and per_cell_ratio > global_ratio:
            # Per-cell ratio is higher than global -> use global as safety fallback
            r = global_ratio
            used_global = True
        else:
            # Per-cell ratio is reasonable -> use it
            r = per_cell_ratio
            used_global = False
    else:
        # Reasonable FB coverage: always use per-cell ratio
        r = per_cell_ratio
        used_global = False
    
    # Ensure non-negative and finite
    if not np.isnan(r) and np.isfinite(r):
        r = max(r, 0.0)
    else:
        r = 0.0
        used_global = False
    
    return float(r), used_global

# Compute scaling ratios and track which cells used global fallback
ratio_results = disp_gdf.apply(
    lambda r: compute_ratio(r, global_ratio, max_ratio=MAX_RATIO, min_fb_for_uncapped=MIN_FB_BASELINE_FOR_UNCAPPED), 
    axis=1
)
disp_gdf['3_scaling_ratio'] = ratio_results.apply(lambda x: x[0])
disp_gdf['3_used_global_ratio'] = ratio_results.apply(lambda x: x[1]).astype(int)

# Diagnostics: how many used global fallback?

# Diagnostics: how many used per-cell ratio vs global fallback?
# Note: ratio_was_capped is no longer relevant since we use global fallback for low FB areas
disp_gdf['3_ratio_was_capped'] = 0  # Deprecated - kept for compatibility
n_used_global = disp_gdf['3_used_global_ratio'].sum()
n_used_per_cell = (disp_gdf['3_fb_baseline_median'] >= MIN_FB_BASELINE_FOR_UNCAPPED).sum()
n_uncapped_high_ratio = (
    (disp_gdf['3_fb_baseline_median'] >= MIN_FB_BASELINE_FOR_UNCAPPED) & 
    (disp_gdf['3_scaling_ratio'] > MAX_RATIO)
).sum()

# Diagnostic: Show distribution of scaling ratios across cells
print("\n" + "="*60)
print("SCALING RATIO DISTRIBUTION (per quadkey):")
print("="*60)
ratio_stats = pd.Series(disp_gdf['3_scaling_ratio']).describe()
print(ratio_stats)
print(f"\nNumber of cells using global fallback ratio (fb_baseline < {MIN_FB_BASELINE_FOR_UNCAPPED} AND per-cell ratio > global): {n_used_global}")
n_low_fb_used_per_cell = ((disp_gdf['3_fb_baseline_median'] < MIN_FB_BASELINE_FOR_UNCAPPED) & (disp_gdf['3_used_global_ratio'] == 0)).sum()
print(f"Number of low FB cells using per-cell ratio (fb_baseline < {MIN_FB_BASELINE_FOR_UNCAPPED} AND per-cell ratio <= global): {n_low_fb_used_per_cell}")
print(f"Number of cells using per-cell ratio (fb_baseline >= {MIN_FB_BASELINE_FOR_UNCAPPED}): {n_used_per_cell}")
print(f"Number of cells with high per-cell ratio > {MAX_RATIO}: {n_uncapped_high_ratio}")
print(f"Number of unique ratio values: {disp_gdf['3_scaling_ratio'].nunique()}")
print("="*60 + "\n")
disp_gdf.head()

# ---------- Compute estimated displacement in population units ----------
# Scale three different outflow metrics:
# 1. From step 2: 2_outflow_max
# 2. From step 1: 1_outflow_accumulated_hour0
# 3. From step 1: 1_outflow_max_hour0

# 1. Scale 2_outflow_max (from step 2)
disp_gdf['3_estimated_outflow_pop_from_2_outflow_max'] = disp_gdf['2_outflow_max'].fillna(0.0) * disp_gdf['3_scaling_ratio']

# 2. Scale 1_outflow_accumulated_hour0 (from step 1)
if '1_outflow_accumulated_hour0' in disp_gdf.columns:
    disp_gdf['3_estimated_outflow_pop_from_1_outflow_accumulated_hour0'] = disp_gdf['1_outflow_accumulated_hour0'].fillna(0.0) * disp_gdf['3_scaling_ratio']
else:
    disp_gdf['3_estimated_outflow_pop_from_1_outflow_accumulated_hour0'] = np.nan
    print("⚠️  Warning: 1_outflow_accumulated_hour0 not found, setting to NaN")

# 3. Scale 1_outflow_max_hour0 (from step 1)
if '1_outflow_max_hour0' in disp_gdf.columns:
    disp_gdf['3_estimated_outflow_pop_from_1_outflow_max_hour0'] = disp_gdf['1_outflow_max_hour0'].fillna(0.0) * disp_gdf['3_scaling_ratio']
else:
    disp_gdf['3_estimated_outflow_pop_from_1_outflow_max_hour0'] = np.nan
    print("⚠️  Warning: 1_outflow_max_hour0 not found, setting to NaN")

# Option B (sensitivity): scale raw displaced_excess_max similarly
disp_gdf['3_estimated_excess_displacement_pop'] = disp_gdf['2_displaced_excess_max'].fillna(0.0) * disp_gdf['3_scaling_ratio']

# Compute totals after scaling
total_outflow_pop_2 = disp_gdf['3_estimated_outflow_pop_from_2_outflow_max'].sum()
total_outflow_pop_1_acc = disp_gdf['3_estimated_outflow_pop_from_1_outflow_accumulated_hour0'].sum() if '1_outflow_accumulated_hour0' in disp_gdf.columns else np.nan
total_outflow_pop_1_max = disp_gdf['3_estimated_outflow_pop_from_1_outflow_max_hour0'].sum() if '1_outflow_max_hour0' in disp_gdf.columns else np.nan
total_excess_displacement_pop = disp_gdf['3_estimated_excess_displacement_pop'].sum()

# Print totals after scaling
print("\n" + "="*60)
print("TOTAL DISPLACEMENT SUMMARY (after scaling to population):")
print("="*60)
print(f"Total estimated outflow (from 2_outflow_max):                    {total_outflow_pop_2:,.0f} people")
if not np.isnan(total_outflow_pop_1_acc):
    print(f"Total estimated outflow (from 1_outflow_accumulated_hour0):     {total_outflow_pop_1_acc:,.0f} people")
if not np.isnan(total_outflow_pop_1_max):
    print(f"Total estimated outflow (from 1_outflow_max_hour0):            {total_outflow_pop_1_max:,.0f} people")
print(f"Total estimated excess displacement:                             {total_excess_displacement_pop:,.0f} people")
print("="*60 + "\n")


# ---------- Compute displacement percentages and comparison ----------
# Calculate percentage displacement from FB baseline
# Avoid division by zero
disp_gdf['3_fb_baseline_safe'] = disp_gdf['3_fb_baseline_median'].replace(0, np.nan)
disp_gdf['3_worldpop_safe'] = disp_gdf['3_worldpop'].replace(0, np.nan)

# Define metrics to process
metrics_config = [
    {
        'name': '2_outflow_max',
        'fb_col': '2_outflow_max',
        'wp_col': '3_estimated_outflow_pop_from_2_outflow_max',
        'pct_fb_col': '3_pct_outflow_fb_from_2_outflow_max',
        'pct_wp_col': '3_pct_outflow_worldpop_from_2_outflow_max'
    },
    {
        'name': '1_outflow_accumulated_hour0',
        'fb_col': '1_outflow_accumulated_hour0',
        'wp_col': '3_estimated_outflow_pop_from_1_outflow_accumulated_hour0',
        'pct_fb_col': '3_pct_outflow_fb_from_1_outflow_accumulated_hour0',
        'pct_wp_col': '3_pct_outflow_worldpop_from_1_outflow_accumulated_hour0'
    },
    {
        'name': '1_outflow_max_hour0',
        'fb_col': '1_outflow_max_hour0',
        'wp_col': '3_estimated_outflow_pop_from_1_outflow_max_hour0',
        'pct_fb_col': '3_pct_outflow_fb_from_1_outflow_max_hour0',
        'pct_wp_col': '3_pct_outflow_worldpop_from_1_outflow_max_hour0'
    }
]

# Compute percentages for each metric
for metric in metrics_config:
    if metric['fb_col'] in disp_gdf.columns:
        # FB displacement as % of FB baseline
        disp_gdf[metric['pct_fb_col']] = (disp_gdf[metric['fb_col']].fillna(0.0) / disp_gdf['3_fb_baseline_safe']) * 100
        # WorldPop displacement as % of WorldPop population
        disp_gdf[metric['pct_wp_col']] = (disp_gdf[metric['wp_col']] / disp_gdf['3_worldpop_safe']) * 100
    else:
        disp_gdf[metric['pct_fb_col']] = np.nan
        disp_gdf[metric['pct_wp_col']] = np.nan

# Print summary statistics
print("\n" + "="*60)
print("DISPLACEMENT PERCENTAGE COMPARISON:")
print("="*60)
for metric in metrics_config:
    if metric['fb_col'] in disp_gdf.columns:
        print(f"\n{metric['name']}:")
        print(f"  FB displacement as % of FB baseline:")
        print(f"    mean={disp_gdf[metric['pct_fb_col']].mean():.2f}%, median={disp_gdf[metric['pct_fb_col']].median():.2f}%")
        print(f"  WorldPop displacement as % of WorldPop population:")
        print(f"    mean={disp_gdf[metric['pct_wp_col']].mean():.2f}%, median={disp_gdf[metric['pct_wp_col']].median():.2f}%")
        
        # Calculate correlation
        valid_mask = (disp_gdf[metric['pct_fb_col']].notna() & disp_gdf[metric['pct_wp_col']].notna())
        if valid_mask.sum() > 0:
            corr = disp_gdf.loc[valid_mask, [metric['pct_fb_col'], metric['pct_wp_col']]].corr().iloc[0, 1]
            print(f"  Correlation: {corr:.4f}")
print("="*60 + "\n")


# ---------- Compute cell-count based displacement analysis ----------
# Count cells with displacement (by cell number, not headcount)
total_cells = len(disp_gdf)

# Print cell-count statistics
print("\n" + "="*60)
print("DISPLACEMENT BY CELL COUNT (Percentage of cells with displacement):")
print("="*60)
print(f"Total number of cells (quadkeys): {total_cells}")

for metric in metrics_config:
    if metric['fb_col'] in disp_gdf.columns:
        # FB: cells with outflow
        cells_with_outflow_fb = (disp_gdf[metric['fb_col']].fillna(0.0) > 0).sum()
        # WorldPop: cells with outflow
        cells_with_outflow_worldpop = (disp_gdf[metric['wp_col']] > 0).sum()
        
        # Calculate percentages
        pct_cells_outflow_fb = (cells_with_outflow_fb / total_cells) * 100
        pct_cells_outflow_worldpop = (cells_with_outflow_worldpop / total_cells) * 100
        
        print(f"\n{metric['name']}:")
        print(f"  Facebook displacement (by cell count):")
        print(f"    Cells with outflow:       {cells_with_outflow_fb:4d} ({pct_cells_outflow_fb:.1f}%)")
        print(f"  WorldPop displacement (by cell count):")
        print(f"    Cells with outflow:       {cells_with_outflow_worldpop:4d} ({pct_cells_outflow_worldpop:.1f}%)")
        
        diff = pct_cells_outflow_worldpop - pct_cells_outflow_fb
        print(f"  Difference: {diff:+.2f} percentage points")

print("\nNote: Small negative differences (e.g., -0.8%) are normal and expected.")
print("      This can occur because scaling can change which cells cross the zero threshold.")
print("      When FB values are small and scaled, some may become zero or change sign.")
print("="*60 + "\n")


# ---------- Create visualizations for each metric ----------
FIGURE_DIR.mkdir(parents=True, exist_ok=True)

def create_figures_for_metric(metric, plot_df):
    """Create percentage comparison and cell-count figures for a given metric."""
    metric_name_clean = metric['name'].replace('_', ' ').title()
    
    # Remove infinite and extreme values for plotting
    pct_fb_col = metric['pct_fb_col']
    pct_wp_col = metric['pct_wp_col']
    
    plot_df_clean = plot_df.copy()
    for col in [pct_fb_col, pct_wp_col]:
        if col in plot_df_clean.columns:
            plot_df_clean[col] = plot_df_clean[col].replace([np.inf, -np.inf], np.nan)
            # Cap extreme values at ±200% for visualization
            plot_df_clean[col] = plot_df_clean[col].clip(-200, 200)
    
    # Calculate correlation
    valid_mask = (plot_df_clean[pct_fb_col].notna() & plot_df_clean[pct_wp_col].notna())
    if valid_mask.sum() > 0:
        corr = plot_df_clean.loc[valid_mask, [pct_fb_col, pct_wp_col]].corr().iloc[0, 1]
    else:
        corr = np.nan
    
    # ---------- Percentage comparison figure ----------
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    fig.suptitle(f'Outflow Percentage Comparison: Facebook vs WorldPop\n({metric_name_clean})', fontsize=16, fontweight='bold')
    
    # Left: Scatter comparison
    ax1 = axes[0]
    valid_outflow = plot_df_clean[[pct_fb_col, pct_wp_col]].dropna()
    if len(valid_outflow) > 0:
        ax1.scatter(valid_outflow[pct_fb_col], valid_outflow[pct_wp_col], 
                    alpha=0.5, s=20, edgecolors='none')
        min_val = min(valid_outflow[pct_fb_col].min(), valid_outflow[pct_wp_col].min())
        max_val = max(valid_outflow[pct_fb_col].max(), valid_outflow[pct_wp_col].max())
        ax1.plot([min_val, max_val], [min_val, max_val], 'r--', alpha=0.5, label='1:1 line')
        ax1.set_xlabel('FB Outflow (% of FB baseline)')
        ax1.set_ylabel('WorldPop Outflow (% of WorldPop)')
        ax1.set_title(f'Outflow Comparison\n(correlation: {corr:.3f})')
        ax1.legend()
        ax1.grid(True, alpha=0.3)
    
    # Right: Distribution comparison
    ax2 = axes[1]
    valid_outflow_fb = plot_df_clean[pct_fb_col].dropna()
    valid_outflow_wp = plot_df_clean[pct_wp_col].dropna()
    if len(valid_outflow_fb) > 0 and len(valid_outflow_wp) > 0:
        ax2.hist(valid_outflow_fb, bins=50, alpha=0.5, label='FB', density=True)
        ax2.hist(valid_outflow_wp, bins=50, alpha=0.5, label='WorldPop', density=True)
        ax2.set_xlabel('Outflow Percentage (%)')
        ax2.set_ylabel('Density')
        ax2.set_title('Outflow Percentage Distribution')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
    
    plt.tight_layout()
    
    # Save percentage comparison figure
    fig_name = f"3_displacement_percentage_comparison_{metric['name']}.png"
    fig_path = FIGURE_DIR / fig_name
    plt.savefig(fig_path, dpi=300, bbox_inches='tight')
    # print(f"Saved displacement percentage comparison figure to: {fig_path}")
    plt.close()
    
    # ---------- Cell-count figure ----------
    total_cells = len(plot_df)
    cells_with_outflow_fb = (plot_df[metric['fb_col']].fillna(0.0) > 0).sum() if metric['fb_col'] in plot_df.columns else 0
    cells_with_outflow_worldpop = (plot_df[metric['wp_col']] > 0).sum() if metric['wp_col'] in plot_df.columns else 0
    pct_cells_outflow_fb = (cells_with_outflow_fb / total_cells) * 100 if total_cells > 0 else 0
    pct_cells_outflow_worldpop = (cells_with_outflow_worldpop / total_cells) * 100 if total_cells > 0 else 0
    
    fig2, axes2 = plt.subplots(1, 2, figsize=(12, 5))
    fig2.suptitle(f'Outflow by Cell Count: Facebook vs WorldPop\n({metric_name_clean})', fontsize=16, fontweight='bold')
    
    # Prepare data for bar charts
    categories = ['Outflow']
    fb_pcts = [pct_cells_outflow_fb]
    worldpop_pcts = [pct_cells_outflow_worldpop]
    
    # Left: Bar chart comparing percentages
    ax1 = axes2[0]
    x = np.arange(len(categories))
    width = 0.35
    bars1 = ax1.bar(x - width/2, fb_pcts, width, label='Facebook', alpha=0.8)
    bars2 = ax1.bar(x + width/2, worldpop_pcts, width, label='WorldPop', alpha=0.8)
    ax1.set_ylabel('Percentage of Cells (%)')
    ax1.set_title('Percentage of Cells with Outflow')
    ax1.set_xticks(x)
    ax1.set_xticklabels(categories)
    ax1.legend()
    ax1.grid(True, alpha=0.3, axis='y')
    # Add value labels on bars
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1f}%', ha='center', va='bottom', fontsize=10)
    
    # Right: Count comparison (absolute numbers)
    ax2 = axes2[1]
    fb_counts = [cells_with_outflow_fb]
    worldpop_counts = [cells_with_outflow_worldpop]
    bars1 = ax2.bar(x - width/2, fb_counts, width, label='Facebook', alpha=0.8)
    bars2 = ax2.bar(x + width/2, worldpop_counts, width, label='WorldPop', alpha=0.8)
    ax2.set_ylabel('Number of Cells')
    ax2.set_title('Absolute Number of Cells with Outflow')
    ax2.set_xticks(x)
    ax2.set_xticklabels(categories)
    ax2.legend()
    ax2.grid(True, alpha=0.3, axis='y')
    # Add value labels
    for bars in [bars1, bars2]:
        for bar in bars:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{int(height)}', ha='center', va='bottom', fontsize=10)
    
    plt.tight_layout()
    
    # Save cell-count figure
    fig2_name = f"3_displacement_cell_count_comparison_{metric['name']}.png"
    fig2_path = FIGURE_DIR / fig2_name
    plt.savefig(fig2_path, dpi=300, bbox_inches='tight')
    # print(f"Saved displacement cell-count comparison figure to: {fig2_path}")
    plt.close()

# Create figures for each metric
plot_df = disp_gdf.copy()
for metric in metrics_config:
    if metric['fb_col'] in disp_gdf.columns:
        create_figures_for_metric(metric, plot_df)


# ---------- Save outputs ----------
# Create output directory if it doesn't exist
OUT_DIR.mkdir(parents=True, exist_ok=True)

out_gpkg = OUT_DIR / "3_displacement_scaled_to_worldpop.gpkg"
disp_gdf.to_file(out_gpkg, layer="3_displacement_scaled", driver="GPKG")
# disp_gdf.to_file(OUT_DIR / "3displacement_scaled_to_worldpop.geojson", driver="GeoJSON")
# disp_gdf.drop(columns='geometry').to_csv(OUT_DIR / "3displacement_scaled_to_worldpop.csv", index=False)

print("Saved scaled outputs to:", out_gpkg)

# ---------- Export 3_fb_baseline_median-only GPKG to pop directory ----------
POP_OUT_DIR = Path("/Users/wenlanzhang/Downloads/PhD_UCL/Data/pop/")
POP_OUT_DIR.mkdir(parents=True, exist_ok=True)
fb_baseline_gdf = disp_gdf[["quadkey", "geometry", "3_fb_baseline_median"]].copy()
fb_baseline_gpkg = POP_OUT_DIR / "3_fb_baseline_median.gpkg"
fb_baseline_gdf.to_file(fb_baseline_gpkg, layer="3_fb_baseline_median", driver="GPKG")
print("Saved 3_fb_baseline_median to:", fb_baseline_gpkg)
# print(disp_gdf[['quadkey','worldpop','fb_baseline_median','scaling_ratio','outflow_max','estimated_outflow_pop']].head(12))