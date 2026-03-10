#!/usr/bin/env Rscript
# 01 — Descriptive figures: raw signal maps + share maps (saved separately)
#
# Figure 1a: Meta | WorldPop | Poverty (3-panel, raw counts — descriptive only)
# Figure 1b: Meta | WorldPop | Poverty (3-panel, log1p — descriptive only)
# Figure 1c: worldpop_share | meta_share — true comparison figures
# Figure 1c–1d: Same, clipped to Nairobi (raw and log1p)
# Figure 2: Bivariate WorldPop vs Meta (z-score classification)
#
# Requires: harmonised data from 01_harmonise_datasets.py
# Usage: Rscript pipeline/01_plot_descriptive.R
#        Rscript pipeline/01_plot_descriptive.R -i outputs/01/harmonised_meta_worldpop.gpkg
#        Rscript pipeline/01_plot_descriptive.R --threshold 0.5   # bivariate z-score threshold
#        Rscript pipeline/01_plot_descriptive.R --region philippines
#        Rscript pipeline/01_plot_descriptive.R --no-basemap      # skip basemap (avoids memory limit)
#        Rscript pipeline/01_plot_descriptive.R --basemap-zoom 9  # lower zoom to reduce memory
#
# Optional: install.packages(c("patchwork", "biscale", "cowplot"))

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
})
use_patchwork <- requireNamespace("patchwork", quietly = TRUE)
if (use_patchwork) library(patchwork)

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
script_dir <- file.path(project_root, "pipeline")
source(file.path(script_dir, "region_config.R"), local = TRUE)

input_path <- file.path(project_root, "outputs", "01", "harmonised_meta_worldpop.gpkg")
out_dir <- file.path(project_root, "outputs", "01")
output_data_overview_raw <- file.path(out_dir, "01_data_overview_raw.png")
output_data_overview_log1p <- file.path(out_dir, "01_data_overview_log1p.png")
output_share_maps <- file.path(out_dir, "01_share_maps.png")
output_data_overview_clip_raw <- file.path(out_dir, "01_data_overview_clip_raw.png")
output_data_overview_clip_log1p <- file.path(out_dir, "01_data_overview_clip_log1p.png")
output_bivariate <- file.path(out_dir, "01_bivariate_worldpop_meta.png")
output_bivariate_basemap <- file.path(out_dir, "01_bivariate_worldpop_meta_basemap.png")
threshold <- 0.5
region_arg <- NULL  # PHI, KEN, MEX from --region; or NULL for auto
skip_basemap <- FALSE
basemap_zoom_arg <- NULL  # override default zoom if set

args <- commandArgs(trailingOnly = TRUE)
i <- 1
while (i <= length(args)) {
  if (args[i] == "-i" && i < length(args)) {
    input_path <- args[i + 1]
    out_dir <- dirname(input_path)
    output_data_overview_raw <- file.path(out_dir, "01_data_overview_raw.png")
    output_data_overview_log1p <- file.path(out_dir, "01_data_overview_log1p.png")
    output_share_maps <- file.path(out_dir, "01_share_maps.png")
    output_data_overview_clip_raw <- file.path(out_dir, "01_data_overview_clip_raw.png")
    output_data_overview_clip_log1p <- file.path(out_dir, "01_data_overview_clip_log1p.png")
    output_bivariate <- file.path(out_dir, "01_bivariate_worldpop_meta.png")
    output_bivariate_basemap <- file.path(out_dir, "01_bivariate_worldpop_meta_basemap.png")
    i <- i + 2
  } else if (args[i] == "--threshold" && i < length(args)) {
    threshold <- as.numeric(args[i + 1])
    if (is.na(threshold) || threshold <= 0) stop("--threshold must be positive (e.g. 0.5 or 1)")
    i <- i + 2
  } else if (args[i] == "--region" && i < length(args)) {
    region_arg <- args[i + 1]
    if (region_arg == "philippines") region_arg <- "PHI"
    if (region_arg == "nairobi") region_arg <- "KEN_Nairobi"
    if (region_arg == "mombasa") region_arg <- "KEN_Mombasa"
    if (region_arg == "auto") region_arg <- NULL
    if (!is.null(region_arg)) {
      regions <- load_regions()
      valid <- setdiff(names(regions), "data_root")
      if (length(valid) > 0 && !region_arg %in% valid) {
        stop("--region must be a valid region from config (e.g. PHI_CagayandeOroCity, PHI_DavaoCity, KEN_Nairobi, KEN_Mombasa, MEX, PRT)")
      }
    }
    i <- i + 2
  } else if (args[i] == "--no-basemap") {
    skip_basemap <- TRUE
    i <- i + 1
  } else if (args[i] == "--basemap-zoom" && i < length(args)) {
    basemap_zoom_arg <- as.integer(args[i + 1])
    if (is.na(basemap_zoom_arg) || basemap_zoom_arg < 1 || basemap_zoom_arg > 18) {
      stop("--basemap-zoom must be 1-18 (e.g. 10)")
    }
    i <- i + 2
  } else {
    i <- i + 1
  }
}

