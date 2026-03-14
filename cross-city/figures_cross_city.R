#!/usr/bin/env Rscript
# Cross-city figures for publication
#
# FIGURE 1 — Spatial Agreement (log-log scatter, 2x2 panels)
# FIGURE — Concentration Comparison (bar plot)
# FIGURE 2 — Lorenz Curves (2x2 small multiples)
# FIGURE 3 — Allocation Residual Maps (Davao + Mexico only)
# FIGURE 4 — Poverty Effect (SEM τ forest plot)
# FIGURE 5 — Cross-city scatter: ΔGini vs Poverty τ
#
# Usage: Rscript cross-city/figures_cross_city.R
#        Rscript cross-city/figures_cross_city.R -o outputs/cross-city/

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
  library(tidyr)
})
has_patchwork <- requireNamespace("patchwork", quietly = TRUE)
if (has_patchwork) library(patchwork)
has_ggspatial <- requireNamespace("ggspatial", quietly = TRUE)

# Paths
args <- commandArgs(trailingOnly = TRUE)
out_dir <- "outputs/cross-city"
if (length(args) >= 2 && args[1] == "-o") {
  out_dir <- args[2]
}
project_root <- Sys.getenv("RESPOP_PROJECT_ROOT", unset = NA)
if (is.na(project_root) || !nzchar(project_root)) {
  cmd_args <- commandArgs(trailingOnly = FALSE)
  file_arg <- grep("^--file=", cmd_args, value = TRUE)
  if (length(file_arg) > 0) {
    script_path <- normalizePath(sub("^--file=", "", file_arg), mustWork = FALSE)
    project_root <- dirname(dirname(script_path))
  } else {
    project_root <- getwd()
  }
}
out_dir <- file.path(project_root, out_dir)
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# ArmyRose palette (rcartocolor)
armyrose <- c("#798234", "#A3AD62", "#D0D3A2", "#FDFBE4", "#F0C6C3", "#DF91A3", "#D46780")

# Region mapping: display order and paths
regions <- list(
  "Davao City"    = "PHI_DavaoCity",
  "Nairobi"       = "KEN_Nairobi",
  "Mombasa"       = "KEN_Mombasa",
  "Cagayan de Oro"= "PHI_CagayandeOroCity",
  "Mexico City"   = "MEX"
)

