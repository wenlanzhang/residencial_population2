#!/usr/bin/env Rscript
# 03c_plots.R — Nature-style residual maps for spatial regression (SLM, SEM)
#
# Reads: outputs/03c_spatial_regression/03c_residuals_for_plots.gpkg
# Outputs: slm_residual_map_r.png, sem_residual_map_r.png
#
# Usage: Rscript scripts/03c_plots.R

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
})

theme_nature_map <- function() {
  theme_void() +
    theme(
      plot.title = element_text(face = "bold", size = 12, hjust = 0.5),
      plot.subtitle = element_text(size = 10, colour = "grey30", hjust = 0.5),
      legend.title = element_text(face = "bold", size = 10),
      legend.text = element_text(size = 9),
      plot.margin = margin(10, 10, 10, 10)
    )
}

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
script_dir <- file.path(project_root, "pipeline")
source(file.path(script_dir, "region_config.R"), local = TRUE)

in_dir <- file.path(project_root, "outputs", "03c_spatial_regression")
out_dir <- in_dir
region_arg <- NULL
args <- commandArgs(trailingOnly = TRUE)
i <- 1
while (i <= length(args)) {
  if (args[i] == "-i" && i < length(args)) {
    in_dir <- args[i + 1]
    out_dir <- if (dir.exists(in_dir)) in_dir else dirname(in_dir)
    in_dir <- if (dir.exists(in_dir)) in_dir else dirname(in_dir)
    i <- i + 2
  } else if (args[i] == "--region" && i < length(args)) {
    region_arg <- args[i + 1]
    i <- i + 2
  } else {
    i <- i + 1
  }
}
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

gpkg_path <- file.path(in_dir, "03c_residuals_for_plots.gpkg")

if (!file.exists(gpkg_path)) {
  stop("Run 03c_spatial_regression.py first. Missing: ", gpkg_path)
}

gdf <- st_read(gpkg_path, quiet = TRUE)
map_bbox <- get_map_bbox_for_plot(region_arg, in_dir, gdf)
gdf_plot <- clip_gdf_to_bbox(gdf, map_bbox)
coord_map <- coord_from_bbox(map_bbox)

plot_residual_map <- function(gdf_use, gdf_full, col, title, subtitle, fname) {
  v <- gdf_use[[col]]
  v <- v[!is.na(v)]
  if (length(v) == 0) {
    message("No valid values for ", col)
    return(invisible(NULL))
  }
  lim <- max(abs(min(v, na.rm = TRUE)), abs(max(v, na.rm = TRUE)), 1e-6)
  p <- ggplot(gdf_use) +
    geom_sf(aes(fill = .data[[col]]), colour = "white", linewidth = 0.15) +
    scale_fill_gradient2(
      low = "#2166AC", mid = "white", high = "#B2182B",
      midpoint = 0, limits = c(-lim, lim), name = "Residual"
    ) +
    labs(title = title, subtitle = subtitle) +
    theme_nature_map()
  p <- p + coord_map
  fname_r <- sub("\\.png$", "_r.png", fname)
  ggsave(file.path(out_dir, fname_r), p, width = 8, height = 8, dpi = 300, bg = "white")
  message("Saved: ", file.path(out_dir, fname_r))
}

plot_residual_map(gdf_plot, gdf, "slm_residual",
  title = "SLM residuals",
  subtitle = "Spatial Lag Model",
  "slm_residual_map.png"
)

plot_residual_map(gdf_plot, gdf, "sem_residual",
  title = "SEM residuals",
  subtitle = "Spatial Error Model",
  "sem_residual_map.png"
)