if (!file.exists(input_path)) {
  stop("Run script 01 first. Missing: ", input_path)
}

gdf <- st_read(input_path, quiet = TRUE)

# Get map_bbox (when clip_shape: uses data extent; else from config)
map_bbox <- get_map_bbox_for_plot(region_arg, input_path, gdf)
if (!is.null(map_bbox)) {
  message("Using map extent: ", paste(round(map_bbox, 4), collapse = ", "))
}

# Region-specific output paths
use_clip <- !is.null(map_bbox)
output_clip_raw <- output_data_overview_clip_raw
output_clip_log1p <- output_data_overview_clip_log1p

# Compute shares before clip (needed for gdf_plot)
has_share <- "worldpop_share" %in% names(gdf) && "meta_share" %in% names(gdf)
if (!has_share && "worldpop_count" %in% names(gdf) && "meta_baseline" %in% names(gdf)) {
  gdf <- gdf %>%
    mutate(
      worldpop_share = worldpop_count / sum(worldpop_count, na.rm = TRUE),
      meta_share = meta_baseline / sum(meta_baseline, na.rm = TRUE)
    )
  has_share <- TRUE
}

# Zoom-first: use clipped data when map_bbox available
gdf_plot <- clip_gdf_to_bbox(gdf, map_bbox)

# coord_sf limits from map_bbox
coord_map <- coord_from_bbox(map_bbox)

# -----------------------------------------------------------------------------
# Row 1: Data overview (Meta, WorldPop, Poverty) — legend from zoomed data
# -----------------------------------------------------------------------------
theme_map <- function() {
  theme_void() +
    theme(
      plot.title = element_text(hjust = 0.5, face = "bold", size = 10),
      legend.position = "bottom",
      legend.direction = "horizontal",
      legend.title = element_text(size = 10, face = "bold"),
      legend.text = element_text(size = 9),
      plot.margin = margin(2, 2, 2, 2, "pt"),
      panel.border = element_rect(fill = NA, color = "grey70", linewidth = 0.5)
    )
}
guide_horizontal <- guide_colorbar(
  barwidth = unit(10, "lines"),
  barheight = unit(0.5, "cm"),
  title.position = "top",
  title.hjust = 0.5
)

add_coord <- function(p) p + coord_map

p_meta <- ggplot(gdf_plot) +
  geom_sf(aes(fill = meta_baseline), color = "white", linewidth = 0.12) +
  scale_fill_viridis_c(option = "plasma", na.value = "grey95", name = "Count",
    trans = "log1p", labels = scales::comma, guide = guide_horizontal) +
  labs(title = "Meta (midnight baseline)") +
  theme_map()
p_meta <- add_coord(p_meta)

p_wp <- ggplot(gdf_plot) +
  geom_sf(aes(fill = worldpop_count), color = "white", linewidth = 0.12) +
  scale_fill_viridis_c(option = "viridis", na.value = "grey95", name = "Count",
    trans = "log1p", labels = scales::comma, guide = guide_horizontal) +
  labs(title = "WorldPop (sum)") +
  theme_map()
p_wp <- add_coord(p_wp)

