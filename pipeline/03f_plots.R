#!/usr/bin/env Rscript
# 03f_plots.R — Nature-style forest plot for robustness specifications
#
# Reads: outputs/03f_robustness/Table_robustness_summary.csv
# Outputs: 03f_robustness_forest_r.png
#
# Usage: Rscript scripts/03f_plots.R

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
in_dir <- file.path(project_root, "outputs", "03f_robustness")
out_dir <- in_dir
# Allow -i to override (for multi-region: -i outputs/PHI/03f_robustness)
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

csv_path <- file.path(in_dir, "Table_robustness_summary.csv")

if (!file.exists(csv_path)) {
  stop("Run 03f_robustness.py first. Missing: ", csv_path)
}

df <- read.csv(csv_path, check.names = FALSE)
# Handle column names: Specification, τ (or tau), SE, p (or p_value)
tau_col <- names(df)[grepl("tau|τ", names(df), ignore.case = TRUE)][1]
se_col <- names(df)[grepl("^SE$|se", names(df))][1]
if (is.na(tau_col)) tau_col <- names(df)[2]
if (is.na(se_col)) se_col <- names(df)[3]

df <- df %>%
  mutate(
    Specification = factor(.data[[names(df)[1]]], levels = rev(.data[[names(df)[1]]])),
    tau = as.numeric(.data[[tau_col]]),
    se = as.numeric(.data[[se_col]]),
    ci_lo = tau - 1.96 * se,
    ci_hi = tau + 1.96 * se
  )

p <- ggplot(df, aes(x = tau, y = Specification, colour = Specification)) +
  geom_vline(xintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
  geom_errorbar(aes(xmin = ci_lo, xmax = ci_hi), width = 0.2, linewidth = 0.8, na.rm = TRUE, orientation = "y") +
  geom_point(size = 3, na.rm = TRUE) +
  scale_colour_brewer(palette = "Set2", guide = "none") +
  labs(
    x = expression("Treatment effect " * (tau)),
    y = NULL,
    title = "Sensitivity: τ across specifications",
    subtitle = "SEM-based estimates with 95% CI"
  ) +
  theme_nature() +
  scale_x_continuous(expand = expansion(mult = c(0.05, 0.05)))

ggsave(file.path(out_dir, "03f_robustness_forest_r.png"), p, width = 7, height = 4.5, dpi = 300, bg = "white")
message("Saved: ", file.path(out_dir, "03f_robustness_forest_r.png"))
