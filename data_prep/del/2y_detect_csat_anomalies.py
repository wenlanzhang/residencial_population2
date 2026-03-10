#!/usr/bin/env python3

"""
================================================================================
PROJECT: PhD UCL - Waste & Flood Impact Evaluation
OUTPUT DIRECTORY: /Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/2/

PRIMARY OUTPUTS:
1. agg_REFERENCEHOUR_... .gpkg        : Final spatial output
   - 'displaced_excess_max'           : Displacement count exceeding -3.5 Z-score.
   - 'outflow_max'                    : Maximum raw people who left the cell.
   
2. rows_with_displacement_... .csv    : Processed data for the specific Ref Hour.
3. anomalies_csat_outflow.csv         : Log of all statistically significant drops.
4. CSAT_thresholds_... .csv           : Historical Baseline (Median/MAD) stats.
================================================================================
"""

import numpy as np
import pandas as pd
import geopandas as gpd
from pathlib import Path

# ---------- PARAMETERS ----------
FB_WIDE_PATH = '/Users/wenlanzhang/Downloads/PhD_UCL/Data/Waste_flood/Meta/FB_32737_wide.gpkg'
FB_WIDE_LAYER = 'population_change'
OUT_DIR = Path('/Users/wenlanzhang/PycharmProjects/Waste_Flood_out/Data/2/')
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Analysis choices
REFERENCE_HOUR = 0                    # set to 0, 8, or 16 (primary analysis uses one hour)
CHANGE_METRIC = 'modified_zscore'     # 'relative_percent' | 'absolute_diff' | 'log_change' | 'modified_zscore'

# Conditional parameters based on CHANGE_METRIC
if CHANGE_METRIC in ['relative_percent', 'absolute_diff', 'log_change']:
    OUTFLOW_PCT = 10                  # lower-tail percentile for outflow (default: 10th percentile)
    MODIFIED_ZSCORE_THRESHOLD = None  # not used for percentile-based metrics
elif CHANGE_METRIC == 'modified_zscore':
    OUTFLOW_PCT = None                # not used for modified_zscore
    MODIFIED_ZSCORE_THRESHOLD = -3.5   # threshold for modified_zscore outflow detection (default: -3.5)
else:
    OUTFLOW_PCT = None
    MODIFIED_ZSCORE_THRESHOLD = None

MIN_BASELINE_SAMPLES = 3              # mark low_confidence if fewer samples used to build threshold
EXCLUDE_PREFIXES = [
    '20240430_1600','20240501_0000','20240502_0800',
    '20240502_1600','20240503_0000'
]
BASELINE_SUFFIX = '_n_baseline'
CRISIS_SUFFIX = '_n_crisis'

# ---------- Helper functions ----------
def extract_timestamp_prefix(col):
    try:
        return str(col).split('_n_')[0]
    except Exception:
        return None

def parse_prefix_to_dt(prefix):
    try:
        return pd.to_datetime(prefix, format='%Y%m%d_%H%M')
    except Exception:
        return pd.NaT

def relative_percent_change(baseline, crisis):
    with np.errstate(divide='ignore', invalid='ignore'):
        out = np.where(baseline != 0, (crisis - baseline) / baseline, np.nan)
    return out

def absolute_diff(baseline, crisis):
    return crisis - baseline

def log_change(baseline, crisis):
    return np.log1p(crisis) - np.log1p(baseline)

def compute_modified_zscore(change_values, median_val, mad_val):
    """
    Compute Modified Z-Score for change values.
    Modified Z-Score = 0.6745 * (x - median) / MAD
    Where MAD is the Median Absolute Deviation.
    """
    with np.errstate(divide='ignore', invalid='ignore'):
        out = np.where(mad_val != 0, 0.6745 * (change_values - median_val) / mad_val, np.nan)
    return out

