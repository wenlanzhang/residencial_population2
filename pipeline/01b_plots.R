#!/usr/bin/env Rscript
# 01b_plots.R — Meta coverage map on the independent city grid
#
# Reads: data/processed/.../01b_coverage/independent_grid.gpkg
#        (or -i pointing at the GPKG / 01b_coverage folder)
# Outputs: 01b_meta_coverage_r.png
#
# Usage: Rscript pipeline/01b_plots.R --region ZAF_CapeTown
#        Rscript pipeline/01b_plots.R -i path/to/independent_grid.gpkg --region ZAF_CapeTown

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
})

theme_nature_map <- function() {
  theme_void() +
    theme(
      plot.title = element_text(face = "bold", size = 12, hjust = 0),
      plot.subtitle = element_text(size = 9.5, colour = "grey30", hjust = 0),
      legend.title = element_blank(),
      legend.text = element_text(size = 9),
      legend.position = "bottom",
      legend.justification = "left",
      plot.margin = margin(10, 10, 10, 10)
    )
}

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
script_dir <- file.path(project_root, "pipeline")
source(file.path(script_dir, "region_config.R"), local = TRUE)

in_path <- NULL
out_dir <- NULL
region_arg <- NULL
o_arg <- NULL
footprint_arg <- NULL
args <- commandArgs(trailingOnly = TRUE)
i <- 1
while (i <= length(args)) {
  if (args[i] == "-i" && i < length(args)) {
    in_path <- args[i + 1]
    i <- i + 2
  } else if (args[i] == "-o" && i < length(args)) {
    o_arg <- args[i + 1]
    i <- i + 2
  } else if (args[i] == "--region" && i < length(args)) {
    region_arg <- args[i + 1]
    i <- i + 2
  } else if (args[i] == "--footprint" && i < length(args)) {
    footprint_arg <- args[i + 1]
    i <- i + 2
  } else {
    i <- i + 1
  }
}

if (!is.null(region_arg) && nzchar(region_arg) && (is.null(in_path) || !nzchar(in_path))) {
  in_path <- file.path(geo_dir(region_arg, "01b_coverage"), "independent_grid.gpkg")
}
if (is.null(in_path) || !nzchar(in_path)) {
  stop("Pass --region CITY or -i independent_grid.gpkg")
}
if (dir.exists(in_path)) {
  cand <- file.path(in_path, "independent_grid.gpkg")
  if (file.exists(cand)) in_path <- cand
}
if (!file.exists(in_path)) {
  stop("Run 01b_meta_coverage_qa.py first. Missing: ", in_path)
}

out_dir <- resolve_plot_out_dir(region_arg, in_path, "01b_coverage", o_arg, footprint_arg)
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

gdf <- st_read(in_path, quiet = TRUE)
if (!"coverage_class" %in% names(gdf)) {
  stop("independent_grid.gpkg missing coverage_class; re-run 01b_meta_coverage_qa.py")
}

keep <- c("published Meta", "eligible but unpublished Meta")
gdf <- gdf %>%
  mutate(coverage_class = as.character(coverage_class)) %>%
  filter(coverage_class %in% keep)
gdf$coverage_class <- factor(gdf$coverage_class, levels = keep)

n_pub <- sum(gdf$coverage_class == "published Meta", na.rm = TRUE)
n_miss <- sum(gdf$coverage_class == "eligible but unpublished Meta", na.rm = TRUE)
n_grid <- n_pub + n_miss
c_c <- if (n_grid > 0) n_pub / n_grid else NA_real_

map_bbox <- get_map_bbox_for_plot(region_arg, in_path, gdf, footprint_arg = footprint_arg)
if (!is.null(map_bbox) && is.null(names(map_bbox)) && length(map_bbox) == 4) {
  names(map_bbox) <- c("xmin", "ymin", "xmax", "ymax")
}
gdf_plot <- clip_gdf_to_bbox(gdf, map_bbox)
coord_map <- coord_from_bbox(map_bbox)

fill_cols <- c(
  "published Meta" = "#798234",
  "eligible but unpublished Meta" = "#D46780"
)

p <- ggplot(gdf_plot) +
  geom_sf(aes(fill = coverage_class), colour = "white", linewidth = 0.08) +
  scale_fill_manual(values = fill_cols, drop = FALSE) +
  labs(
    title = "Meta coverage of the eligible city grid",
    subtitle = sprintf(
      "C_c = N_published / N_grid = %s / %s = %s   |   unpublished = %s",
      format(n_pub, big.mark = ",", trim = TRUE),
      format(n_grid, big.mark = ",", trim = TRUE),
      if (is.finite(c_c)) sprintf("%.2f", c_c) else "NA",
      format(n_miss, big.mark = ",", trim = TRUE)
    )
  ) +
  theme_nature_map()
if (!is.null(coord_map)) p <- p + coord_map

ggsave(
  file.path(out_dir, "01b_meta_coverage_r.png"),
  p, width = 7.2, height = 7.0, dpi = 300, bg = "white"
)
message("Saved: ", file.path(out_dir, "01b_meta_coverage_r.png"))