# ---- FIGURE 1: Spatial Agreement (log-log scatter) ----
# Layout: [ Davao ] [ Nairobi ] [ Mombasa ]
#         [ Cagayan ] [ Mexico City ]
fig1_scatter_order <- c("Davao City", "Nairobi", "Mombasa", "Cagayan de Oro", "Mexico City")
fig1_scatter_plots <- list()
tbl1_path <- file.path(out_dir, "Table1_cross_city_table.csv")
tbl1_corr <- NULL
if (file.exists(tbl1_path)) {
  tbl1_corr <- read.csv(tbl1_path)
}
for (city in fig1_scatter_order) {
  reg <- regions[[city]]
  path <- file.path(project_root, "outputs", reg, "02", "harmonised_with_residual.gpkg")
  if (!file.exists(path)) next
  gdf <- st_read(path, quiet = TRUE)
  df <- data.frame(
    wp = gdf$worldpop_share,
    meta = gdf$meta_share
  )
  df <- df[df$wp > 0 & df$meta > 0, ]
  if (nrow(df) < 2) next
  df$log_wp <- log(df$wp)
  df$log_meta <- log(df$meta)
  lim <- range(c(df$log_wp, df$log_meta), na.rm = TRUE)
  if (city == "Mexico City") lim[1] <- max(lim[1], -13)
  if (city == "Nairobi") lim[1] <- max(lim[1], -10.5)
  lim <- lim + c(-0.05, 0.05) * diff(lim)
  p <- ggplot(df, aes(x = log_wp, y = log_meta)) +
    geom_hex(bins = 25, alpha = 0.85) +
    scale_fill_gradientn(colours = armyrose[4:1], name = "count") +
    geom_abline(slope = 1, intercept = 0, linetype = "dashed", colour = "gray40", linewidth = 0.6) +
    geom_smooth(method = "lm", se = TRUE, colour = armyrose[7], fill = armyrose[7], alpha = 0.2, linewidth = 0.8) +
    coord_fixed(ratio = 1, xlim = lim, ylim = lim) +
    labs(
      x = expression(log(WorldPop~share)),
      y = expression(log(Meta~share)),
      title = city
    ) +
    theme_minimal(base_size = 9) +
    theme(
      plot.title = element_text(face = "bold", hjust = 0.5),
      panel.grid.minor = element_blank(),
      legend.position = c(0.98, 0.02),
      legend.justification = c(1, 0),
      legend.background = element_rect(fill = "transparent", colour = NA),
      legend.key.size = unit(0.5, "cm"),
      legend.title = element_text(size = 8),
      legend.text = element_text(size = 7)
    )
  if (!is.null(tbl1_corr) && city %in% tbl1_corr$City) {
    row <- tbl1_corr[tbl1_corr$City == city, ]
    spearman_col <- names(row)[grepl("Spearman", names(row), ignore.case = TRUE)][1]
    pearson_col <- names(row)[grepl("Pearson", names(row), ignore.case = TRUE)][1]
    rho_val <- if (length(spearman_col) && spearman_col %in% names(row)) as.numeric(row[[spearman_col]][1]) else NA_real_
    r_val <- if (length(pearson_col) && pearson_col %in% names(row)) as.numeric(row[[pearson_col]][1]) else NA_real_
    if (!is.na(rho_val) || !is.na(r_val)) {
      lab <- if (!is.na(rho_val) && !is.na(r_val)) {
        paste0("atop(rho == ", round(rho_val, 3), ", r == ", round(r_val, 3), ")")
      } else if (!is.na(rho_val)) {
        paste0("rho == ", round(rho_val, 3))
      } else {
        paste0("r == ", round(r_val, 3))
      }
      p <- p + annotate("text", x = lim[1], y = lim[2], label = lab,
        hjust = 0, vjust = 1, size = 2.5, colour = "gray30", parse = TRUE)
    }
  }
  fig1_scatter_plots[[city]] <- p
}
if (length(fig1_scatter_plots) >= 4) {
  if (has_patchwork) {
    combined1 <- fig1_scatter_plots[["Davao City"]] + fig1_scatter_plots[["Nairobi"]] + fig1_scatter_plots[["Mombasa"]] +
      fig1_scatter_plots[["Cagayan de Oro"]] + fig1_scatter_plots[["Mexico City"]] +
      patchwork::plot_layout(ncol = 3) +
      patchwork::plot_annotation(
        title = "Spatial Agreement (log-log scatter)",
        subtitle = "Meta share vs WorldPop share. Dashed = 1:1 line; shaded = regression line. High agreement across cities."
      ) & theme(
        plot.title = element_text(face = "bold", size = 12),
        plot.subtitle = element_text(colour = "gray40", size = 9)
      )
    ggsave(file.path(out_dir, "Figure1_spatial_agreement.png"), combined1, width = 10, height = 7, dpi = 300)
    # ggsave(file.path(out_dir, "Figure1_spatial_agreement.pdf"), combined1, width = 10, height = 7)
  } else if (requireNamespace("gridExtra", quietly = TRUE)) {
    png(file.path(out_dir, "Figure1_spatial_agreement.png"), width = 10, height = 7, units = "in", res = 300)
    gridExtra::grid.arrange(
      fig1_scatter_plots[["Davao City"]], fig1_scatter_plots[["Nairobi"]], fig1_scatter_plots[["Mombasa"]],
      fig1_scatter_plots[["Cagayan de Oro"]], fig1_scatter_plots[["Mexico City"]],
      ncol = 3,
      top = "Spatial Agreement (log-log scatter)")
    dev.off()
    # pdf(file.path(out_dir, "Figure1_spatial_agreement.pdf"), width = 10, height = 7)
    # gridExtra::grid.arrange(
    #   fig1_scatter_plots[["Davao City"]], fig1_scatter_plots[["Nairobi"]], fig1_scatter_plots[["Mombasa"]],
    #   fig1_scatter_plots[["Cagayan de Oro"]], fig1_scatter_plots[["Mexico City"]],
    #   ncol = 3,
    #   top = "Spatial Agreement (log-log scatter)")
    # dev.off()
  } else {
    ggsave(file.path(out_dir, "Figure1_spatial_agreement.png"), fig1_scatter_plots[[1]], width = 6, height = 5, dpi = 300)
    message("Install patchwork or gridExtra for full 2x2 Figure 1; saved first panel only")
  }
  message("Saved: Figure1_spatial_agreement.png/.pdf")
  # Figure 1 — row version
  if (has_patchwork) {
    combined1_row <- fig1_scatter_plots[["Davao City"]] + fig1_scatter_plots[["Nairobi"]] + fig1_scatter_plots[["Mombasa"]] +
      fig1_scatter_plots[["Cagayan de Oro"]] + fig1_scatter_plots[["Mexico City"]] +
      patchwork::plot_layout(ncol = 5) +
      patchwork::plot_annotation(
        title = "Spatial Agreement (log-log scatter)",
        subtitle = "Meta share vs WorldPop share. Dashed = 1:1 line; shaded = regression line."
      ) & theme(
        plot.title = element_text(face = "bold", size = 12),
        plot.subtitle = element_text(colour = "gray40", size = 9)
      )
    ggsave(file.path(out_dir, "Figure1_spatial_agreement_row.png"), combined1_row, width = 16, height = 4, dpi = 300)
    # ggsave(file.path(out_dir, "Figure1_spatial_agreement_row.pdf"), combined1_row, width = 16, height = 4)
    message("Saved: Figure1_spatial_agreement_row.png/.pdf")
  }
}