has_poverty <- "poverty_mean" %in% names(gdf)
if (has_poverty) {
  p_pov <- ggplot(gdf_plot) +
    geom_sf(aes(fill = poverty_mean), color = "white", linewidth = 0.12) +
    scale_fill_viridis_c(option = "viridis", na.value = "grey95", name = "MPI proportion",
      limits = c(0, NA), guide = guide_horizontal) +
    labs(title = "Poverty (MPI mean)") +
    theme_map()
  p_pov <- add_coord(p_pov)
  row1 <- p_meta + p_wp + p_pov
} else {
  row1 <- p_meta + p_wp
}

# -----------------------------------------------------------------------------
# Row 2: Same 3 variables, log1p-transformed (logged) values
# -----------------------------------------------------------------------------
gdf_log <- gdf_plot %>%
  mutate(
    meta_log = log1p(meta_baseline),
    worldpop_log = log1p(worldpop_count),
    poverty_log = if (has_poverty) log1p(poverty_mean) else NA_real_
  )

p_meta_log <- ggplot(gdf_log) +
  geom_sf(aes(fill = meta_log), color = "white", linewidth = 0.12) +
  scale_fill_viridis_c(option = "plasma", na.value = "grey95", name = "log1p(Count)",
    guide = guide_horizontal) +
  labs(title = "Meta (log1p)") +
  theme_map()
p_meta_log <- add_coord(p_meta_log)

p_wp_log <- ggplot(gdf_log) +
  geom_sf(aes(fill = worldpop_log), color = "white", linewidth = 0.12) +
  scale_fill_viridis_c(option = "viridis", na.value = "grey95", name = "log1p(Count)",
    guide = guide_horizontal) +
  labs(title = "WorldPop (log1p)") +
  theme_map()
p_wp_log <- add_coord(p_wp_log)

if (has_poverty) {
  p_pov_log <- ggplot(gdf_log) +
    geom_sf(aes(fill = poverty_log), color = "white", linewidth = 0.12) +
    scale_fill_viridis_c(option = "viridis", na.value = "grey95", name = "log1p(MPI proportion)",
      guide = guide_horizontal) +
    labs(title = "Poverty (log1p)") +
    theme_map()
  p_pov_log <- add_coord(p_pov_log)
  row2 <- p_meta_log + p_wp_log + p_pov_log
} else {
  row2 <- p_meta_log + p_wp_log
}

# -----------------------------------------------------------------------------
# Row 2: Bivariate WorldPop vs Meta — z-scores from zoomed data for clearer legend
# -----------------------------------------------------------------------------
gdf_bi <- gdf_plot %>% filter(worldpop_count > 0, meta_baseline > 0)
z_wp <- (gdf_bi$worldpop_count - mean(gdf_bi$worldpop_count)) / sd(gdf_bi$worldpop_count)
z_meta <- (gdf_bi$meta_baseline - mean(gdf_bi$meta_baseline)) / sd(gdf_bi$meta_baseline)
classify_z <- function(z, t) {
  dplyr::case_when(z < -t ~ 1L, z > t ~ 3L, TRUE ~ 2L)
}
gdf_bi <- gdf_bi %>%
  mutate(
    wp_class = classify_z(z_wp, threshold),
    meta_class = classify_z(z_meta, threshold),
    bi_class = paste0(wp_class, "-", meta_class)
  )

bivariate_palette <- c(
  "1-1" = "#e8e8e8", "2-1" = "#e4acac", "3-1" = "#c85a5a",
  "1-2" = "#b8d6be", "2-2" = "#ad9ea5", "3-2" = "#985356",
  "1-3" = "#64acbe", "2-3" = "#627f8c", "3-3" = "#574249"
)
gdf_bi$bi_class <- factor(gdf_bi$bi_class, levels = names(bivariate_palette))

use_biscale <- requireNamespace("biscale", quietly = TRUE)
use_cowplot <- requireNamespace("cowplot", quietly = TRUE)