# ---------- wide -> long paired ----------
def wide_to_long_paired(fb_wide, baseline_suffix='_n_baseline', crisis_suffix='_n_crisis', exclude_prefixes=None):
    cols = fb_wide.columns.tolist()
    baseline_cols = [c for c in cols if str(c).endswith(baseline_suffix)]
    crisis_cols = [c for c in cols if str(c).endswith(crisis_suffix)]
    baseline_map = {extract_timestamp_prefix(c): c for c in baseline_cols}
    crisis_map = {extract_timestamp_prefix(c): c for c in crisis_cols}
    matching_prefixes = sorted(set(baseline_map.keys()) & set(crisis_map.keys()))
    records = []
    exclude_set = set(exclude_prefixes) if exclude_prefixes else set()
    for prefix in matching_prefixes:
        if prefix in exclude_set:
            continue
        bcol = baseline_map[prefix]
        ccol = crisis_map[prefix]
        dt = parse_prefix_to_dt(prefix)
        hour = int(dt.hour) if pd.notna(dt) else None
        bl = pd.to_numeric(fb_wide[bcol], errors='coerce')
        cr = pd.to_numeric(fb_wide[ccol], errors='coerce')
        tmp = pd.DataFrame({
            'quadkey': fb_wide['quadkey'],
            'ts_prefix': prefix,
            'dt': dt,
            'hour': hour,
            'baseline': bl,
            'crisis': cr
        })
        records.append(tmp)
    if len(records) == 0:
        return pd.DataFrame(columns=['quadkey','ts_prefix','dt','hour','baseline','crisis'])
    long_df = pd.concat(records, ignore_index=True)
    return long_df

# ---------- per-cell-only CSAT (outflow only) ----------
def compute_csat_outflow_per_cell_only(
    fb_wide,
    change_metric='relative_percent',
    outflow_pct=None,
    min_baseline_samples=3,
    exclude_prefixes=None,
    baseline_suffix='_n_baseline',
    crisis_suffix='_n_crisis',
    modified_zscore_threshold=None
):
    """
    Compute per-quadkey × hour outflow threshold (lower-tail percentile or Modified Z-Score threshold).
    Returns dict with 'thresholds' and 'baseline_stats'.
    """
    # Validate parameters based on change_metric
    if change_metric == 'modified_zscore':
        if modified_zscore_threshold is None:
            modified_zscore_threshold = -3.5  # default
        if outflow_pct is not None:
            print("Warning: outflow_pct is not used for modified_zscore metric, ignoring it.")
    else:
        if outflow_pct is None:
            outflow_pct = 10  # default
        if modified_zscore_threshold is not None:
            print("Warning: modified_zscore_threshold is not used for percentile-based metrics, ignoring it.")
    
    # Build historical sample excluding crisis timestamps
    paired = wide_to_long_paired(fb_wide, baseline_suffix, crisis_suffix, exclude_prefixes=exclude_prefixes)
    if paired.empty:
        raise ValueError("No matching baseline/crisis pairs found in fb_wide (after exclusions).")

    if change_metric == 'relative_percent':
        compute_change = lambda b, c: relative_percent_change(b, c)
    elif change_metric == 'absolute_diff':
        compute_change = lambda b, c: absolute_diff(b, c)
    elif change_metric == 'log_change':
        compute_change = lambda b, c: log_change(b, c)
    elif change_metric == 'modified_zscore':
        # For Modified Z-Score, we first compute absolute_diff, then standardize
        compute_change = lambda b, c: absolute_diff(b, c)
    else:
        raise ValueError("change_metric must be 'relative_percent'|'absolute_diff'|'log_change'|'modified_zscore'")

    paired['change'] = compute_change(paired['baseline'].values, paired['crisis'].values)
    paired_valid = paired.dropna(subset=['baseline', 'crisis', 'change']).copy()

    rows = []
    baseline_stats = []
    grouped = paired_valid.groupby(['quadkey', 'hour'], sort=False)
    for (qk, hr), grp in grouped:
        ch = grp['change'].values.astype(float)
        n_pairs = int(np.sum(~np.isnan(ch)))
        
        if change_metric == 'modified_zscore':
            # For Modified Z-Score: compute median and MAD from baseline changes
            if n_pairs >= min_baseline_samples:
                median_ch = np.nanmedian(ch)
                mad_ch = np.nanmedian(np.abs(ch - median_ch))
                # Modified Z-Score threshold is fixed at -3.5
                lower = modified_zscore_threshold
                low_confidence = False
                # Store median and MAD for later use
                median_val = median_ch
                mad_val = mad_ch
            else:
                lower = np.nan
                low_confidence = True
                median_val = np.nan
                mad_val = np.nan
        else:
            # For other metrics: use percentile-based threshold
            if n_pairs >= min_baseline_samples:
                lower = np.nanpercentile(ch, outflow_pct)
                low_confidence = False
            else:
                lower = np.nan
                low_confidence = True
            median_val = np.nanmedian(ch)
            mad_val = np.nanmedian(np.abs(ch - median_val))

        rows.append({
            'quadkey': qk,
            'hour': hr,
            '2_threshold_lower': lower,
            '2_n_pairs': n_pairs,
            '2_low_confidence': low_confidence
        })
        baseline_stats.append({
            'quadkey': qk,
            'hour': hr,
            '2_baseline_mean': np.nanmean(grp['baseline'].values),
            '2_baseline_median': np.nanmedian(grp['baseline'].values),
            '2_baseline_std': np.nanstd(grp['baseline'].values),
            '2_n_baseline': n_pairs,
            '2_change_median': median_val,
            '2_change_mad': mad_val
        })

    thresholds_df = pd.DataFrame(rows)
    baseline_stats_df = pd.DataFrame(baseline_stats)
    return {
        'thresholds': thresholds_df,
        'baseline_stats': baseline_stats_df,
        'change_metric': change_metric,
        'outflow_pct': outflow_pct,
        'modified_zscore_threshold': modified_zscore_threshold if change_metric == 'modified_zscore' else None
    }