# ---- Helper: Lorenz curve data ----
lorenz_data <- function(x) {
  x <- x[!is.na(x) & x > 0]
  if (length(x) == 0) return(data.frame(pop = c(0, 1), val = c(0, 1)))
  n <- length(x)
  x_sorted <- sort(x)
  cumval <- cumsum(x_sorted)
  data.frame(
    pop = c(0, (1:n) / n),
    val = c(0, cumval / cumval[n])
  )
}

# ---- FIGURE 2: Structural Concentration Comparison ----
fig1_data <- lapply(names(regions), function(city) {
  reg <- regions[[city]]
  path <- file.path(project_root, "outputs", reg, "02", "02_top_share_concentration.csv")
  if (!file.exists(path)) return(NULL)
  d <- read.csv(path)
  row10 <- d[d$Top_pct == 0.1, ]
  if (nrow(row10) == 0) return(NULL)
  ratio <- row10$Share_Meta / row10$Share_WP
  data.frame(City = city, Share_WP = row10$Share_WP, Share_Meta = row10$Share_Meta, Ratio = ratio)
})
fig1_data <- bind_rows(Filter(Negate(is.null), fig1_data))
if (nrow(fig1_data) > 0) {
  # Order by concentration ratio descending (Nairobi, Davao, Cagayan, Mexico)
  fig1_data <- fig1_data %>% arrange(desc(Ratio))
  fig1_data$City <- factor(fig1_data$City, levels = fig1_data$City)
  p1 <- ggplot(fig1_data, aes(x = City, y = Ratio, fill = City)) +
    geom_col(width = 0.7, alpha = 0.85) +
    geom_hline(yintercept = 1, linetype = "dashed", linewidth = 0.6, colour = "gray30") +
    geom_text(aes(label = sprintf("%.2f", Ratio)), vjust = -0.5, size = 3.5, fontface = "bold") +
    scale_fill_manual(values = c("Nairobi" = armyrose[1], "Mombasa" = armyrose[3], "Davao City" = armyrose[2], "Cagayan de Oro" = armyrose[6], "Mexico City" = armyrose[7]), guide = "none") +
    scale_y_continuous(expand = expansion(mult = c(0.02, 0.08))) +
    coord_cartesian(ylim = c(0.8, 1.25)) +
    labs(
      title = "Structural Concentration Comparison",
      subtitle = "Ratio = Meta/WP share. >1 = more concentration in Meta.",
      x = NULL, y = "Concentration ratio"
    ) +
    theme_minimal(base_size = 11) +
    theme(
      plot.title = element_text(face = "bold", size = 10, hjust = 0),
      plot.subtitle = element_text(colour = "gray40", size = 8, hjust = 0),
      panel.grid.major.x = element_blank(),
      axis.text.x = element_text(angle = 15, hjust = 1)
    )
  ggsave(file.path(out_dir, "Figure_concentration_ratio.png"), p1, width = 6, height = 3.2, dpi = 300)
  # ggsave(file.path(out_dir, "Figure_concentration_ratio.pdf"), p1, width = 6, height = 3.2)
  message("Saved: Figure_concentration_ratio.png/.pdf")
}

