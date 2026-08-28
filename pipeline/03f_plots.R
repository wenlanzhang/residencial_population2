#!/usr/bin/env Rscript
# 03f_plots.R — Nature-style forest plot for robustness specifications
#
# Reads: outputs/03f_robustness/Table_robustness_summary.csv
#        outputs/03f_robustness/Table_meta_count_sensitivity.csv
#        outputs/03f_robustness/meta_count_cells.csv
#        outputs/03f_robustness/Table_meta_count_censoring_sensitivity.csv
# Outputs: 03f_robustness_forest_r.png
#          03f_meta_count_sensitivity_r.png
#          03f_meta_count_residual_by_poverty_r.png
#          03f_meta_censoring_sensitivity_r.png
#
# Usage: Rscript pipeline/03f_plots.R

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
script_dir <- file.path(project_root, "pipeline")
source(file.path(script_dir, "region_config.R"), local = TRUE)
in_dir <- file.path(project_root, "outputs", "03f_robustness")
out_dir <- in_dir
region_arg <- NULL
o_arg <- NULL
footprint_arg <- NULL
args <- commandArgs(trailingOnly = TRUE)
i <- 1
while (i <= length(args)) {
  if (args[i] == "-i" && i < length(args)) {
    in_dir <- args[i + 1]
    in_dir <- if (dir.exists(in_dir)) in_dir else dirname(in_dir)
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
out_dir <- resolve_plot_out_dir(region_arg, in_dir, "03f_robustness", o_arg, footprint_arg)
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

# ---------------------------------------------------------------------------
# Meta low-count / disclosure-threshold sensitivity
# ---------------------------------------------------------------------------
sens_path <- file.path(in_dir, "Table_meta_count_sensitivity.csv")
if (!file.exists(sens_path)) {
  message("Skipping meta-count plot (missing ", sens_path, ")")
} else {

sens <- read.csv(sens_path, check.names = FALSE)
need <- c("min_meta", "N", "tau")
missing <- setdiff(need, names(sens))
if (length(missing) > 0) {
  stop("Table_meta_count_sensitivity.csv missing columns: ", paste(missing, collapse = ", "))
}

if (!("CI_low" %in% names(sens) && "CI_high" %in% names(sens))) {
  se_col <- if ("se" %in% names(sens)) "se" else if ("SE" %in% names(sens)) "SE" else NA
  if (is.na(se_col)) stop("Need CI_low/CI_high or se in Table_meta_count_sensitivity.csv")
  sens$CI_low <- sens$tau - 1.96 * sens[[se_col]]
  sens$CI_high <- sens$tau + 1.96 * sens[[se_col]]
}

order_keys <- c("baseline", "20", "30", "50")
axis_labs <- c("Baseline", "\u2265 20", "\u2265 30", "\u2265 50")
sens$min_meta <- as.character(sens$min_meta)
sens <- sens[sens$min_meta %in% order_keys, , drop = FALSE]
sens$x_pos <- match(sens$min_meta, order_keys)
sens <- sens[order(sens$x_pos), , drop = FALSE]
sens$tick <- paste0(axis_labs[sens$x_pos], "\nN = ", format(sens$N, big.mark = ",", trim = TRUE))

p_meta <- ggplot(sens, aes(x = x_pos, y = tau)) +
  geom_hline(yintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
  geom_errorbar(aes(ymin = CI_low, ymax = CI_high), width = 0.12, linewidth = 0.8, na.rm = TRUE) +
  geom_point(size = 3.2, colour = "#1b4f72", na.rm = TRUE) +
  scale_x_continuous(breaks = sens$x_pos, labels = sens$tick) +
  labs(
    x = "Minimum Meta count",
    y = expression("SEM " * tau),
    title = "Meta low-count sensitivity",
    subtitle = "T frozen at full-sample poverty Q75; R = allocation residual (Step 02)"
  ) +
  theme_nature() +
  scale_y_continuous(expand = expansion(mult = c(0.12, 0.12)))

ggsave(
  file.path(out_dir, "03f_meta_count_sensitivity_r.png"),
  p_meta, width = 6.5, height = 4.2, dpi = 300, bg = "white"
)
message("Saved: ", file.path(out_dir, "03f_meta_count_sensitivity_r.png"))
}

# ---------------------------------------------------------------------------
# Allocation discrepancy by Meta count and (frozen) deprivation
# ---------------------------------------------------------------------------
cells_path <- file.path(in_dir, "meta_count_cells.csv")
if (!file.exists(cells_path)) {
  message("Skipping residual-by-count plot (missing ", cells_path, ")")
} else {
  cells <- read.csv(cells_path, check.names = FALSE)
  need_c <- c("meta_baseline", "allocation_residual", "high_deprivation")
  miss_c <- setdiff(need_c, names(cells))
  if (length(miss_c) > 0) {
    stop("meta_count_cells.csv missing columns: ", paste(miss_c, collapse = ", "))
  }
  cells <- cells %>%
    filter(is.finite(meta_baseline), is.finite(allocation_residual)) %>%
    mutate(
      log_meta = log(pmax(meta_baseline, 0) + 1),
      depr = factor(
        ifelse(high_deprivation == 1, "High-deprivation quartile", "Other cells"),
        levels = c("High-deprivation quartile", "Other cells")
      )
    )
  n_ok <- nrow(cells)
  smooth_method <- if (n_ok >= 40) "loess" else "lm"
  v_x <- log(c(20, 30, 50) + 1)
  p_cells <- ggplot(cells, aes(x = log_meta, y = allocation_residual, colour = depr, fill = depr)) +
    geom_vline(xintercept = v_x, colour = "grey70", linewidth = 0.35, linetype = "dashed") +
    geom_hline(yintercept = 0, colour = "grey40", linewidth = 0.35, linetype = "dotted") +
    geom_point(alpha = 0.35, size = 1.15, stroke = 0, na.rm = TRUE) +
    geom_smooth(
      method = smooth_method, formula = y ~ x, se = TRUE, linewidth = 0.95,
      alpha = 0.18, span = 0.85, na.rm = TRUE
    ) +
    scale_colour_manual(values = c("High-deprivation quartile" = "#8B1E3F", "Other cells" = "#4C6A7A")) +
    scale_fill_manual(values = c("High-deprivation quartile" = "#8B1E3F", "Other cells" = "#4C6A7A")) +
    annotate("text", x = v_x, y = Inf, label = c("20", "30", "50"),
             vjust = 1.4, size = 2.8, colour = "grey40") +
    labs(
      x = expression(log(Meta + 1)),
      y = expression(R[i] == log(M[i] / W[i])),
      colour = NULL,
      fill = NULL,
      title = "Allocation discrepancy by Meta count and deprivation",
      subtitle = "High-deprivation status frozen at full-sample Q75"
    ) +
    theme_nature() +
    theme(
      legend.position = "bottom",
      legend.justification = "left",
      plot.margin = margin(10, 12, 10, 10)
    ) +
    scale_x_continuous(expand = expansion(mult = c(0.02, 0.04))) +
    scale_y_continuous(expand = expansion(mult = c(0.08, 0.14)))
  ggsave(
    file.path(out_dir, "03f_meta_count_residual_by_poverty_r.png"),
    p_cells, width = 6.8, height = 4.6, dpi = 300, bg = "white"
  )
  message("Saved: ", file.path(out_dir, "03f_meta_count_residual_by_poverty_r.png"))
}

# ---------------------------------------------------------------------------
# Missing-cell privacy-censoring sensitivity (03f-D)
# ---------------------------------------------------------------------------
cens_path <- file.path(in_dir, "Table_meta_count_censoring_sensitivity.csv")
if (!file.exists(cens_path)) {
  message("Skipping censoring plot (missing ", cens_path, ")")
} else {

cens <- read.csv(cens_path, check.names = FALSE)
need_d <- c("scenario", "N", "tau")
miss_d <- setdiff(need_d, names(cens))
if (length(miss_d) > 0) {
  stop("Table_meta_count_censoring_sensitivity.csv missing columns: ", paste(miss_d, collapse = ", "))
}
if (!("CI_low" %in% names(cens) && "CI_high" %in% names(cens))) {
  se_col <- if ("se" %in% names(cens)) "se" else if ("SE" %in% names(cens)) "SE" else NA
  if (is.na(se_col)) stop("Need CI_low/CI_high or se in Table_meta_count_censoring_sensitivity.csv")
  cens$CI_low <- cens$tau - 1.96 * cens[[se_col]]
  cens$CI_high <- cens$tau + 1.96 * cens[[se_col]]
}

order_d <- c("Original", "Low censored", "Mid censored", "Max censored")
cens$scenario <- as.character(cens$scenario)
cens <- cens[cens$scenario %in% order_d, , drop = FALSE]
cens$x_pos <- match(cens$scenario, order_d)
cens <- cens[order(cens$x_pos), , drop = FALSE]
assump <- if ("assumption" %in% names(cens)) as.character(cens$assumption) else cens$scenario
cens$tick <- paste0(cens$scenario, "\n", assump, "\nN = ", format(cens$N, big.mark = ",", trim = TRUE))

p_cens <- ggplot(cens, aes(x = x_pos, y = tau)) +
  geom_hline(yintercept = 0, linetype = "dashed", colour = "grey40", linewidth = 0.4) +
  geom_errorbar(aes(ymin = CI_low, ymax = CI_high), width = 0.12, linewidth = 0.8, na.rm = TRUE) +
  geom_point(size = 3.2, colour = "#1b4f72", na.rm = TRUE) +
  scale_x_continuous(breaks = cens$x_pos, labels = cens$tick) +
  labs(
    x = "Assumption for missing Meta",
    y = expression("SEM " * tau),
    title = "Missing-cell privacy-censoring sensitivity",
    subtitle = "Independent city grid; unpublished Meta filled at 1 / 5 / 9.9; T frozen at original Q75"
  ) +
  theme_nature() +
  scale_y_continuous(expand = expansion(mult = c(0.12, 0.12)))

ggsave(
  file.path(out_dir, "03f_meta_censoring_sensitivity_r.png"),
  p_cens, width = 7.2, height = 4.4, dpi = 300, bg = "white"
)
message("Saved: ", file.path(out_dir, "03f_meta_censoring_sensitivity_r.png"))
}
