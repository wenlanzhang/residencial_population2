#!/usr/bin/env Rscript
# 04b_plots.R — Crisis inference sensitivity maps and S-by-deprivation
#
# Fig 04b-1 (per city): three maps
#   A. G under the actual Meta baseline
#   B. G under the WorldPop-pattern counterfactual baseline (same colour scale)
#   C. Changed inference (increase/decrease both vs sign flips)
# Annotation: F, J_10+, J_10-
#
# Also: 04b_S_by_deprivation.png (supplement: |G_Meta − G_WP|, C cancels)
#        04b_snapshot_F.png (F across crisis days at the reference hour)
#
# Usage:
#   Rscript pipeline/04b_plots.R --region ZAF_CapeTown
#   Rscript pipeline/04b_plots.R -i outputs/city/ZAF/CapeTown/04b_crisis_inference --region ZAF_CapeTown

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
})

theme_nature_map <- function() {
  theme_void() +
    theme(
      plot.title = element_text(face = "bold", size = 11, hjust = 0.5),
      legend.title = element_text(face = "bold", size = 9),
      legend.text = element_text(size = 8),
      plot.margin = margin(4, 4, 4, 4)
    )
}

theme_nature <- function(base_size = 10, base_family = "sans") {
  theme_minimal(base_size = base_size, base_family = base_family) +
    theme(
      panel.grid.minor = element_blank(),
      panel.grid.major = element_line(linewidth = 0.25, colour = "grey92"),
      axis.line = element_line(linewidth = 0.5, colour = "black"),
      axis.ticks = element_line(linewidth = 0.5, colour = "black"),
      axis.text = element_text(colour = "black", size = rel(0.9)),
      axis.title = element_text(colour = "black", size = rel(1), face = "bold"),
      plot.title = element_text(face = "bold", size = rel(1.1), hjust = 0),
      plot.subtitle = element_text(size = rel(0.95), colour = "grey30", hjust = 0),
      plot.margin = margin(10, 10, 10, 10)
    )
}

initial_ca <- commandArgs(trailingOnly = FALSE)
ff <- grep("^--file=", initial_ca, value = TRUE)
project_root <- if (length(ff)) {
  dirname(dirname(normalizePath(sub("^--file=", "", ff[1]), winslash = "/", mustWork = TRUE)))
} else {
  normalizePath(".", winslash = "/", mustWork = TRUE)
}
source(file.path(project_root, "pipeline", "region_config.R"), local = TRUE)

in_arg <- NULL
out_arg <- NULL
region_cli <- NULL
footprint_cli <- NULL
args <- commandArgs(trailingOnly = TRUE)
i <- 1L
while (i <= length(args)) {
  if (args[i] == "-i" && i < length(args)) {
    in_arg <- args[i + 1]
    i <- i + 2L
  } else if (args[i] == "-o" && i < length(args)) {
    out_arg <- args[i + 1]
    i <- i + 2L
  } else if (args[i] == "--region" && i < length(args)) {
    region_cli <- args[i + 1]
    i <- i + 2L
  } else if (args[i] == "--footprint" && i < length(args)) {
    footprint_cli <- args[i + 1]
    i <- i + 2L
  } else {
    i <- i + 1L
  }
}

step <- "04b_crisis_inference"
if (!is.null(footprint_cli) && nzchar(footprint_cli)) {
  csv_dir_in <- footprint_csv_dir(footprint_cli, step)
  gpkg_path <- file.path(footprint_geo_dir(footprint_cli, step), "04b_crisis_inference.gpkg")
  out_dir <- footprint_figure_dir(footprint_cli, step)
  city_lab <- city_display_label(footprint_cli)
} else if (!is.null(region_cli) && nzchar(region_cli)) {
  csv_dir_in <- csv_dir(region_cli, step)
  gpkg_path <- file.path(geo_dir(region_cli, step), "04b_crisis_inference.gpkg")
  out_dir <- figure_dir(region_cli, step)
  city_lab <- city_display_label(region_cli)
} else if (!is.null(in_arg) && dir.exists(in_arg)) {
  csv_dir_in <- in_arg
  inf <- region_from_artifact_path(in_arg)
  fp <- footprint_code_from_path(in_arg)
  if (!is.null(fp)) {
    gpkg_path <- file.path(footprint_geo_dir(fp, step), "04b_crisis_inference.gpkg")
    out_dir <- footprint_figure_dir(fp, step)
    city_lab <- city_display_label(fp)
  } else if (!is.null(inf)) {
    gpkg_path <- file.path(geo_dir(inf, step), "04b_crisis_inference.gpkg")
    out_dir <- figure_dir(inf, step)
    city_lab <- city_display_label(inf)
  } else {
    gpkg_path <- file.path(in_arg, "04b_crisis_inference.gpkg")
    out_dir <- in_arg
    city_lab <- "City"
  }
} else {
  stop("Provide --region, --footprint, or -i <04b_crisis_inference directory>")
}