# ---- FIGURE 3: Lorenz Curves (2x2) ----
# Load ΔGini for annotations (from Table1)
tbl1_path <- file.path(out_dir, "Table1_cross_city_table.csv")
delta_gini <- setNames(rep(NA_real_, length(regions)), names(regions))
if (file.exists(tbl1_path)) {
  tbl1 <- read.csv(tbl1_path)
  dg_col <- names(tbl1)[grepl("Gini|Delta", names(tbl1), ignore.case = TRUE)][1]
  if (!is.na(dg_col) && dg_col %in% names(tbl1)) {
    for (i in seq_len(nrow(tbl1))) {
      city <- tbl1$City[i]
      if (city %in% names(delta_gini)) delta_gini[city] <- as.numeric(tbl1[[dg_col]][i])
    }
  }
}
fig2_plots <- list()
for (city in names(regions)) {
  reg <- regions[[city]]
  path <- file.path(project_root, "outputs", reg, "02", "harmonised_with_residual.gpkg")
  if (!file.exists(path)) next
  gdf <- st_read(path, quiet = TRUE)
  wp <- gdf$worldpop_share
  meta <- gdf$meta_share
  valid <- (wp > 0) & (meta > 0)
  wp <- wp[valid]
  meta <- meta[valid]
  lwp <- lorenz_data(wp)
  lmeta <- lorenz_data(meta)
  lwp$Source <- "WorldPop"
  lmeta$Source <- "Meta"
  ldf <- bind_rows(lwp, lmeta)
  dg <- delta_gini[city]
  dg_lab <- if (!is.na(dg)) sprintf("ΔGini = %+.3f", dg) else ""
  p <- ggplot(ldf, aes(x = pop, y = val, colour = Source, linetype = Source)) +
    geom_line(linewidth = 1.2) +
    geom_abline(slope = 1, intercept = 0, linetype = "dotted", colour = "gray50", linewidth = 0.5) +
    scale_colour_manual(values = c("WorldPop" = armyrose[1], "Meta" = armyrose[7])) +
    scale_linetype_manual(values = c("WorldPop" = "solid", "Meta" = "solid")) +
    coord_fixed(ratio = 1, xlim = c(0, 1), ylim = c(0, 1)) +
    labs(x = "Cumulative share of cells", y = "Cumulative share of allocation", title = city) +
    annotate("text", x = 0.02, y = 0.98, label = dg_lab, hjust = 0, vjust = 1, size = 2.5, colour = "gray30") +
    theme_minimal(base_size = 9) +
    theme(
      plot.title = element_text(face = "bold", hjust = 0.5),
      legend.position = "none",
      legend.title = element_blank(),
      panel.grid.minor = element_blank()
    )
  fig2_plots[[city]] <- p
}
if (length(fig2_plots) >= 4) {
  if (has_patchwork) {
    # Add legend back to one panel for collection (shared legend)
    p_with_leg <- fig2_plots[["Davao City"]] + theme(legend.position = "bottom")
    combined <- p_with_leg + fig2_plots[["Nairobi"]] + fig2_plots[["Mombasa"]] +
      fig2_plots[["Cagayan de Oro"]] + fig2_plots[["Mexico City"]] +
      patchwork::plot_layout(ncol = 3, guides = "collect") &
      theme(legend.position = "bottom", legend.title = element_blank())
    combined <- combined +
      patchwork::plot_annotation(
        title = "Lorenz Curves (Structural Illustration)",
        subtitle = "Panel A: Davao | B: Nairobi | C: Mombasa | D: Cagayan de Oro | E: Mexico City"
      ) & theme(
        plot.title = element_text(face = "bold", size = 12),
        plot.subtitle = element_text(colour = "gray40", size = 9)
      )
    ggsave(file.path(out_dir, "Figure2_lorenz_curves.png"), combined, width = 10, height = 7, dpi = 300)
    # ggsave(file.path(out_dir, "Figure2_lorenz_curves.pdf"), combined, width = 10, height = 7)
  } else if (requireNamespace("gridExtra", quietly = TRUE)) {
    png(file.path(out_dir, "Figure2_lorenz_curves.png"), width = 10, height = 7, units = "in", res = 300)
    gridExtra::grid.arrange(
      fig2_plots[["Davao City"]], fig2_plots[["Nairobi"]], fig2_plots[["Mombasa"]],
      fig2_plots[["Cagayan de Oro"]], fig2_plots[["Mexico City"]],
      ncol = 3,
      top = "Lorenz Curves (Panel A: Davao | B: Nairobi | C: Mombasa | D: Cagayan | E: Mexico)")
    dev.off()
    # pdf(file.path(out_dir, "Figure2_lorenz_curves.pdf"), width = 10, height = 7)
    # gridExtra::grid.arrange(
    #   fig2_plots[["Davao City"]], fig2_plots[["Nairobi"]], fig2_plots[["Mombasa"]],
    #   fig2_plots[["Cagayan de Oro"]], fig2_plots[["Mexico City"]],
    #   ncol = 3,
    #   top = "Lorenz Curves (Panel A: Davao | B: Nairobi | C: Mombasa | D: Cagayan | E: Mexico)")
    # dev.off()
  } else {
    ggsave(file.path(out_dir, "Figure2_lorenz_curves.png"), fig2_plots[["Davao City"]], width = 6, height = 5, dpi = 300)
    message("Install patchwork or gridExtra for full 2x2 Figure 2; saved Davao only")
  }
  message("Saved: Figure2_lorenz_curves.png/.pdf")
  # Figure 2 — 4-in-a-row version
  if (has_patchwork) {
    combined2_row <- p_with_leg + fig2_plots[["Nairobi"]] + fig2_plots[["Mombasa"]] +
      fig2_plots[["Cagayan de Oro"]] + fig2_plots[["Mexico City"]] +
      patchwork::plot_layout(ncol = 5, guides = "collect") &
      theme(legend.position = "bottom", legend.title = element_blank())
    combined2_row <- combined2_row +
      patchwork::plot_annotation(
        title = "Lorenz Curves (Structural Illustration)",
        subtitle = "Davao | Nairobi | Mombasa | Cagayan de Oro | Mexico City"
      ) & theme(
        plot.title = element_text(face = "bold", size = 12),
        plot.subtitle = element_text(colour = "gray40", size = 9)
      )
    ggsave(file.path(out_dir, "Figure2_lorenz_curves_row.png"), combined2_row, width = 16, height = 4, dpi = 300)
    # ggsave(file.path(out_dir, "Figure2_lorenz_curves_row.pdf"), combined2_row, width = 16, height = 4)
    message("Saved: Figure2_lorenz_curves_row.png/.pdf")
  }
}

