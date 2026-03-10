#!/usr/bin/env Rscript
# 03b_plots.R — Nature-style figures for stratified analysis
#
# Reads: outputs/03b_stratified/03b_marginal_effects_for_plots.csv,
#        03b_strata_for_plots.csv, Table4_gini_by_quintile.csv
# Outputs: marginal_effects_poverty_r.png, residual_by_poverty_strata_r.png,
#          gini_by_poverty_quintile_r.png
#
# Usage: Rscript scripts/03b_plots.R

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(tidyr)
})

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
      strip.text = element_text(face = "bold", size = rel(0.95)),
      legend.title = element_text(face = "bold", size = rel(0.9)),
      legend.text = element_text(size = rel(0.85)),
      plot.margin = margin(10, 10, 10, 10)
    )
}

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
in_dir <- file.path(project_root, "outputs", "03b_stratified")
out_dir <- in_dir
# Allow -i to override (for multi-region: -i outputs/PHI/03b_stratified)
args <- commandArgs(trailingOnly = TRUE)
for (i in seq_along(args)) {
  if (args[i] == "-i" && i < length(args)) {
    in_dir <- args[i + 1]
    out_dir <- if (dir.exists(in_dir)) in_dir else dirname(in_dir)
    in_dir <- if (dir.exists(in_dir)) in_dir else dirname(in_dir)
    break
  }
}
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)

# 1. Marginal effects (poverty × residual at median density)
marg_path <- file.path(in_dir, "03b_marginal_effects_for_plots.csv")
if (file.exists(marg_path)) {
  marg <- read.csv(marg_path)
  p_marg <- ggplot(marg, aes(x = poverty, y = pred)) +
    geom_ribbon(aes(ymin = ci_lo, ymax = ci_hi), fill = "#4A90A4", alpha = 0.25) +
    geom_line(colour = "#2C3E50", linewidth = 1) +
    geom_hline(yintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
    labs(
      x = "Poverty (MPI proportion)",
      y = "Predicted residual",
      title = "Marginal effect of poverty on allocation residual",
      subtitle = "At median population density (95% CI)"
    ) +
    theme_nature() +
    scale_x_continuous(expand = c(0.02, 0))
  ggsave(file.path(out_dir, "marginal_effects_poverty_r.png"), p_marg, width = 6, height = 4, dpi = 300, bg = "white")
  message("Saved: ", file.path(out_dir, "marginal_effects_poverty_r.png"))
}

# 2. Boxplot: residual by poverty stratum
strata_path <- file.path(in_dir, "03b_strata_for_plots.csv")
if (file.exists(strata_path)) {
  strata <- read.csv(strata_path)
  strata$poverty_strata <- factor(strata$poverty_strata,
    levels = c("Low (bottom 25%)", "Medium", "High (top 25%)")
  )
  resid_col <- if ("allocation_residual" %in% names(strata)) "allocation_residual" else "allocation_log_ratio"
  p_box <- ggplot(strata, aes(x = poverty_strata, y = .data[[resid_col]], fill = poverty_strata)) +
    geom_boxplot(outlier.size = 1, outlier.alpha = 0.5) +
    geom_hline(yintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
    scale_fill_manual(values = c("#5D8A66", "#4A90A4", "#C75D4E"), guide = "none") +
    labs(
      x = "Poverty stratum",
      y = "Allocation residual: log(meta_share / worldpop_share)",
      title = "Allocation residual by poverty stratum"
    ) +
    theme_nature() +
    theme(axis.text.x = element_text(angle = 15, hjust = 1))
  ggsave(file.path(out_dir, "residual_by_poverty_strata_r.png"), p_box, width = 6, height = 4, dpi = 300, bg = "white")
  message("Saved: ", file.path(out_dir, "residual_by_poverty_strata_r.png"))
}

# 3. Gini by poverty quintile (grouped bar)
gini_path <- file.path(in_dir, "Table4_gini_by_quintile.csv")
if (file.exists(gini_path)) {
  gini <- read.csv(gini_path, check.names = FALSE)
  nm <- names(gini)
  gini_long <- gini %>%
    mutate(
      quintile = .data[[nm[1]]],
      WorldPop = as.numeric(as.character(.data[[nm[2]]])),
      Meta = as.numeric(as.character(.data[[nm[3]]]))
    ) %>%
    select(quintile, WorldPop, Meta) %>%
    tidyr::pivot_longer(cols = c(WorldPop, Meta), names_to = "Source", values_to = "Gini")
  p_gini <- ggplot(gini_long, aes(x = quintile, y = Gini, fill = Source)) +
    geom_col(position = position_dodge(width = 0.8), width = 0.7) +
    scale_fill_manual(values = c(WorldPop = "#4A90A4", Meta = "#C75D4E"), name = "Source") +
    labs(
      x = "Poverty quintile",
      y = "Gini coefficient",
      title = "Spatial allocation inequality by poverty quintile"
    ) +
    theme_nature() +
    theme(axis.text.x = element_text(angle = 15, hjust = 1))
  ggsave(file.path(out_dir, "gini_by_poverty_quintile_r.png"), p_gini, width = 7, height = 4, dpi = 300, bg = "white")
  message("Saved: ", file.path(out_dir, "gini_by_poverty_quintile_r.png"))
}