if (!is.null(in_arg) && dir.exists(in_arg)) csv_dir_in <- in_arg
if (!is.null(out_arg) && nzchar(out_arg)) out_dir <- out_arg
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

tbl_path <- file.path(csv_dir_in, "Table4c_crisis_inference_sensitivity.csv")
if (!file.exists(gpkg_path)) {
  alt <- file.path(csv_dir_in, "04b_crisis_inference.gpkg")
  if (file.exists(alt)) gpkg_path <- alt
}
if (!file.exists(gpkg_path)) stop("Missing 04b GPKG: ", gpkg_path)
if (!file.exists(tbl_path)) stop("Missing Table4c: ", tbl_path)

gdf <- st_read(gpkg_path, quiet = TRUE)
tbl <- read.csv(tbl_path, stringsAsFactors = FALSE)
gdf <- gdf[is.finite(gdf$G_meta) & is.finite(gdf$G_wp), ]
if (nrow(gdf) == 0) stop("No finite G_meta / G_wp rows in ", gpkg_path)

f_pct <- if ("direction_flip_pct" %in% names(tbl)) tbl$direction_flip_pct[[1]] else NA_real_
j_inc <- if ("jaccard_increase_top10" %in% names(tbl)) tbl$jaccard_increase_top10[[1]] else NA_real_
j_dec <- if ("jaccard_decrease_top10" %in% names(tbl)) tbl$jaccard_decrease_top10[[1]] else NA_real_
annot <- sprintf(
  "F = %.1f%% of cells change inferred direction    J[10]^+ = %.2f    J[10]^- = %.2f",
  f_pct, j_inc, j_dec
)
annot_plain <- sprintf(
  "F=%.1f%% of cells change inferred direction solely because baseline spatial allocation changes.  J10+=%.2f   J10-=%.2f",
  f_pct, j_inc, j_dec
)

vlim <- max(abs(c(gdf$G_meta, gdf$G_wp)), na.rm = TRUE)
vlim <- max(min(vlim, 2.5), 0.2)
crs_epsg <- utm_epsg(gdf)
gdf_proj <- st_transform(gdf, crs_epsg)
gdf_proj$G_meta_clip <- pmin(pmax(gdf_proj$G_meta, -vlim), vlim)
gdf_proj$G_wp_clip <- pmin(pmax(gdf_proj$G_wp, -vlim), vlim)

cls_levels <- c(
  "increase_both", "decrease_both",
  "increase_to_decrease", "decrease_to_increase", "other"
)
cls_labels <- c(
  "Increase under both",
  "Decrease under both",
  "Increase -> decrease",
  "Decrease -> increase",
  "Zero / mixed"
)
cls_cols <- c(
  "Increase under both" = "#798234",
  "Decrease under both" = "#D46780",
  "Increase -> decrease" = "#C47B2B",
  "Decrease -> increase" = "#4C78A8",
  "Zero / mixed" = "grey75"
)
gdf_proj$inference_lab <- factor(
  gdf_proj$inference_change,
  levels = cls_levels,
  labels = cls_labels
)

plot_g <- function(fill_col, title) {
  ggplot(gdf_proj) +
    geom_sf(aes(fill = .data[[fill_col]]), colour = NA) +
    scale_fill_gradientn(
      colours = ARMYROSE,
      values = seq(0, 1, length.out = 7),
      limits = c(-vlim, vlim),
      oob = scales::squish,
      name = "Inferred change"
    ) +
    labs(
      title = title,
      subtitle = "Population decrease  \u2190  0  \u2192  population increase"
    ) +
    theme_nature_map() +
    theme(
      plot.subtitle = element_text(size = 8, colour = "grey35", hjust = 0.5),
      legend.position = "bottom",
      legend.direction = "horizontal",
      legend.key.width = grid::unit(1.1, "cm"),
      legend.key.height = grid::unit(0.35, "cm")
    )
}