# ---------- detect outflow anomalies by hour per cell (use ALL rows: no exclusions) ----------
def detect_outflow_anomalies_by_hour_per_cell_only(fb_wide, csat_results,
                                                   baseline_suffix='_n_baseline',
                                                   crisis_suffix='_n_crisis',
                                                   enforce_confidence=False):
    # IMPORTANT: use *all* rows for anomaly detection (including crisis timestamps).
    paired = wide_to_long_paired(fb_wide, baseline_suffix, crisis_suffix, exclude_prefixes=None)
    if paired.empty:
        raise ValueError("No matching baseline/crisis pairs found in fb_wide.")
    cm = csat_results['change_metric']
    if cm == 'relative_percent':
        paired['2_change'] = relative_percent_change(paired['baseline'].values, paired['crisis'].values)
    elif cm == 'absolute_diff':
        paired['2_change'] = absolute_diff(paired['baseline'].values, paired['crisis'].values)
    elif cm == 'log_change':
        paired['2_change'] = log_change(paired['baseline'].values, paired['crisis'].values)
    elif cm == 'modified_zscore':
        # For Modified Z-Score, first compute absolute_diff
        paired['change_raw'] = absolute_diff(paired['baseline'].values, paired['crisis'].values)
    else:
        raise ValueError("Unknown change metric in csat_results")

    thresholds = csat_results['thresholds']
    if '2_low_confidence' not in thresholds.columns:
        thresholds = thresholds.copy()
        thresholds['2_low_confidence'] = False

    # For Modified Z-Score, merge baseline_stats to get median and MAD
    if cm == 'modified_zscore':
        baseline_stats = csat_results['baseline_stats']
        merged = paired.merge(thresholds, how='left', on=['quadkey', 'hour'])
        merged = merged.merge(baseline_stats[['quadkey', 'hour', '2_change_median', '2_change_mad']], 
                             how='left', on=['quadkey', 'hour'])
        # Compute Modified Z-Score for each row
        merged['2_change'] = compute_modified_zscore(
            merged['change_raw'].values,
            merged['2_change_median'].values,
            merged['2_change_mad'].values
        )
    else:
        merged = paired.merge(thresholds, how='left', on=['quadkey', 'hour'])
        # 2_change should already exist from paired dataframe
        if '2_change' not in merged.columns:
            # If change wasn't computed, create empty 2_change column
            merged['2_change'] = np.nan

    # Fix FutureWarning: use mask assignment instead of fillna to avoid downcasting warning
    if '2_low_confidence' in merged.columns:
        # Use mask to fill NaN values without triggering downcasting warning
        mask = merged['2_low_confidence'].isna()
        merged.loc[mask, '2_low_confidence'] = True
        merged['2_low_confidence'] = merged['2_low_confidence'].astype(bool)
    else:
        merged['2_low_confidence'] = True

    # only outflow: change significantly below threshold_lower
    def flag_row(row):
        ch = row.get('2_change', np.nan)
        low = row.get('2_threshold_lower', np.nan)
        if pd.isna(ch) or pd.isna(low):
            return pd.Series({'2_is_anomaly': False, '2_anomaly_direction': None})
        if enforce_confidence and bool(row.get('2_low_confidence', False)):
            return pd.Series({'2_is_anomaly': False, '2_anomaly_direction': None})
        # Outflow: change < lower threshold
        if ch < low:
            return pd.Series({'2_is_anomaly': True, '2_anomaly_direction': 'outflow'})
        return pd.Series({'2_is_anomaly': False, '2_anomaly_direction': None})

    flags = merged.apply(flag_row, axis=1)
    merged = pd.concat([merged, flags], axis=1)
    anomalies_df = merged[merged['2_is_anomaly']].copy()
    return merged, anomalies_df