if (use_biscale && use_cowplot) {
  map_bi <- ggplot(gdf_bi) +
    geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.2, show.legend = FALSE) +
    biscale::bi_scale_fill(pal = "DkBlue", dim = 3) +
    biscale::bi_theme() +
    labs(title = "Bivariate: WorldPop vs Meta (z-score)", subtitle = sprintf("Threshold ±%.1f", threshold))
  map_bi <- add_coord(map_bi)
  legend_bi <- biscale::bi_legend(pal = "DkBlue", dim = 3, xlab = "Higher WorldPop ", ylab = "Higher Meta ", size = 10)
  p_bi <- cowplot::ggdraw() +
    cowplot::draw_plot(map_bi, 0, 0, 1, 1) +
    cowplot::draw_plot(legend_bi, 0.12, 0.02, 0.28, 0.28)
} else if (use_biscale) {
  p_bi <- ggplot(gdf_bi) +
    geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.2) +
    biscale::bi_scale_fill(pal = "DkBlue", dim = 3) +
    biscale::bi_theme() +
    theme(legend.position = "right") +
    labs(title = "Bivariate: WorldPop vs Meta (z-score)", subtitle = sprintf("Threshold ±%.1f", threshold))
  p_bi <- add_coord(p_bi)
} else {
  p_bi <- ggplot(gdf_bi) +
    geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.2) +
    scale_fill_manual(values = bivariate_palette, na.value = "grey90", drop = FALSE,
      name = sprintf("Z-score (t=±%.1f)\nWorldPop | Meta", threshold)) +
    theme_void() +
    theme(
      legend.position = c(0.02, 0.02),
      legend.justification = c(0, 0),
      legend.title = element_text(size = 10, face = "bold"),
      legend.text = element_text(size = 9),
      plot.title = element_text(hjust = 0.5, face = "bold", size = 10)
    ) +
    labs(title = "Bivariate: WorldPop vs Meta", subtitle = sprintf("Threshold ±%.1f", threshold))
  p_bi <- add_coord(p_bi)
}

# -----------------------------------------------------------------------------
# Save separate figures
# -----------------------------------------------------------------------------
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# Figure 1a: Row 1 only — raw values
# Figure 1b: Row 2 only — log1p-transformed
if (use_patchwork) {
  ncols <- if (has_poverty) 3 else 2
  if (has_poverty) {
    p_row1 <- patchwork::wrap_plots(p_meta, p_wp, p_pov, ncol = ncols) +
      patchwork::plot_annotation(title = "Raw signal maps (descriptive only) — quadkey grid")
    p_row2 <- patchwork::wrap_plots(p_meta_log, p_wp_log, p_pov_log, ncol = ncols) +
      patchwork::plot_annotation(title = "Raw signal maps (descriptive only) — log1p")
  } else {
    p_row1 <- patchwork::wrap_plots(p_meta, p_wp, ncol = ncols) +
      patchwork::plot_annotation(title = "Raw signal maps (descriptive only) — quadkey grid")
    p_row2 <- patchwork::wrap_plots(p_meta_log, p_wp_log, ncol = ncols) +
      patchwork::plot_annotation(title = "Raw signal maps (descriptive only) — log1p")
  }
} else if (requireNamespace("gridExtra", quietly = TRUE)) {
  ncols <- if (has_poverty) 3 else 2
  if (has_poverty) {
    p_row1 <- gridExtra::grid.arrange(p_meta, p_wp, p_pov, ncol = ncols, top = "Raw signal maps (descriptive only)")
    p_row2 <- gridExtra::grid.arrange(p_meta_log, p_wp_log, p_pov_log, ncol = ncols, top = "Raw signal maps (descriptive only) — log1p")
  } else {
    p_row1 <- gridExtra::grid.arrange(p_meta, p_wp, ncol = ncols, top = "Raw signal maps (descriptive only)")
    p_row2 <- gridExtra::grid.arrange(p_meta_log, p_wp_log, ncol = ncols, top = "Raw signal maps (descriptive only) — log1p")
  }
} else {
  stop("Install patchwork or gridExtra: install.packages(c('patchwork','gridExtra'))")
}
if (use_patchwork) {
  ggsave(output_data_overview_raw, p_row1, width = 12, height = 4, dpi = 200, bg = "white")
  ggsave(output_data_overview_log1p, p_row2, width = 12, height = 4, dpi = 200, bg = "white")
} else {
  png(output_data_overview_raw, width = 12, height = 4, units = "in", res = 200, bg = "white")
  grid::grid.draw(p_row1)
  dev.off()
  png(output_data_overview_log1p, width = 12, height = 4, units = "in", res = 200, bg = "white")
  grid::grid.draw(p_row2)
  dev.off()
}
message("Saved: ", output_data_overview_raw, ", ", output_data_overview_log1p)
if (use_clip) {
  if (use_patchwork) {
    ggsave(output_clip_raw, p_row1, width = 12, height = 4, dpi = 200, bg = "white")
    ggsave(output_clip_log1p, p_row2, width = 12, height = 4, dpi = 200, bg = "white")
  } else {
    png(output_clip_raw, width = 12, height = 4, units = "in", res = 200, bg = "white")
    grid::grid.draw(p_row1)
    dev.off()
    png(output_clip_log1p, width = 12, height = 4, units = "in", res = 200, bg = "white")
    grid::grid.draw(p_row2)
    dev.off()
  }
  message("Saved: ", output_clip_raw, ", ", output_clip_log1p)
}