# ---- Helper: build allocation residual map for one city ----
build_residual_map <- function(city, reg, crs_epsg) {
  path <- file.path(project_root, "outputs", reg, "02", "harmonised_with_residual.gpkg")
  if (!file.exists(path)) return(NULL)
  gdf <- st_read(path, quiet = TRUE)
  gdf <- gdf[!is.na(gdf$allocation_residual), ]
  if (nrow(gdf) == 0) return(NULL)
  v <- gdf$allocation_residual
  vlim <- max(abs(range(v, na.rm = TRUE)), 0.5)
  vlim <- pmin(vlim, 2)
  gdf_proj <- st_transform(gdf, crs_epsg)
  p <- ggplot(gdf_proj) +
    geom_sf(aes(fill = pmin(pmax(allocation_residual, -vlim), vlim)), colour = NA) +
    geom_sf(data = gdf_proj, fill = NA, colour = "gray85", linewidth = 0.15) +
    scale_fill_gradientn(
      colours = armyrose,
      values = seq(0, 1, length.out = 7),
      limits = c(-vlim, vlim), oob = scales::squish,
      name = expression(log(meta/wp))
    ) +
    coord_sf(
      crs = crs_epsg,
      datum = sf::st_crs(4326),
      label_graticule = "SW",
      label_axes = "SW"
    ) +
    labs(title = city) +
    theme_void() +
    theme(
      plot.title = element_text(face = "bold", hjust = 0.5, size = 11),
      legend.position = "bottom",
      legend.direction = "horizontal",
      legend.key.width = unit(1.2, "cm"),
      legend.key.height = unit(0.4, "cm"),
      panel.border = element_rect(fill = NA, colour = "gray30", linewidth = 0.8),
      axis.text = element_text(size = 7, colour = "gray30"),
      axis.ticks = element_line(colour = "gray50", linewidth = 0.3),
      axis.ticks.length = unit(0.1, "cm")
    )
  bbox <- st_bbox(gdf_proj)
  x_extent <- as.numeric(bbox["xmax"] - bbox["xmin"])
  y_extent <- as.numeric(bbox["ymax"] - bbox["ymin"])
  pad_frac <- 0.04
  scale_x0 <- as.numeric(bbox["xmin"]) + x_extent * pad_frac
  scale_y0 <- as.numeric(bbox["ymin"]) + y_extent * pad_frac
  scale_x1 <- scale_x0 + 10000
  p <- p +
    annotate("segment", x = scale_x0, xend = scale_x1, y = scale_y0, yend = scale_y0,
      colour = "gray30", linewidth = 0.8
    ) +
    annotate("text", x = (scale_x0 + scale_x1) / 2, y = scale_y0,
      label = "10 km", vjust = -0.8, size = 2.8, colour = "gray30")
  if (has_ggspatial) {
    p <- p +
      ggspatial::annotation_north_arrow(
        location = "tr",
        which_north = "true",
        height = unit(0.9, "cm"),
        width = unit(0.9, "cm"),
        style = ggspatial::north_arrow_orienteering
      )
  }
  p
}