# ---------- displacement calculation (outflow only; temporal filters removed) ----------
def compute_displacement_per_row_outflow(merged_long, change_metric='relative_percent'):
    df = merged_long.copy()
    # raw signed displacement: positive => crisis > baseline (inflow), negative => crisis < baseline (outflow)
    df['2_D_raw'] = df['crisis'] - df['baseline']

    # For outflow we only care about negative D_raw (people left)
    if change_metric == 'absolute_diff':
        df['2_threshold_counts_outflow'] = -df['2_threshold_lower']  # make positive
        df['2_D_excess'] = np.where(
            df['2_D_raw'] < 0,
            ( -df['2_D_raw'] - df['2_threshold_counts_outflow'] ).clip(lower=0),
            0.0
        )
    elif change_metric == 'relative_percent':
        df['2_threshold_counts_outflow'] = np.where(
            (df['baseline'].notna()),
            (-df['2_threshold_lower'].astype(float) * df['baseline']).fillna(0.0),
            0.0
        )
        df['2_threshold_counts_outflow'] = df['2_threshold_counts_outflow'].clip(lower=0.0)
        df['2_D_excess'] = np.where(
            df['2_D_raw'] < 0,
            ( -df['2_D_raw'] - df['2_threshold_counts_outflow'] ).clip(lower=0),
            0.0
        )
    elif change_metric == 'log_change':
        t_out = df['2_threshold_lower']
        crisis_threshold_outflow = np.expm1(np.log1p(df['baseline']) + t_out)
        df['2_D_excess'] = np.where(
            df['2_D_raw'] < 0,
            (crisis_threshold_outflow - df['crisis']).clip(lower=0),
            0.0
        )
        df['2_threshold_counts_outflow'] = crisis_threshold_outflow
    elif change_metric == 'modified_zscore':
        # Convert Modified Z-Score threshold back to raw change value
        # change_value = median + (z_score / 0.6745) * MAD
        # threshold_lower is -3.5 (z-score), convert to raw change threshold
        z_threshold = df['2_threshold_lower'].astype(float)  # -3.5
        # Get change_median and change_mad if they exist, otherwise use NaN
        if '2_change_median' in df.columns and '2_change_mad' in df.columns:
            median_ch = df['2_change_median'].fillna(np.nan)
            mad_ch = df['2_change_mad'].fillna(np.nan)
        else:
            # Fallback: use NaN if columns don't exist
            median_ch = pd.Series([np.nan] * len(df), index=df.index)
            mad_ch = pd.Series([np.nan] * len(df), index=df.index)
        with np.errstate(divide='ignore', invalid='ignore'):
            threshold_change_raw = np.where(
                mad_ch != 0,
                median_ch + (z_threshold / 0.6745) * mad_ch,
                np.nan
            )
        # threshold_change_raw is the raw change value threshold (negative for outflow)
        # Convert to positive threshold counts
        df['2_threshold_counts_outflow'] = np.where(
            threshold_change_raw < 0,
            -threshold_change_raw,
            0.0
        )
        df['2_D_excess'] = np.where(
            df['2_D_raw'] < 0,
            ( -df['2_D_raw'] - df['2_threshold_counts_outflow'] ).clip(lower=0),
            0.0
        )
    else:
        raise ValueError("unknown change_metric")

    # No temporal outlier flags in this simplified pipeline.
    # USE ROW: CSAT anomaly (outflow) only
    df['2_use_row'] = (df['2_is_anomaly'] == True)

    # Signed contribution for outflow (only from used rows)
    df['2_D_out_used'] = np.where(df['2_use_row'], np.maximum(-df['2_D_raw'], 0.0), 0.0)  # positive counts leaving

    # Also D_raw_used and D_excess_used for reference
    df['2_D_raw_used'] = np.where(df['2_use_row'], df['2_D_raw'], 0.0)
    df['2_D_excess_used'] = np.where(df['2_use_row'], df['2_D_excess'], 0.0)
    return df