# -----------------------------------------------------------------------------
# Share maps (worldpop_share, meta_share) — legend from zoomed data
# -----------------------------------------------------------------------------
if (has_share) {
  p_wp_share <- ggplot(gdf_plot) +
    geom_sf(aes(fill = worldpop_share), color = "white", linewidth = 0.12) +
    scale_fill_viridis_c(option = "viridis", na.value = "grey95", name = "Share",
      trans = "log1p", guide = guide_horizontal) +
    labs(title = "WorldPop share (spatial allocation)") +
    theme_map()
  p_wp_share <- add_coord(p_wp_share)
  p_meta_share <- ggplot(gdf_plot) +
    geom_sf(aes(fill = meta_share), color = "white", linewidth = 0.12) +
    scale_fill_viridis_c(option = "plasma", na.value = "grey95", name = "Share",
      trans = "log1p", guide = guide_horizontal) +
    labs(title = "Meta share (spatial allocation)") +
    theme_map()
  p_meta_share <- add_coord(p_meta_share)
  if (use_patchwork) {
    p_share <- patchwork::wrap_plots(p_wp_share, p_meta_share, ncol = 2) +
      patchwork::plot_annotation(title = "Spatial allocation shares — true comparison figures")
  } else if (requireNamespace("gridExtra", quietly = TRUE)) {
    p_share <- gridExtra::grid.arrange(p_wp_share, p_meta_share, ncol = 2,
      top = "Spatial allocation shares — true comparison figures")
  } else {
    p_share <- NULL
  }
  if (!is.null(p_share)) {
    if (use_patchwork) {
      ggsave(output_share_maps, p_share, width = 10, height = 5, dpi = 200, bg = "white")
    } else {
      png(output_share_maps, width = 10, height = 5, units = "in", res = 200, bg = "white")
      grid::grid.draw(p_share)
      dev.off()
    }
    message("Saved: ", output_share_maps)
  }
} else {
  message("Skipping share maps (worldpop_share/meta_share not in input)")
}

# Figure 2: Bivariate WorldPop vs Meta
ggsave(output_bivariate, p_bi, width = 10, height = 8, dpi = 150, bg = "white")
message("Saved: ", output_bivariate)