# ---- FIGURE 4: Allocation Residual Maps (Davao + Mexico) ----
fig3_cities <- list("Davao City" = "PHI_DavaoCity", "Mexico City" = "MEX")
fig3_crs <- list("Davao City" = 32651, "Mexico City" = 32614)  # UTM 51N, 14N
fig3_list <- list()
for (city in names(fig3_cities)) {
  reg <- fig3_cities[[city]]
  p <- build_residual_map(city, reg, fig3_crs[[city]])
  if (!is.null(p)) fig3_list[[city]] <- p
}
if (length(fig3_list) >= 2) {
  if (has_patchwork) {
    combined3 <- fig3_list[["Davao City"]] + fig3_list[["Mexico City"]] +
      patchwork::plot_layout(ncol = 2, guides = "collect") &
      theme(legend.position = "bottom", legend.direction = "horizontal")
    combined3 <- combined3 +
      patchwork::plot_annotation(
        title = "Allocation Residual Maps",
        subtitle = "log(meta_share / worldpop_share) — Davao (strong divergence) vs Mexico (minimal)"
      ) & theme(
        plot.title = element_text(face = "bold", size = 12),
        plot.subtitle = element_text(colour = "gray40", size = 9)
      )
    ggsave(file.path(out_dir, "Figure3_residual_maps.png"), combined3, width = 10, height = 5, dpi = 300)
    # ggsave(file.path(out_dir, "Figure3_residual_maps.pdf"), combined3, width = 10, height = 5)
  } else if (requireNamespace("gridExtra", quietly = TRUE)) {
    png(file.path(out_dir, "Figure3_residual_maps.png"), width = 10, height = 5, units = "in", res = 300)
    gridExtra::grid.arrange(fig3_list[["Davao City"]], fig3_list[["Mexico City"]], ncol = 2,
      top = "Allocation Residual Maps (Davao | Mexico)")
    dev.off()
    # pdf(file.path(out_dir, "Figure3_residual_maps.pdf"), width = 10, height = 5)
    # gridExtra::grid.arrange(fig3_list[["Davao City"]], fig3_list[["Mexico City"]], ncol = 2,
    #   top = "Allocation Residual Maps (Davao | Mexico)")
    # dev.off()
  } else {
    ggsave(file.path(out_dir, "Figure3_residual_maps.png"), fig3_list[["Davao City"]], width = 6, height = 5, dpi = 300)
    message("Install patchwork or gridExtra for 2-panel Figure 3; saved Davao only")
  }
  message("Saved: Figure3_residual_maps.png/.pdf")
}

# ---- FIGURE 3b: Allocation Residual Maps (Nairobi, Mombasa, Cagayan de Oro) ----
fig3b_cities <- list("Nairobi" = "KEN_Nairobi", "Mombasa" = "KEN_Mombasa", "Cagayan de Oro" = "PHI_CagayandeOroCity")
fig3b_crs <- list("Nairobi" = 32737, "Mombasa" = 32737, "Cagayan de Oro" = 32651)  # UTM 37S Kenya, 51N Philippines
fig3b_list <- list()
for (city in names(fig3b_cities)) {
  reg <- fig3b_cities[[city]]
  p <- build_residual_map(city, reg, fig3b_crs[[city]])
  if (!is.null(p)) fig3b_list[[city]] <- p
}
if (length(fig3b_list) >= 2) {
  fig3b_order <- c("Nairobi", "Mombasa", "Cagayan de Oro")
  fig3b_plots <- fig3b_list[intersect(fig3b_order, names(fig3b_list))]
  n3b <- length(fig3b_plots)
  if (has_patchwork) {
    combined3b <- Reduce(`+`, fig3b_plots) +
      patchwork::plot_layout(ncol = n3b, guides = "collect") &
      theme(legend.position = "bottom", legend.direction = "horizontal")
    combined3b <- combined3b +
      patchwork::plot_annotation(
        title = "Allocation Residual Maps (Other Cities)",
        subtitle = "log(meta_share / worldpop_share) — Nairobi, Mombasa, Cagayan de Oro"
      ) & theme(
        plot.title = element_text(face = "bold", size = 12),
        plot.subtitle = element_text(colour = "gray40", size = 9)
      )
    ggsave(file.path(out_dir, "Figure3_residual_maps_other.png"), combined3b, width = 12, height = 4.5, dpi = 300)
    # ggsave(file.path(out_dir, "Figure3_residual_maps_other.pdf"), combined3b, width = 12, height = 4.5)
  } else if (requireNamespace("gridExtra", quietly = TRUE)) {
    png(file.path(out_dir, "Figure3_residual_maps_other.png"), width = 12, height = 4.5, units = "in", res = 300)
    do.call(gridExtra::grid.arrange, c(fig3b_plots, list(ncol = n3b, top = "Allocation Residual Maps (Nairobi | Mombasa | Cagayan de Oro)")))
    dev.off()
    # pdf(file.path(out_dir, "Figure3_residual_maps_other.pdf"), width = 12, height = 4.5)
    # do.call(gridExtra::grid.arrange, c(fig3b_plots, list(ncol = n3b, top = "Allocation Residual Maps (Nairobi | Mombasa | Cagayan de Oro)")))
    # dev.off()
  } else {
    ggsave(file.path(out_dir, "Figure3_residual_maps_other.png"), fig3b_plots[[1]], width = 6, height = 5, dpi = 300)
    message("Install patchwork or gridExtra for 3-panel Figure 3b; saved first panel only")
  }
  message("Saved: Figure3_residual_maps_other.png/.pdf")
}

