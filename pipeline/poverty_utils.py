"""
Shared utilities for allocation_residual analysis (03a, 03b).

Provides: load_and_prepare_gdf() — validates input, filters to valid quadkeys,
adds Distance and PopulationDensity for regression.
has_valid_centroids() — vectorized geometry validation (shared by 02, 03c, 03f).
"""

from pathlib import Path

import geopandas as gpd
import numpy as np
from shapely.geometry import Point


def has_valid_centroids(gdf):
    """Vectorized: return boolean mask of rows with valid, non-empty centroids."""
    centroids = gdf.geometry.centroid
    return ~centroids.is_empty


def load_and_prepare_gdf(input_path, project_crs: str, residual_col: str = "allocation_residual"):
    """
    Load harmonised gpkg from script 02, filter to valid quadkeys, add controls.

    Args:
        residual_col: Column to use as dependent variable. Default: allocation_residual.

    Returns:
        gdf_analysis: GeoDataFrame with residual_col, poverty_mean, Distance, PopulationDensity
    """
    gdf = gpd.read_file(input_path)
    if "poverty_mean" not in gdf.columns:
        raise ValueError("Input must include poverty_mean. Run script 01 with --poverty, then script 02.")
    # Backward compat: old gpkg may have allocation_log_ratio
    if "allocation_residual" not in gdf.columns and "allocation_log_ratio" in gdf.columns:
        gdf["allocation_residual"] = gdf["allocation_log_ratio"]
    if residual_col not in gdf.columns:
        raise ValueError(f"Input must include {residual_col}. Run script 02.")

    valid = gdf[residual_col].notna() & gdf["poverty_mean"].notna()
    if "poverty_n_pixels" in gdf.columns:
        valid = valid & (gdf["poverty_n_pixels"] > 0)
    gdf_analysis = gdf[valid].copy()

    # Use appropriate UTM for study area (Philippines vs Kenya)
    b = gdf_analysis.total_bounds
    centroid_lon = (b[0] + b[2]) / 2
    centroid_lat = (b[1] + b[3]) / 2
    if 118 <= centroid_lon <= 127 and 5 <= centroid_lat <= 20:
        project_crs = "EPSG:32651"  # UTM 51N for Philippines
    elif project_crs == "EPSG:32737":
        pass  # Keep UTM 37S for Kenya/Nairobi

    # Distance and population density for regression controls
    gdf_proj = gdf_analysis.to_crs(project_crs)
    # Drop invalid geometries (empty centroids cause KNN.from_dataframe to fail)
    valid_geom = has_valid_centroids(gdf_proj)
    if not valid_geom.all():
        gdf_analysis = gdf_analysis.loc[valid_geom].reset_index(drop=True)
        gdf_proj = gdf_proj.loc[valid_geom].reset_index(drop=True)
    # Use centroid mean (faster than unary_union for many polygons)
    centroids = gdf_proj.geometry.centroid
    centroid_study = Point(centroids.x.mean(), centroids.y.mean())
    gdf_analysis["Distance"] = gdf_proj.geometry.centroid.distance(centroid_study)
    gdf_analysis["area_km2"] = gdf_proj.geometry.area / 1e6
    gdf_analysis["PopulationDensity"] = gdf_analysis["worldpop_count"] / gdf_analysis["area_km2"].clip(lower=1e-6)

    return gdf_analysis
