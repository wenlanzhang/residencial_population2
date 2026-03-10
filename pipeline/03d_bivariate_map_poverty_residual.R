#!/usr/bin/env Rscript
# 03d — Bivariate map: Poverty × Allocation residual (Digital invisibility hotspots)
#
# Poverty (MPI): high = more poverty
# Allocation residual = log(meta_share / worldpop_share): negative = Meta under-allocates
# Key quadrant: High poverty (3) + Negative residual (1) = 3-1 = Digital invisibility
#
# Reads directly from script 02 output. No Python step needed.
# Usage: Rscript pipeline/03d_bivariate_map_poverty_residual.R
#        Rscript pipeline/03d_bivariate_map_poverty_residual.R -i outputs/02/harmonised_with_residual.gpkg
#        Rscript pipeline/03d_bivariate_map_poverty_residual.R -i outputs/KEN/02/... -o outputs/KEN/03d_bivariate

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
})

# Z-score classify for 3×3 bivariate: 1=low, 2=medium, 3=high
classify_z <- function(z, t = 0.5) {
  out <- rep(2L, length(z))
  out[z < -t] <- 1L
  out[z > t] <- 3L
  out
}

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
script_dir <- file.path(project_root, "pipeline")
source(file.path(script_dir, "region_config.R"), local = TRUE)

input_path <- file.path(project_root, "outputs", "02", "harmonised_with_residual.gpkg")
out_dir <- file.path(project_root, "outputs", "03d_bivariate")
output_path <- file.path(out_dir, "03d_bivariate_poverty_residual.png")
output_path_basemap <- file.path(out_dir, "03d_bivariate_poverty_residual_basemap.png")
region_arg <- NULL

# Residual metric: allocation_residual (canonical)
residual_var <- "allocation_residual"
args <- commandArgs(trailingOnly = TRUE)
i <- 1
while (i <= length(args)) {
  if (args[i] == "-i" && i < length(args)) {
    input_path <- args[i + 1]
    out_dir <- file.path(dirname(dirname(input_path)), "03d_bivariate")
    i <- i + 2
  } else if (args[i] == "-o" && i < length(args)) {
    out_dir <- args[i + 1]
    i <- i + 2
  } else if (args[i] == "--region" && i < length(args)) {
    region_arg <- args[i + 1]
    i <- i + 2
  } else if (args[i] == "--residual-var" && i < length(args)) {
    residual_var <- args[i + 1]
    i <- i + 2
  } else {
    i <- i + 1
  }
}
output_path <- file.path(out_dir, "03d_bivariate_poverty_residual.png")
output_path_basemap <- file.path(out_dir, "03d_bivariate_poverty_residual_basemap.png")

if (!file.exists(input_path)) {
  stop("Run script 02 first. Missing: ", input_path)
}

gdf <- st_read(input_path, quiet = TRUE)
map_bbox <- get_map_bbox_for_plot(region_arg, input_path, gdf)
coord_map <- coord_from_bbox(map_bbox)
add_coord <- function(p, g) p + coord_map
if (!"poverty_mean" %in% names(gdf)) {
  stop("Input must include poverty_mean. Run script 01 with --poverty, then script 02.")
}
# Fallback for old gpkg with allocation_log_ratio
if (!residual_var %in% names(gdf)) {
  residual_var <- if ("allocation_residual" %in% names(gdf)) "allocation_residual"
  else if ("allocation_log_ratio" %in% names(gdf)) "allocation_log_ratio"
  else "residual"
}
if (!residual_var %in% names(gdf)) {
  stop("Input must include allocation_residual. Run script 02.")
}

# Legend labels for residual metric
residual_labels <- c(
  allocation_residual = "Allocation residual: log(Meta) − log(WorldPop)",
  allocation_log_ratio = "Allocation residual: log(Meta) − log(WorldPop)",
  residual = "Residual: log(Meta) − log(WorldPop)"
)
residual_legend <- residual_labels[residual_var]

# Filter to valid quadkeys (calculations use full gdf)
gdf <- gdf %>%
  filter(!is.na(.data[[residual_var]]), !is.na(poverty_mean))
if ("poverty_n_pixels" %in% names(gdf)) {
  gdf <- gdf %>% filter(poverty_n_pixels > 0)
}

# Plot data: clipped to map_bbox when available
gdf_plot <- clip_gdf_to_bbox(gdf, map_bbox)
# Z-scores for bivariate: compute from full gdf for consistency, then subset for plot
gdf <- gdf %>%
  mutate(
    poverty_z = (poverty_mean - mean(poverty_mean, na.rm = TRUE)) / sd(poverty_mean, na.rm = TRUE),
    residual_z = (.data[[residual_var]] - mean(.data[[residual_var]], na.rm = TRUE)) / sd(.data[[residual_var]], na.rm = TRUE),
    poverty_z = ifelse(is.na(poverty_z), 0, poverty_z),
    residual_z = ifelse(is.na(residual_z), 0, residual_z),
    pov_class = classify_z(poverty_z),
    res_class = classify_z(residual_z),
    bi_class = paste0(pov_class, "-", res_class)
  )

message("Valid quadkeys: ", nrow(gdf), "; residual metric: ", residual_var)

# Ensure plot data has bi_class (z-scores from zoomed data for clearer legend)
gdf_plot <- gdf_plot %>%
  mutate(
    poverty_z = (poverty_mean - mean(poverty_mean, na.rm = TRUE)) / sd(poverty_mean, na.rm = TRUE),
    residual_z = (.data[[residual_var]] - mean(.data[[residual_var]], na.rm = TRUE)) / sd(.data[[residual_var]], na.rm = TRUE),
    poverty_z = ifelse(is.na(poverty_z), 0, poverty_z),
    residual_z = ifelse(is.na(residual_z), 0, residual_z),
    pov_class = classify_z(poverty_z),
    res_class = classify_z(residual_z),
    bi_class = paste0(pov_class, "-", res_class)
  )