# ---- Individual allocation residual maps (one file per city) ----
all_residual_maps <- c(fig3_list, fig3b_list)
for (city in names(all_residual_maps)) {
  fname <- gsub(" ", "_", city)
  ggsave(file.path(out_dir, paste0("Figure3_residual_map_", fname, ".png")),
    all_residual_maps[[city]], width = 6, height = 5, dpi = 300)
  # ggsave(file.path(out_dir, paste0("Figure3_residual_map_", fname, ".pdf")),
  #   all_residual_maps[[city]], width = 6, height = 5)
}
if (length(all_residual_maps) > 0) {
  message("Saved: Figure3_residual_map_{city}.png/.pdf for ", paste(names(all_residual_maps), collapse = ", "))
}

# ---- FIGURE 4: Poverty Effect (SEM tau forest plot) ----
p4 <- NULL
fig4_data <- lapply(names(regions), function(city) {
  reg <- regions[[city]]
  path <- file.path(project_root, "outputs", reg, "03c_spatial_regression", "Table_tau_comparison.csv")
  if (!file.exists(path)) return(NULL)
  d <- read.csv(path)
  sem <- d[grepl("SEM", d$Model), ]
  if (nrow(sem) == 0) return(NULL)
  data.frame(
    City = city,
    tau = sem$tau,
    SE = sem$SE,
    exp_tau = sem$exp_tau,
    CI_lo = sem$tau - 1.96 * sem$SE,
    CI_hi = sem$tau + 1.96 * sem$SE
  )
})
fig4_data <- bind_rows(Filter(Negate(is.null), fig4_data))
if (nrow(fig4_data) > 0) {
  city_order <- c("Davao City", "Nairobi", "Mombasa", "Cagayan de Oro", "Mexico City")
  fig4_data$City <- factor(fig4_data$City, levels = rev(city_order))
  p4 <- ggplot(fig4_data, aes(x = tau, y = City, colour = City)) +
    geom_vline(xintercept = 0, linetype = "dashed", colour = "gray50", linewidth = 0.5) +
    geom_errorbar(aes(xmin = CI_lo, xmax = CI_hi), height = 0.2, linewidth = 0.8, orientation = "y") +
    geom_point(size = 3.5, fill = "white", shape = 21, stroke = 1.2) +
    geom_text(aes(label = sprintf("exp(tau)==%.2f", exp_tau), x = CI_hi), hjust = -0.15, size = 2.8, colour = "gray30", parse = TRUE) +
    scale_colour_manual(values = c("Nairobi" = armyrose[1], "Mombasa" = armyrose[3], "Davao City" = armyrose[2], "Cagayan de Oro" = armyrose[6], "Mexico City" = armyrose[7]), guide = "none") +
    scale_x_continuous(expand = expansion(mult = c(0.15, 0.35))) +
    labs(
      title = "Poverty Effect (SEM tau Across Cities)",
      subtitle = "Point estimate +/- 95% CI.",
      x = "SEM tau (treatment effect)", y = NULL
    ) +
    theme_minimal(base_size = 11) +
    theme(
      plot.title = element_text(face = "bold", size = 12, hjust = 0),
      plot.subtitle = element_text(colour = "gray40", size = 9, hjust = 0),
      panel.grid.major.y = element_blank(),
      axis.ticks.y = element_line(colour = "gray70")
    )
  ggsave(file.path(out_dir, "Figure4_sem_forest.png"), p4, width = 7, height = 4, dpi = 300)
  # ggsave(file.path(out_dir, "Figure4_sem_forest.pdf"), p4, width = 7, height = 4)
  message("Saved: Figure4_sem_forest.png/.pdf")
}

