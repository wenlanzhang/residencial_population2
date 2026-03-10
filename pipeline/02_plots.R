#!/usr/bin/env Rscript
# 02_plots.R — Nature-style figures for Meta vs WorldPop comparison
#
# Reads: outputs/02/harmonised_with_residual.gpkg
# Outputs: 02_density_histogram_r.png, 02_density_histogram_overlapped_r.png,
#          02_density_cdf_ks_r.png, 02_scatter_meta_vs_worldpop_r.png,
#          etc. (_r suffix to avoid overwriting Python figures)
#
# Usage: Rscript pipeline/02_plots.R

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
  library(tidyr)
})
if (!requireNamespace("hexbin", quietly = TRUE)) {
  stop("Package 'hexbin' required for hexbin scatter. Install with: install.packages(\"hexbin\")")
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

theme_nature_map <- function() {
  theme_void() +
    theme(
      plot.title = element_text(face = "bold", size = 12, hjust = 0.5),
      legend.title = element_text(face = "bold", size = 10),
      legend.text = element_text(size = 9),
      plot.margin = margin(10, 10, 10, 10)
    )
}

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
script_dir <- file.path(project_root, "pipeline")
source(file.path(script_dir, "region_config.R"), local = TRUE)

in_path <- file.path(project_root, "outputs", "02", "harmonised_with_residual.gpkg")
out_dir <- file.path(project_root, "outputs", "02")
region_arg <- NULL
args <- commandArgs(trailingOnly = TRUE)
i <- 1
while (i <= length(args)) {
  if (args[i] == "-i" && i < length(args)) {
    in_path <- args[i + 1]
    out_dir <- dirname(in_path)
    i <- i + 2
  } else if (args[i] == "--region" && i < length(args)) {
    region_arg <- args[i + 1]
    i <- i + 2
  } else {
    i <- i + 1
  }
}
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

if (!file.exists(in_path)) {
  stop("Run 02_compare_meta_worldpop.py first. Missing: ", in_path)
}

gdf <- st_read(in_path, quiet = TRUE)
map_bbox <- get_map_bbox_for_plot(region_arg, in_path, gdf)
gdf_plot <- clip_gdf_to_bbox(gdf, map_bbox)
coord_map <- coord_from_bbox(map_bbox)
add_coord <- function(p, g) p + coord_map
gdf <- gdf %>%
  filter(worldpop_share > 0, meta_share > 0, !is.na(worldpop_share), !is.na(meta_share))

# Ensure area_km2 exists (compute from geometry if missing)
if (!"area_km2" %in% names(gdf)) {
  gdf_proj <- st_transform(gdf, "EPSG:32737")
  gdf$area_km2 <- as.numeric(st_area(gdf_proj)) / 1e6
}
gdf$area_km2 <- pmax(gdf$area_km2, 1e-6)
gdf$density_wp <- gdf$worldpop_count / gdf$area_km2
gdf$density_meta <- gdf$meta_baseline / gdf$area_km2
gdf$log_wp <- log(gdf$worldpop_share + 1e-10)
gdf$log_meta <- log(gdf$meta_share + 1e-10)

wp_s <- gdf$worldpop_share
meta_s <- gdf$meta_share
dens_wp <- gdf$density_wp[gdf$density_wp > 0]
dens_meta <- gdf$density_meta[gdf$density_meta > 0]
log_wp <- gdf$log_wp
log_meta <- gdf$log_meta

# Lorenz curve helper
lorenz_curve <- function(x) {
  x <- sort(x[!is.na(x) & x >= 0])
  if (length(x) == 0) return(list(pop = 0, val = 0))
  n <- length(x)
  cumx <- cumsum(x)
  list(pop = c(0, (1:n) / n), val = c(0, cumx / cumx[n]))
}

# 1. Density histogram (side-by-side)
skew_fn <- if (requireNamespace("moments", quietly = TRUE)) moments::skewness else function(x, ...) 0
use_log <- abs(skew_fn(dens_wp, na.rm = TRUE)) > 1 | abs(skew_fn(dens_meta, na.rm = TRUE)) > 1

df_dens <- bind_rows(
  tibble(density = dens_wp, source = "WorldPop"),
  tibble(density = dens_meta, source = "Meta")
) %>% filter(density > 0)
if (use_log) df_dens <- df_dens %>% mutate(density = log10(density + 1))

p1 <- ggplot(df_dens, aes(x = density, fill = source)) +
  geom_histogram(aes(y = after_stat(density)), bins = 40, alpha = 0.7, position = "identity") +
  scale_fill_manual(values = c(WorldPop = "#4A90A4", Meta = "#C75D4E"), name = "Source") +
  labs(
    x = if (use_log) "log₁₀(density + 1) [per km²]" else "Population density [per km²]",
    y = "Density",
    title = "Population density per grid cell"
  ) +
  facet_wrap(~source, ncol = 2) +
  theme_nature() +
  theme(legend.position = "none")
ggsave(file.path(out_dir, "02_density_histogram_r.png"), p1, width = 8, height = 4, dpi = 300, bg = "white")
message("Saved: 02_density_histogram_r.png")

# 2. Density histogram overlapped
df_dens2 <- bind_rows(
  tibble(x = if (use_log) log10(dens_wp + 1) else dens_wp, source = "WorldPop"),
  tibble(x = if (use_log) log10(dens_meta + 1) else dens_meta, source = "Meta")
) %>% filter(!is.na(x), is.finite(x))
p2 <- ggplot(df_dens2, aes(x = x, fill = source)) +
  geom_histogram(aes(y = after_stat(density)), bins = 40, alpha = 0.6, position = "identity") +
  geom_density(aes(colour = source), linewidth = 0.8, fill = NA) +
  scale_fill_manual(values = c(WorldPop = "#4A90A4", Meta = "#C75D4E"), name = "Source") +
  scale_colour_manual(values = c(WorldPop = "#2C3E50", Meta = "#8B3A3A"), guide = "none") +
  labs(
    x = if (use_log) "log₁₀(density + 1) [per km²]" else "Population density [per km²]",
    y = "Density",
    title = "Population density per grid cell (overlapped)"
  ) +
  theme_nature()
ggsave(file.path(out_dir, "02_density_histogram_overlapped_r.png"), p2, width = 8, height = 4, dpi = 300, bg = "white")
message("Saved: 02_density_histogram_overlapped_r.png")

# 3. Scatter: log(meta_share) vs log(worldpop_share)
df_scatter <- tibble(log_meta = log_meta, log_wp = log_wp)
fit <- lm(log_wp ~ log_meta, data = df_scatter)
slope <- coef(fit)[2]
r_pearson <- cor(log_meta, log_wp)
r_spearman <- cor(log_meta, log_wp, method = "spearman")
p3 <- ggplot(df_scatter, aes(x = log_meta, y = log_wp)) +
  geom_hex(bins = 25) +
  scale_fill_gradient(low = "#E8F4F8", high = "#2166AC", name = "Count") +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed", colour = "grey30", linewidth = 0.6) +
  geom_abline(slope = slope, intercept = coef(fit)[1], colour = "#C75D4E", linewidth = 0.8) +
  annotate("label", x = min(log_meta, na.rm = TRUE), y = max(log_wp, na.rm = TRUE),
           label = sprintf("Slope = %.3f\nPearson r = %.3f", slope, r_pearson),
           hjust = 0, vjust = 1, fill = "white", alpha = 0.9) +
  coord_fixed(ratio = 0.75) +  # ratio < 1 makes plot area wider (more horizontal)
  labs(
    x = "log(meta_share)",
    y = "log(worldpop_share)",
    title = "Spatial agreement: log shares"
  ) +
  theme_nature()
ggsave(file.path(out_dir, "02_scatter_meta_vs_worldpop_r.png"), p3, width = 7, height = 6, dpi = 300, bg = "white")
message("Saved: 02_scatter_meta_vs_worldpop_r.png")

# 4. Distribution histogram + KDE (normalized shares)
wp_norm <- (wp_s - min(wp_s, na.rm = TRUE)) / (max(wp_s, na.rm = TRUE) - min(wp_s, na.rm = TRUE) + 1e-10)
meta_norm <- (meta_s - min(meta_s, na.rm = TRUE)) / (max(meta_s, na.rm = TRUE) - min(meta_s, na.rm = TRUE) + 1e-10)
df_dist <- bind_rows(
  tibble(value = wp_norm, source = "WorldPop"),
  tibble(value = meta_norm, source = "Meta")
)
p4a <- ggplot(df_dist, aes(x = value, fill = source)) +
  geom_histogram(aes(y = after_stat(density)), bins = 30, alpha = 0.7, position = "identity") +
  scale_fill_manual(values = c(WorldPop = "#4A90A4", Meta = "#C75D4E"), name = "Source") +
  labs(x = "Normalized value", y = "Density", title = "Histograms (normalized)") +
  theme_nature()
p4b <- ggplot(df_dist, aes(x = value, colour = source)) +
  geom_density(linewidth = 0.8) +
  scale_colour_manual(values = c(WorldPop = "#4A90A4", Meta = "#C75D4E"), name = "Source") +
  labs(x = "Normalized value", y = "Density", title = "Kernel density") +
  theme_nature()
if (requireNamespace("patchwork", quietly = TRUE)) {
  p4 <- p4a + p4b + patchwork::plot_annotation(title = "Distribution similarity: Meta vs WorldPop shares")
} else if (requireNamespace("cowplot", quietly = TRUE)) {
  p4 <- cowplot::plot_grid(p4a, p4b, ncol = 2, labels = c("a", "b"))
} else {
  p4 <- p4a
}
ggsave(file.path(out_dir, "02_distribution_histogram_kde_r.png"), p4, width = 8, height = 4, dpi = 300, bg = "white")
message("Saved: 02_distribution_histogram_kde_r.png")

# 5. Lorenz curves
l_wp <- lorenz_curve(wp_s)
l_meta <- lorenz_curve(meta_s)
df_lorenz <- bind_rows(
  tibble(pop = l_wp$pop, val = l_wp$val, source = "WorldPop"),
  tibble(pop = l_meta$pop, val = l_meta$val, source = "Meta")
)
p5 <- ggplot(df_lorenz, aes(x = pop, y = val, colour = source)) +
  geom_line(linewidth = 0.8) +
  geom_abline(slope = 1, intercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
  scale_colour_manual(values = c(WorldPop = "#4A90A4", Meta = "#C75D4E"), name = "Source") +
  coord_fixed(xlim = c(0, 1), ylim = c(0, 1)) +
  labs(
    x = "Cumulative share of quadkeys",
    y = "Cumulative share of allocation",
    title = "Lorenz curves (spatial allocation inequality)"
  ) +
  theme_nature()
ggsave(file.path(out_dir, "02_lorenz_curves_r.png"), p5, width = 6, height = 6, dpi = 300, bg = "white")
message("Saved: 02_lorenz_curves_r.png")

# 6. Allocation residual map (zoomed when Philippines)
resid_col <- if ("allocation_residual" %in% names(gdf)) "allocation_residual" else "allocation_log_ratio"
if (resid_col %in% names(gdf)) {
  v <- gdf_plot[[resid_col]]
  lim <- max(abs(min(v, na.rm = TRUE)), abs(max(v, na.rm = TRUE)), 1e-6)
  p6 <- ggplot(gdf_plot) +
    geom_sf(aes(fill = .data[[resid_col]]), colour = "white", linewidth = 0.15) +
    scale_fill_gradient2(low = "#2166AC", mid = "white", high = "#B2182B", midpoint = 0,
                         limits = c(-lim, lim), name = "Residual") +
    labs(title = "Allocation residual: log(meta_share / worldpop_share)") +
    theme_nature_map()
  p6 <- add_coord(p6, gdf)
  ggsave(file.path(out_dir, "02_allocation_log_ratio_r.png"), p6, width = 8, height = 8, dpi = 300, bg = "white")
  message("Saved: 02_allocation_log_ratio_r.png")
}

# 7. Agreement typology (median) — zoomed when Philippines
typ_labels <- c("1" = "HH", "2" = "LH", "3" = "LL", "4" = "HL")
typ_colors <- c("HH" = "#d73027", "LH" = "#fc8d59", "LL" = "#91cf60", "HL" = "#1a9850")
if ("agreement_typology_median" %in% names(gdf)) {
  gdf_plot$typ_med <- factor(typ_labels[as.character(gdf_plot$agreement_typology_median)], levels = c("HH", "LH", "LL", "HL"))
  p7 <- ggplot(gdf_plot) +
    geom_sf(aes(fill = typ_med), colour = "white", linewidth = 0.15) +
    scale_fill_manual(values = typ_colors, name = "Typology", na.value = "grey90", drop = FALSE) +
    labs(title = "Agreement typology (median split)") +
    theme_nature_map()
  p7 <- add_coord(p7, gdf)
  ggsave(file.path(out_dir, "02_agreement_typology_median_r.png"), p7, width = 8, height = 8, dpi = 300, bg = "white")
  message("Saved: 02_agreement_typology_median_r.png")
}

# 8. Agreement typology (quartile) — zoomed when Philippines
typ_q_labels <- c("0" = "other", "1" = "HH", "2" = "LH", "3" = "LL", "4" = "HL")
typ_q_colors <- c("HH" = "#d73027", "LH" = "#fc8d59", "LL" = "#91cf60", "HL" = "#1a9850", "other" = "#e0e0e0")
if ("agreement_typology_quartile" %in% names(gdf)) {
  gdf_plot$typ_q <- factor(typ_q_labels[as.character(gdf_plot$agreement_typology_quartile)], levels = c("HH", "LH", "LL", "HL", "other"))
  p8 <- ggplot(gdf_plot) +
    geom_sf(aes(fill = typ_q), colour = "white", linewidth = 0.15) +
    scale_fill_manual(values = typ_q_colors, name = "Typology", na.value = "grey90", drop = FALSE) +
    labs(title = "Agreement typology (quartile split)") +
    theme_nature_map()
  p8 <- add_coord(p8, gdf)
  ggsave(file.path(out_dir, "02_agreement_typology_quartile_r.png"), p8, width = 8, height = 8, dpi = 300, bg = "white")
  message("Saved: 02_agreement_typology_quartile_r.png")
}

# 9. LISA maps (if columns exist) — zoomed when Philippines
lisa_labels <- c("0" = "ns", "1" = "HH", "2" = "LH", "3" = "LL", "4" = "HL")
lisa_colors <- c("ns" = "#f0f0f0", "HH" = "#d73027", "LH" = "#fc8d59", "LL" = "#4575b4", "HL" = "#91bfdb")
if ("lisa_sig_wp" %in% names(gdf)) {
  gdf_plot$lisa_wp <- factor(lisa_labels[as.character(gdf_plot$lisa_sig_wp)], levels = c("HH", "LH", "LL", "HL", "ns"))
  p9a <- ggplot(gdf_plot) +
    geom_sf(aes(fill = lisa_wp), colour = "white", linewidth = 0.15) +
    scale_fill_manual(values = lisa_colors, name = "LISA", na.value = "grey90", drop = FALSE) +
    labs(title = "LISA — WorldPop") +
    theme_nature_map()
  p9a <- add_coord(p9a, gdf)
  ggsave(file.path(out_dir, "02_lisa_worldpop_r.png"), p9a, width = 8, height = 8, dpi = 300, bg = "white")
  message("Saved: 02_lisa_worldpop_r.png")
}
if ("lisa_sig_meta" %in% names(gdf)) {
  gdf_plot$lisa_meta <- factor(lisa_labels[as.character(gdf_plot$lisa_sig_meta)], levels = c("HH", "LH", "LL", "HL", "ns"))
  p9b <- ggplot(gdf_plot) +
    geom_sf(aes(fill = lisa_meta), colour = "white", linewidth = 0.15) +
    scale_fill_manual(values = lisa_colors, name = "LISA", na.value = "grey90", drop = FALSE) +
    labs(title = "LISA — Meta") +
    theme_nature_map()
  p9b <- add_coord(p9b, gdf)
  ggsave(file.path(out_dir, "02_lisa_meta_r.png"), p9b, width = 8, height = 8, dpi = 300, bg = "white")
  message("Saved: 02_lisa_meta_r.png")
}

# 10. Hotspot overlap map — zoomed when Philippines
overlap_labels <- c("-1" = "Both cold", "0" = "Other", "1" = "Both hot", "2" = "WP only", "3" = "Meta only")
overlap_colors <- c("Both cold" = "#4575b4", "Other" = "#f0f0f0", "Both hot" = "#d73027", "WP only" = "#fc8d59", "Meta only" = "#998ec3")
if ("hotspot_overlap" %in% names(gdf)) {
  gdf_plot$hotspot <- factor(overlap_labels[as.character(gdf_plot$hotspot_overlap)], levels = c("Both hot", "Both cold", "WP only", "Meta only", "Other"))
  p10 <- ggplot(gdf_plot) +
    geom_sf(aes(fill = hotspot), colour = "white", linewidth = 0.15) +
    scale_fill_manual(values = overlap_colors, name = "Hotspot", na.value = "grey90", drop = FALSE) +
    labs(title = "Hotspot overlap (Getis-Ord Gi*)") +
    theme_nature_map()
  p10 <- add_coord(p10, gdf)
  ggsave(file.path(out_dir, "02_hotspot_overlap_map_r.png"), p10, width = 8, height = 8, dpi = 300, bg = "white")
  message("Saved: 02_hotspot_overlap_map_r.png")
}

# 11. CDF/KS concentration curves
dens_wp_valid <- dens_wp[!is.na(dens_wp) & dens_wp > 0]
dens_meta_valid <- dens_meta[!is.na(dens_meta) & dens_meta > 0]
dens_wp_prob <- dens_wp_valid / sum(dens_wp_valid)
dens_meta_prob <- dens_meta_valid / sum(dens_meta_valid)
x_wp_log <- log10(dens_wp_valid + 1)
x_meta_log <- log10(dens_meta_valid + 1)
x_wp_log_p <- (x_wp_log + 1e-10) / sum(x_wp_log + 1e-10)
x_meta_log_p <- (x_meta_log + 1e-10) / sum(x_meta_log + 1e-10)
ks_lin <- ks.test(dens_wp_prob, dens_meta_prob)
ks_log <- ks.test(x_wp_log_p, x_meta_log_p)

concentration_curve <- function(x, w) {
  ord <- order(x)
  x_s <- x[ord]
  w_s <- w[ord]
  cum <- cumsum(w_s)
  list(x = x_s, y = cum / cum[length(cum)])
}
cc_wp_lin <- concentration_curve(dens_wp_valid, dens_wp_prob)
cc_meta_lin <- concentration_curve(dens_meta_valid, dens_meta_prob)
cc_wp_log <- concentration_curve(x_wp_log, x_wp_log_p)
cc_meta_log <- concentration_curve(x_meta_log, x_meta_log_p)
df_cc_lin <- bind_rows(
  tibble(x = cc_wp_lin$x, y = cc_wp_lin$y, source = "WorldPop", panel = "Linear"),
  tibble(x = cc_meta_lin$x, y = cc_meta_lin$y, source = "Meta", panel = "Linear")
)
df_cc_log <- bind_rows(
  tibble(x = cc_wp_log$x, y = cc_wp_log$y, source = "WorldPop", panel = "Log"),
  tibble(x = cc_meta_log$x, y = cc_meta_log$y, source = "Meta", panel = "Log")
)
df_cc <- bind_rows(df_cc_lin, df_cc_log)
p11 <- ggplot(df_cc, aes(x = x, y = y, colour = source)) +
  geom_line(linewidth = 0.8) +
  scale_colour_manual(values = c(WorldPop = "#4A90A4", Meta = "#C75D4E"), name = "Source") +
  facet_wrap(~panel, scales = "free_x", ncol = 2) +
  labs(
    x = "Population density",
    y = "Cumulative share of population",
    title = "Concentration curves: WorldPop vs Meta (Kolmogorov–Smirnov)"
  ) +
  theme_nature() +
  scale_y_continuous(limits = c(0, 1))
ggsave(file.path(out_dir, "02_density_cdf_ks_r.png"), p11, width = 10, height = 4, dpi = 300, bg = "white")
message("Saved: 02_density_cdf_ks_r.png")

message("02_plots.R complete.")