bivariate_palette <- c(
  "1-1" = "#e8e8e8", "2-1" = "#e4acac", "3-1" = "#c85a5a",
  "1-2" = "#b8d6be", "2-2" = "#ad9ea5", "3-2" = "#985356",
  "1-3" = "#64acbe", "2-3" = "#627f8c", "3-3" = "#574249"
)
gdf_plot$bi_class <- factor(gdf_plot$bi_class, levels = names(bivariate_palette))

use_biscale <- requireNamespace("biscale", quietly = TRUE)
use_cowplot <- requireNamespace("cowplot", quietly = TRUE)
use_ggspatial <- requireNamespace("ggspatial", quietly = TRUE)
use_maptiles <- requireNamespace("maptiles", quietly = TRUE)

# subtitle_str <- paste0("3-1 = Digital invisibility hotspot")

# Base map (no basemap) — zoomed when Philippines
if (use_biscale && use_cowplot) {
  map <- ggplot(gdf_plot) +
    geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.2, show.legend = FALSE) +
    biscale::bi_scale_fill(pal = "DkBlue", dim = 3) +
    biscale::bi_theme() +
    labs(
      title = "Bivariate: Poverty × Allocation Residual",
      # subtitle = subtitle_str
    )
  legend <- biscale::bi_legend(
    pal = "DkBlue", dim = 3,
    xlab = "Higher Poverty ", ylab = "Higher allocation (over-alloc)",
    size = 8
  )
  map <- add_coord(map, gdf)
  p <- cowplot::ggdraw() +
    cowplot::draw_plot(map, 0, 0, 1, 1) +
    cowplot::draw_plot(legend, 0.02, 0.02, 0.22, 0.22)
} else {
  p <- ggplot(gdf_plot) +
    geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.2) +
    scale_fill_manual(
      values = bivariate_palette,
      na.value = "grey90",
      drop = FALSE,
      name = paste0("Poverty | ", residual_legend)
    ) +
    theme_void() +
    theme(
      legend.position = c(0.02, 0.02),
      legend.justification = c(0, 0),
      plot.title = element_text(hjust = 0.5, face = "bold")
    ) +
    labs(title = "Bivariate: Poverty × Allocation residual")
  p <- add_coord(p, gdf)
}

dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
ggsave(output_path, p, width = 10, height = 8, dpi = 150, bg = "white", create.dir = TRUE)
message("Saved: ", output_path)

# With Sentinel basemap (use gdf_plot for tile extent when Philippines)
basemap_layer <- NULL
basemap_zoom <- if (!is.null(map_bbox)) 10 else 12
if (use_maptiles && requireNamespace("terra", quietly = TRUE)) {
  tryCatch({
    s2_provider <- maptiles::create_provider(
      name = "Sentinel2-EOX",
      url = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/webmercator/{z}/{x}/{y}.jpeg",
      citation = "Sentinel-2 cloudless by EOX"
    )
    tiles <- maptiles::get_tiles(gdf_plot, provider = s2_provider, zoom = basemap_zoom, crop = TRUE, cachedir = tempdir())
    basemap_layer <- ggspatial::annotation_spatial(tiles, alpha = 0.9)
  }, error = function(e) {
    tryCatch({
      tiles <- maptiles::get_tiles(gdf_plot, provider = "Esri.WorldImagery", zoom = basemap_zoom, crop = TRUE, cachedir = tempdir())
      basemap_layer <<- ggspatial::annotation_spatial(tiles, alpha = 0.9)
    }, error = function(e2) NULL)
  })
}
if (is.null(basemap_layer) && use_ggspatial) {
  basemap_layer <- ggspatial::annotation_map_tile(type = "osm", zoom = basemap_zoom, alpha = 0.8, cachedir = tempdir())
}

if (use_ggspatial && !is.null(basemap_layer)) {
  tryCatch({
  if (use_biscale && use_cowplot) {
    map_bm <- ggplot(gdf_plot) +
      basemap_layer +
      geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.3, alpha = 0.5, show.legend = FALSE) +
      biscale::bi_scale_fill(pal = "DkBlue", dim = 3) +
      biscale::bi_theme() +
      labs(title = "Bivariate: Poverty × Residual (Sentinel basemap)")
    map_bm <- add_coord(map_bm, gdf)
    legend_bm <- biscale::bi_legend(pal = "DkBlue", dim = 3, xlab = "Higher Poverty ", ylab = "Higher allocation ", size = 8)
    p_bm <- cowplot::ggdraw() +
      cowplot::draw_plot(map_bm, 0, 0, 1, 1) +
      cowplot::draw_plot(legend_bm, 0.02, 0.02, 0.22, 0.22)
  } else {
    map_bm <- ggplot(gdf_plot) +
      basemap_layer +
      geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.3, alpha = 0.5) +
      scale_fill_manual(values = bivariate_palette, na.value = "grey90", drop = FALSE, name = paste0("Poverty | ", residual_legend)) +
      theme_void() +
      theme(legend.position = c(0.02, 0.02), legend.justification = c(0, 0)) +
      labs(title = "Bivariate: Poverty × Allocation residual (basemap)")
    p_bm <- add_coord(map_bm, gdf)
  }
  ggsave(output_path_basemap, p_bm, width = 10, height = 8, dpi = 150, bg = "white", create.dir = TRUE)
  message("Saved: ", output_path_basemap)
  }, error = function(e) {
    message("Basemap save failed: ", conditionMessage(e))
  })
}