# ---------- pipeline orchestration (outflow only, no temporal outlier filtering) ----------
def run_pipeline_outflow_no_temporal():
    print("Loading fb_wide...")
    fb_wide = gpd.read_file(FB_WIDE_PATH, layer=FB_WIDE_LAYER)
    if 'quadkey' not in fb_wide.columns:
        raise ValueError("fb_wide must contain a 'quadkey' column")

    print("Computing per-cell outflow CSAT thresholds (per quadkey-hour, excluding crisis prefixes)...")
    # Build kwargs conditionally based on CHANGE_METRIC
    csat_kwargs = {
        'fb_wide': fb_wide,
        'change_metric': CHANGE_METRIC,
        'min_baseline_samples': MIN_BASELINE_SAMPLES,
        'exclude_prefixes': EXCLUDE_PREFIXES,
        'baseline_suffix': BASELINE_SUFFIX,
        'crisis_suffix': CRISIS_SUFFIX
    }
    # Only add parameters that are relevant to the chosen metric
    if CHANGE_METRIC in ['relative_percent', 'absolute_diff', 'log_change']:
        csat_kwargs['outflow_pct'] = OUTFLOW_PCT
    elif CHANGE_METRIC == 'modified_zscore':
        csat_kwargs['modified_zscore_threshold'] = MODIFIED_ZSCORE_THRESHOLD
    
    csat = compute_csat_outflow_per_cell_only(**csat_kwargs)
    thresholds_df = csat['thresholds']
    thresholds_df.to_csv(OUT_DIR / '2_CSAT_thresholds_per_cell_hour_outflow.csv', index=False)

    print("Detecting CSAT outflow anomalies (using all timestamps)...")
    merged_long, anomalies_df = detect_outflow_anomalies_by_hour_per_cell_only(
        fb_wide=fb_wide,
        csat_results=csat,
        baseline_suffix=BASELINE_SUFFIX,
        crisis_suffix=CRISIS_SUFFIX,
        enforce_confidence=False
    )
    merged_long.to_csv(OUT_DIR / '2_merged_long_with_csat_outflow.csv', index=False)
    anomalies_df.to_csv(OUT_DIR / '2_anomalies_csat_outflow.csv', index=False)
    print(f"Total outflow anomalies detected: {len(anomalies_df)}")

    # Restrict to reference hour for primary analysis
    ref_df = merged_long[merged_long['hour'] == REFERENCE_HOUR].copy()
    print(f"Rows at reference hour ({REFERENCE_HOUR}): {len(ref_df)}")

    # compute displacement per row (outflow only)
    df_rows = compute_displacement_per_row_outflow(ref_df, change_metric=CHANGE_METRIC)
    df_rows.to_csv(OUT_DIR / f'2_rows_with_displacement_outflow_{REFERENCE_HOUR}.csv', index=False)

    # Aggregation per quadkey: aggregate from ALL rows (not just anomalies) to keep full grid
    # For cells without anomalies, 2_D_out_used and 2_D_excess_used will be 0, which is correct
    print(f"Aggregating from all {len(df_rows)} rows (full grid, not filtered)...")
    
    # Get all unique quadkeys from the full grid (fb_wide) to ensure we include all cells
    all_quadkeys = pd.DataFrame({'quadkey': fb_wide['quadkey'].unique()})
    
    # Aggregate from all df_rows (includes both anomaly and non-anomaly rows)
    agg = (
        df_rows
        .groupby('quadkey', sort=False)
        .agg(
            outflow_max=('2_D_out_used','max'),
            displaced_excess_max=('2_D_excess_used','max'),
            # displaced_raw_max=('2_D_raw_used','max'),
            n_crisis_rows=('2_use_row','sum'),
            n_obs=('2_D_raw','count'),
            n_low_confidence=('2_low_confidence','sum'),
            change_mean=('2_change','mean'),
            change_std=('2_change','std'),
            change_min=('2_change','min'),
            change_max=('2_change','max'),
            # change_median=('2_change','median')
        )
        .reset_index()
    )
    
    # Merge with all_quadkeys to ensure we have the full grid
    # This adds rows for quadkeys that had no data at reference hour
    agg = all_quadkeys.merge(agg, on='quadkey', how='left')
    
    # Fill missing values for quadkeys with no data
    agg['outflow_max'] = agg['outflow_max'].fillna(0.0)
    agg['displaced_excess_max'] = agg['displaced_excess_max'].fillna(0.0)
    agg['n_crisis_rows'] = agg['n_crisis_rows'].fillna(0).astype(int)
    agg['n_obs'] = agg['n_obs'].fillna(0).astype(int)
    agg['n_low_confidence'] = agg['n_low_confidence'].fillna(0).astype(int)
    
    # Rename columns to add 2_ prefix
    agg = agg.rename(columns={
        'outflow_max': '2_outflow_max',
        'displaced_excess_max': '2_displaced_excess_max',
        'n_crisis_rows': '2_n_crisis_rows',
        'n_obs': '2_n_obs',
        'n_low_confidence': '2_n_low_confidence',
        'change_mean': '2_change_mean',
        'change_std': '2_change_std',
        'change_min': '2_change_min',
        'change_max': '2_change_max'
    })

    agg['2_change_range'] = agg['2_change_max'] - agg['2_change_min']

    # IQR per quadkey (robust spread) - compute from all rows, not just anomalies
    def calc_iqr(group):
        return np.nanpercentile(group, 75) - np.nanpercentile(group, 25)

    iqr_by_quadkey = (
        df_rows
        .groupby('quadkey', sort=False)['2_change']
        .apply(calc_iqr)
        .reset_index(name='2_change_iqr')
    )
    agg = agg.merge(iqr_by_quadkey, on='quadkey', how='left')

    with np.errstate(divide='ignore', invalid='ignore'):
        agg['2_change_cv'] = np.where(
            (agg['2_change_mean'] != 0) & (~np.isnan(agg['2_change_mean'])),
            agg['2_change_std'] / np.abs(agg['2_change_mean']),
            np.nan
        )

    # Add geometry from fb_wide if available
    if 'geometry' in fb_wide.columns:
        geom_map = fb_wide[['quadkey','geometry']].drop_duplicates(subset='quadkey').set_index('quadkey')['geometry']
        agg['geometry'] = agg['quadkey'].map(geom_map)
        agg_gdf = gpd.GeoDataFrame(agg, geometry='geometry', crs=fb_wide.crs)
        gpkg_path = OUT_DIR / f'2_agg_displacement_by_quadkey_outflow.gpkg'
        agg_gdf.to_file(gpkg_path, layer=f'2_displacement_outflow', driver='GPKG')
        print(f"Saved GeoPackage: {gpkg_path}")
        print(f"  Total quadkeys in output: {len(agg_gdf)} (full grid)")
    else:
        agg.to_csv(OUT_DIR / f'2_agg_displacement_by_quadkey_outflow.csv', index=False)
        print(f"Saved CSV: 2_agg_displacement_by_quadkey_outflow.csv")
        print(f"  Total quadkeys in output: {len(agg)} (full grid)")

    # Diagnostics: flag counts per quadkey (simplified)
    agg_dict = {
        '2_n_points': ('2_D_raw', 'size'),
        '2_n_crisis_rows': ('2_use_row', 'sum')
    }
    if '2_low_confidence' in df_rows.columns:
        agg_dict['2_n_low_confidence'] = ('2_low_confidence', 'sum')
    else:
        agg_dict['2_n_low_confidence'] = ('2_D_raw', lambda x: 0)

    flag_counts = df_rows.groupby('quadkey', sort=False).agg(**agg_dict).reset_index()
    # flag_counts.to_csv(OUT_DIR / '2_flag_counts_refhour_outflow.csv', index=False)
    # print("Saved diagnostics: 2_flag_counts_refhour_outflow.csv")

    # Summary cleaned per quadkey-hour (since we removed temporal cleaning, this is just grouped stats)
    summary_cleaned = (
        df_rows.groupby(['quadkey','hour'], sort=False)
        .agg(change_median_clean=('2_change','median'),
             change_mean_clean=('2_change','mean'),
             n_obs_clean=('2_change','count'))
        .reset_index()
    )
    # Rename columns
    summary_cleaned = summary_cleaned.rename(columns={
        'change_median_clean': '2_change_median_clean',
        'change_mean_clean': '2_change_mean_clean',
        'n_obs_clean': '2_n_obs_clean'
    })
    # summary_cleaned.to_csv(OUT_DIR / '2_summary_cleaned_refhour_outflow.csv', index=False)
    # print("Saved summary_cleaned_refhour_outflow.csv")

    print("Pipeline finished. Outputs in:", OUT_DIR)

if __name__ == '__main__':
    run_pipeline_outflow_no_temporal()