# ---- FIGURE 5: Cross-city scatter Delta Gini vs Poverty tau ----
p5 <- NULL
tbl1_path <- file.path(out_dir, "Table1_cross_city_table.csv")
tbl2_path <- file.path(out_dir, "Table2_poverty_effect_spatially_corrected.csv")
if (file.exists(tbl1_path) && file.exists(tbl2_path)) {
  t1 <- read.csv(tbl1_path)
  t2 <- read.csv(tbl2_path)
  dg_col <- names(t1)[grepl("Gini", names(t1), ignore.case = TRUE)][1]
  tau_col <- names(t2)[grepl("^SEM", names(t2), ignore.case = TRUE)][1]
  if (is.na(tau_col)) tau_col <- names(t2)[3]
  if (length(dg_col) && dg_col %in% names(t1) && length(tau_col) && tau_col %in% names(t2)) {
    df_scatter <- t1 %>% select(City, Delta_Gini = all_of(dg_col)) %>%
      inner_join(t2 %>% select(City, tau = all_of(tau_col)), by = "City")
    df_scatter$Delta_Gini <- as.numeric(df_scatter$Delta_Gini)
    df_scatter$tau <- as.numeric(df_scatter$tau)
    df_scatter <- df_scatter[complete.cases(df_scatter), ]
    if (nrow(df_scatter) >= 2) {
      city_order <- c("Davao City", "Nairobi", "Mombasa", "Cagayan de Oro", "Mexico City")
      df_scatter$City <- factor(df_scatter$City, levels = city_order)
      df_scatter <- df_scatter %>% arrange(City)
      city_cols <- c("Davao City" = armyrose[2], "Nairobi" = armyrose[1], "Mombasa" = armyrose[3], "Cagayan de Oro" = armyrose[6], "Mexico City" = armyrose[7])
      p5 <- ggplot(df_scatter, aes(x = Delta_Gini, y = tau, colour = City, label = City)) +
        geom_hline(yintercept = 0, linetype = "dashed", colour = "gray50", linewidth = 0.5) +
        geom_vline(xintercept = 0, linetype = "dashed", colour = "gray50", linewidth = 0.5) +
        geom_point(size = 4, shape = 21, fill = "white", stroke = 1.2) +
        geom_text(nudge_y = -0.01, vjust = 1, hjust = 0.5, size = 3.2, show.legend = FALSE) +
        scale_colour_manual(values = city_cols, guide = "none") +
        scale_x_continuous(expand = expansion(mult = c(0.2, 0.35))) +
        scale_y_continuous(limits = c(-0.18, 0.08), expand = expansion(mult = c(0.05, 0.05))) +
        labs(
          title = "Cross-city: Delta Gini vs Poverty tau",
          subtitle = "Structural concentration vs poverty treatment effect.",
          x = "Delta Gini (Meta - WP)", y = "SEM tau (poverty effect)"
        ) +
        theme_minimal(base_size = 11) +
        theme(
          plot.title = element_text(face = "bold", size = 12, hjust = 0),
          plot.subtitle = element_text(colour = "gray40", size = 9, hjust = 0),
          panel.grid.minor = element_blank()
        )
      ggsave(file.path(out_dir, "Figure5_cross_city_scatter.png"), p5, width = 6, height = 5, dpi = 300)
      # ggsave(file.path(out_dir, "Figure5_cross_city_scatter.pdf"), p5, width = 6, height = 5)
      message("Saved: Figure5_cross_city_scatter.png/.pdf")
    }
  }
}

# ---- FIGURE 4+5 combined (left-right) ----
if (!is.null(p4) && !is.null(p5) && has_patchwork) {
  combined45 <- p4 + p5 + patchwork::plot_layout(ncol = 2, widths = c(1, 1))
  ggsave(file.path(out_dir, "Figure4_5_combined.png"), combined45, width = 12, height = 5, dpi = 300)
  # ggsave(file.path(out_dir, "Figure4_5_combined.pdf"), combined45, width = 12, height = 5)
  message("Saved: Figure4_5_combined.png/.pdf")
}

message("\nCross-city figures saved to: ", out_dir)
