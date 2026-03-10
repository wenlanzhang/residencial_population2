#!/usr/bin/env Rscript
# 03a_plots.R — Nature-style figures for regression diagnostics (residual distribution)
#
# Reads: outputs/03a_regression/03a_residual_for_plots.csv, 03a_residual_meta.csv
# Outputs: outputs/03a_regression/03a_residual_distribution_r.png
#
# Usage: Rscript scripts/03a_plots.R

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
})

# Nature-style theme: clean, minimal, publication-ready
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
in_dir <- file.path(project_root, "outputs", "03a_regression")
out_dir <- in_dir
# Allow -i to override (for multi-region: -i outputs/PHI/03a_regression)
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

res_path <- file.path(in_dir, "03a_residual_for_plots.csv")
meta_path <- file.path(in_dir, "03a_residual_meta.csv")

if (!file.exists(res_path)) {
  stop("Run 03a_regression.py first. Missing: ", res_path)
}

df <- read.csv(res_path)
dv_label <- "allocation_residual"
skew_val <- NA
if (file.exists(meta_path)) {
  meta <- read.csv(meta_path)
  if ("skew" %in% names(meta)) skew_val <- meta$skew[1]
  if ("dv_label" %in% names(meta) && nchar(trimws(meta$dv_label[1])) > 0) {
    dv_label <- trimws(meta$dv_label[1])
  }
}
if (is.na(skew_val) && requireNamespace("moments", quietly = TRUE)) {
  skew_val <- moments::skewness(df[[names(df)[1]]], na.rm = TRUE)
}

# Single figure: Histogram + KDE overlaid
subtitle <- if (!is.na(skew_val)) sprintf("Skewness = %.3f — OLS assumption check", skew_val) else "OLS assumption check"
dv_col <- names(df)[1]
p <- ggplot(df, aes(x = .data[[dv_col]])) +
  geom_histogram(aes(y = after_stat(density)), bins = 30, fill = "#4A90A4", colour = "white", linewidth = 0.3) +
  geom_density(colour = "#2C3E50", linewidth = 0.8, alpha = 0.7) +
  geom_vline(xintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
  labs(x = dv_label, y = "Density", title = "Distribution of allocation residual (DV)", subtitle = subtitle) +
  theme_nature() +
  scale_x_continuous(expand = c(0.02, 0)) +
  scale_y_continuous(expand = expansion(mult = c(0, 0.05)))

ggsave(file.path(out_dir, "03a_residual_distribution_r.png"), p, width = 6, height = 4, dpi = 300, bg = "white")
message("Saved: ", file.path(out_dir, "03a_residual_distribution_r.png"))