p_a <- plot_g("G_meta_clip", "A. Actual Meta baseline")
p_b <- plot_g("G_wp_clip", "B. WorldPop-pattern baseline")
p_c <- ggplot(gdf_proj) +
  geom_sf(aes(fill = inference_lab), colour = NA) +
  scale_fill_manual(values = cls_cols, drop = FALSE, name = NULL) +
  labs(title = "C. Changed inference") +
  theme_nature_map() +
  theme(
    legend.position = "bottom",
    legend.direction = "horizontal"
  )

f_maps <- file.path(out_dir, "04b_crisis_sensitivity_maps.png")
if (requireNamespace("patchwork", quietly = TRUE)) {
    p6 <- (p_a | p_b | p_c) +
      patchwork::plot_annotation(
        title = paste0(city_lab, ": does the baseline change what we infer during the crisis?"),
        subtitle = annot_plain
      )
  ggplot2::ggsave(f_maps, p6, width = 14.2, height = 5.6, dpi = 300, bg = "white")
  message("Saved: ", f_maps)
} else if (requireNamespace("cowplot", quietly = TRUE)) {
  title_canvas <- cowplot::ggdraw() +
    cowplot::draw_label(
      paste0(city_lab, ": does the baseline change what we infer during the crisis?"),
      fontface = "bold", size = 13, x = 0, hjust = 0
    )
  sub_canvas <- cowplot::ggdraw() +
    cowplot::draw_label(annot_plain, size = 10, x = 0, hjust = 0)
  panels <- cowplot::plot_grid(p_a, p_b, p_c, ncol = 3, align = "h")
  p6 <- cowplot::plot_grid(title_canvas, sub_canvas, panels, ncol = 1, rel_heights = c(0.08, 0.07, 1))
  ggplot2::ggsave(f_maps, p6, width = 14.2, height = 5.8, dpi = 300, bg = "white")
  message("Saved: ", f_maps)
} else {
  warning("04b maps combined figure skipped: install patchwork or cowplot")
}

# Two-group S distribution (Cape Town worked-example style; produced for every city)
if ("S" %in% names(gdf) && "high_deprivation" %in% names(gdf)) {
  dd <- gdf %>%
    sf::st_drop_geometry() %>%
    filter(is.finite(S)) %>%
    mutate(
      grp = factor(
        ifelse(high_deprivation == 1, "High deprivation", "Other cells"),
        levels = c("High deprivation", "Other cells")
      )
    )
  p_s <- ggplot(dd, aes(x = grp, y = S, fill = grp)) +
    geom_violin(colour = NA, alpha = 0.55, width = 0.85) +
    geom_boxplot(width = 0.18, outlier.size = 0.6, alpha = 0.9) +
    scale_fill_manual(values = c("High deprivation" = "#D46780", "Other cells" = "#798234"), guide = "none") +
    labs(
      title = paste0(city_lab, ": baseline-induced change-metric divergence"),
      subtitle = "S = |G(Meta) \u2212 G(WorldPop-pattern)|; C cancels, so this is baseline discrepancy",
      x = NULL,
      y = expression(S[i])
    ) +
    theme_nature()
  f_s <- file.path(out_dir, "04b_S_by_deprivation.png")
  ggsave(f_s, p_s, width = 6.2, height = 4.6, dpi = 300, bg = "white")
  message("Saved: ", f_s)
}

snap_path <- file.path(csv_dir_in, "Table4d_crisis_snapshots.csv")
if (file.exists(snap_path)) {
  snap <- read.csv(snap_path, stringsAsFactors = FALSE)
  if (nrow(snap) && "direction_flip_pct" %in% names(snap) && "date" %in% names(snap)) {
    snap$date <- as.Date(snap$date)
    snap <- snap[order(snap$date), ]
    p_t <- ggplot(snap, aes(x = date, y = direction_flip_pct)) +
      geom_line(colour = "#798234", linewidth = 0.7) +
      geom_point(colour = "#798234", size = 2.2) +
      scale_y_continuous(limits = c(0, NA), expand = expansion(mult = c(0.02, 0.08))) +
      labs(
        title = paste0(city_lab, ": flip rate across crisis snapshots"),
        subtitle = "Same reference hour; each point is one crisis day",
        x = NULL,
        y = "Cells changing inferred direction (%)"
      ) +
      theme_nature()
    f_t <- file.path(out_dir, "04b_snapshot_F.png")
    ggsave(f_t, p_t, width = 7.0, height = 4.0, dpi = 300, bg = "white")
    message("Saved: ", f_t)
  }
}
