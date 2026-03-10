#!/usr/bin/env Rscript
# 03e_plots.R — Nature-style forest plot for causal estimators (τ comparison)
#
# Reads: outputs/03e_causal/03e_estimators.csv
# Outputs: 03e_estimators_forest_r.png
#
# Usage: Rscript scripts/03e_plots.R

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
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
      plot.margin = margin(10, 10, 10, 10)
    )
}

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
in_dir <- file.path(project_root, "outputs", "03e_causal")
out_dir <- in_dir
# Allow -i to override (for multi-region: -i outputs/PHI/03e_causal)
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

csv_path <- file.path(in_dir, "03e_estimators.csv")

if (!file.exists(csv_path)) {
  stop("Run 03e_causal.py first. Missing: ", csv_path)
}

df <- read.csv(csv_path)
df <- df %>%
  mutate(
    Estimator = factor(Estimator, levels = rev(Estimator)),
    se = ifelse(is.na(se_robust) | se_robust == 0, NA, se_robust),
    ci_lo = tau - 1.96 * se,
    ci_hi = tau + 1.96 * se
  )

p <- ggplot(df, aes(x = tau, y = Estimator, colour = Estimator)) +
  geom_vline(xintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
  geom_errorbar(aes(xmin = ci_lo, xmax = ci_hi), width = 0.2, linewidth = 0.8, na.rm = TRUE, orientation = "y") +
  geom_point(size = 3, na.rm = TRUE) +
  scale_colour_brewer(palette = "Set2", guide = "none") +
  labs(
    x = expression("Treatment effect " * (tau)),
    y = NULL,
    title = "Average treatment effect (ATE) across estimators",
    subtitle = "τ = E[Y(1) − Y(0)] with 95% CI"
  ) +
  theme_nature() +
  scale_x_continuous(expand = expansion(mult = c(0.05, 0.05)))

ggsave(file.path(out_dir, "03e_estimators_forest_r.png"), p, width = 7, height = 4, dpi = 300, bg = "white")
message("Saved: ", file.path(out_dir, "03e_estimators_forest_r.png"))