# Figure 3: Bivariate with Sentinel/satellite basemap
# Use smaller extent and lower zoom for Philippines to avoid memory limit (16GB)
use_ggspatial <- requireNamespace("ggspatial", quietly = TRUE)
use_maptiles <- requireNamespace("maptiles", quietly = TRUE)
use_cowplot <- requireNamespace("cowplot", quietly = TRUE)
basemap_layer <- NULL
basemap_title_add <- " (with basemap)"
basemap_extent <- gdf_bi  # already zoomed when clip (from gdf_plot)
basemap_zoom <- if (!is.null(basemap_zoom_arg)) basemap_zoom_arg else if (!is.null(map_bbox)) 10 else 12
if (!skip_basemap && use_maptiles && requireNamespace("terra", quietly = TRUE)) {
  tryCatch({
    s2_provider <- maptiles::create_provider(
      name = "Sentinel2-EOX",
      url = "https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/webmercator/{z}/{x}/{y}.jpeg",
      citation = "Sentinel-2 cloudless by EOX (s2maps.eu)"
    )
    tiles_s2 <- maptiles::get_tiles(basemap_extent, provider = s2_provider, zoom = basemap_zoom, crop = TRUE, cachedir = tempdir())
    if (terra::ncell(tiles_s2) > 5e6) tiles_s2 <- terra::aggregate(tiles_s2, fact = 2)
    basemap_layer <- ggspatial::annotation_spatial(tiles_s2, alpha = 0.9)
    basemap_title_add <- " (Sentinel-2 basemap)"
  }, error = function(e) {
    tryCatch({
      tiles_esri <- maptiles::get_tiles(basemap_extent, provider = "Esri.WorldImagery", zoom = basemap_zoom, crop = TRUE, cachedir = tempdir())
      if (terra::ncell(tiles_esri) > 5e6) tiles_esri <- terra::aggregate(tiles_esri, fact = 2)
      basemap_layer <<- ggspatial::annotation_spatial(tiles_esri, alpha = 0.9)
      basemap_title_add <<- " (satellite basemap)"
    }, error = function(e2) NULL)
  })
}
if (!skip_basemap && is.null(basemap_layer) && use_ggspatial) {
  tryCatch({
    basemap_layer <- ggspatial::annotation_map_tile(type = "osm", zoom = basemap_zoom, alpha = 0.8, cachedir = tempdir())
    basemap_title_add <- " (with basemap)"
  }, error = function(e) NULL)
}
if (!skip_basemap && use_ggspatial && !is.null(basemap_layer)) {
  if (use_biscale && use_cowplot) {
    map_bm <- ggplot(gdf_bi) +
      basemap_layer +
      geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.3, alpha = 0.5, show.legend = FALSE) +
      biscale::bi_scale_fill(pal = "DkBlue", dim = 3) +
      biscale::bi_theme() +
      labs(title = paste0("Bivariate: WorldPop vs Meta", basemap_title_add), subtitle = sprintf("Threshold ±%.1f", threshold))
    map_bm <- add_coord(map_bm)
    legend_bm <- biscale::bi_legend(pal = "DkBlue", dim = 3, xlab = "Higher WorldPop ", ylab = "Higher Meta ", size = 10)
    p_bm <- cowplot::ggdraw() +
      cowplot::draw_plot(map_bm, 0, 0, 1, 1) +
      cowplot::draw_plot(legend_bm, 0.05, 0.02, 0.28, 0.28)
  } else {
    map_bm <- ggplot(gdf_bi) +
      basemap_layer +
      geom_sf(aes(fill = bi_class), color = "white", linewidth = 0.3, alpha = 0.5) +
      scale_fill_manual(values = bivariate_palette, na.value = "grey90", drop = FALSE,
        name = sprintf("Z-score (t=±%.1f)\nWorldPop | Meta", threshold)) +
      theme_void() +
      theme(legend.position = c(0.02, 0.02), legend.justification = c(0, 0),
        legend.title = element_text(size = 10, face = "bold"),
        legend.text = element_text(size = 9),
        plot.title = element_text(hjust = 0.5, face = "bold")) +
      labs(title = paste0("Bivariate: WorldPop vs Meta", basemap_title_add), subtitle = sprintf("Threshold ±%.1f", threshold))
    p_bm <- add_coord(map_bm)
  }
  tryCatch({
    ggsave(output_bivariate_basemap, p_bm, width = 10, height = 8, dpi = 150, bg = "white")
    message("Saved: ", output_bivariate_basemap)
  }, error = function(e) {
    message("Basemap save failed (memory?): ", conditionMessage(e))
    message("Skipping ", output_bivariate_basemap, " — try --no-basemap or lower zoom")
  })
} else if (skip_basemap) {
  message("Skipping basemap (--no-basemap)")
} else if (!use_ggspatial) {
  message("Install ggspatial for basemap version: install.packages('ggspatial')")
} else {
  message("Could not fetch basemap tiles (network?). Install maptiles: install.packages('maptiles')")
}
