#!/usr/bin/env Rscript
# 04_plots.R — 04a figures (allocation sensitivity & share-space redistribution M)
# 04b maps/cross-city figures are pipeline/04b_plots.R and cross-city/figures_cross_city.R.
#
# Fig 1 — Dumbbell: WorldPop vs Meta share of allocation to high-poverty cells (≥ p75), Table4b full_grid.
# Fig 2 — Bars: redistribution magnitude M (Table4 summary). Panel text kept minimal; define Σ formula in manuscript.
# Combined 04_operation_impact.png (dumbbell | bar; patchwork or cowplot).
#
# Single region (after run_all per city):
#   Rscript pipeline/04_plots.R -i outputs/KEN_Nairobi/04_impact
#
# All cities (combine outputs/*/04_impact):
#   Rscript pipeline/04_plots.R --cross-city -i outputs -o outputs/cross-city
#
# Requires: ggplot2, dplyr, tidyr, scales, jsonlite
# Optional (combined 04_operation_impact): patchwork (preferred) or cowplot

suppressPackageStartupMessages({
  library(ggplot2)
  library(dplyr)
  library(tidyr)
  library(scales)
})

if (!requireNamespace("jsonlite", quietly = TRUE)) {
  stop("Install jsonlite: install.packages(\"jsonlite\")")
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
      plot.caption = element_text(size = rel(0.85), colour = "grey35", hjust = 0),
      legend.title = element_text(face = "bold", size = rel(0.9)),
      legend.text = element_text(size = rel(0.85)),
      plot.margin = margin(10, 10, 10, 10)
    )
}

# Resolve project root from this script location (--file=...)
initial_ca <- commandArgs(trailingOnly = FALSE)
ff <- grep("^--file=", initial_ca, value = TRUE)
project_root <- if (length(ff)) {
  dirname(dirname(normalizePath(sub("^--file=", "", ff[1]), winslash = "/", mustWork = TRUE)))
} else {
  normalizePath(".", winslash = "/", mustWork = TRUE)
}
source(file.path(project_root, "pipeline", "region_config.R"), local = TRUE)

load_city_lookup <- function() {
  p <- file.path(project_root, "config", "regions.json")
  if (!file.exists(p)) return(character(0))
  regs <- jsonlite::read_json(p, simplifyVector = TRUE)
  nm <- names(regs)
  nm <- nm[!nm %in% c("data_root", "poverty_source", "poverty_grdi", "clip_source")]
  out <- stats::setNames(nm, nm)
  for (code in nm) {
    cfg <- regs[[code]]
    if (!is.list(cfg)) next
    lab <- cfg[["city_label"]]
    if (is.null(lab) || !nzchar(as.character(lab)[1])) lab <- cfg[["name"]]
    if (!is.null(lab) && nzchar(as.character(lab)[1])) out[[code]] <- as.character(lab)[1]
  }
  out
}

city_labels_for_regions <- function(region_codes, lookup) {
  vcapply <- function(X, FUN) vapply(X, FUN, character(1))
  vcapply(region_codes, function(rc) {
    if (length(lookup) && rc %in% names(lookup)) lookup[[rc]] else rc
  })
}

discover_cross_city <- function(outputs_root) {
  subs <- list.dirs(outputs_root, full.names = TRUE, recursive = FALSE)
  alloc_rows <- list()
  summ_rows <- list()
  for (d in subs) {
    code <- basename(d)
    if (code %in% c("cross-city", "cross-city_local", "01", "02", ".", "0", "footprints", "KEN")) next
    if (grepl("_local$", code)) next
    imp <- file.path(d, "04_impact")
    tb <- file.path(imp, "Table4b_allocation_sensitivity.csv")
    tm <- file.path(imp, "Table4_impact_population_summary.csv")
    if (file.exists(tb)) {
      z <- read.csv(tb, stringsAsFactors = FALSE)
      z$region_code <- code
      alloc_rows[[length(alloc_rows) + 1]] <- z
    }
    if (file.exists(tm)) {
      z <- read.csv(tm, stringsAsFactors = FALSE)
      z$region_code <- code
      summ_rows[[length(summ_rows) + 1]] <- z
    }
  }
  list(
    alloc = if (length(alloc_rows)) bind_rows(alloc_rows) else tibble(),
    summ = if (length(summ_rows)) bind_rows(summ_rows) else tibble()
  )
}

read_single_region <- function(impact_dir) {
  code <- basename(dirname(normalizePath(impact_dir)))
  tb <- file.path(impact_dir, "Table4b_allocation_sensitivity.csv")
  tm <- file.path(impact_dir, "Table4_impact_population_summary.csv")
  alloc <- if (file.exists(tb)) read.csv(tb, stringsAsFactors = FALSE) else tibble()
  summ <- if (file.exists(tm)) read.csv(tm, stringsAsFactors = FALSE) else tibble()
  if (nrow(alloc)) alloc$region_code <- code
  if (nrow(summ)) summ$region_code <- code
  list(alloc = alloc, summ = summ, region_code = code)
}

# --- CLI ---
in_arg <- NULL
out_arg <- NULL
cross_city <- FALSE
region_cli <- NULL  # reserved for parity with other scripts (--region sets title hint only)
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
  } else if (args[i] == "--cross-city") {
    cross_city <- TRUE
    i <- i + 1L
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

if (is.null(in_arg)) {
  in_arg <- file.path(project_root, "outputs")
}

lookup <- load_city_lookup()

if (cross_city) {
  outputs_root <- normalizePath(in_arg, winslash = "/", mustWork = TRUE)
  dat <- discover_cross_city(outputs_root)
  out_dir <- if (!is.null(out_arg)) {
    normalizePath(out_arg, winslash = "/", mustWork = FALSE)
  } else {
    file.path(project_root, "figure", "cross-city")
  }
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  suffix <- "_cross_city"
} else {
  if (!nzchar(in_arg) || !dir.exists(in_arg)) {
    stop("Provide existing 04_impact directory with -i outputs/<REGION>/04_impact, or use --cross-city -i outputs")
  }
  impact_dir <- normalizePath(in_arg, winslash = "/", mustWork = TRUE)
  dat <- read_single_region(impact_dir)
  if (!is.null(out_arg)) {
    out_dir <- out_arg
  } else if (!is.null(footprint_cli) && nzchar(footprint_cli)) {
    out_dir <- footprint_figure_dir(footprint_cli, "04_impact")
  } else if (!is.null(region_cli) && nzchar(region_cli)) {
    out_dir <- figure_dir(region_cli, "04_impact")
  } else {
    inf <- region_from_artifact_path(impact_dir)
    fp <- footprint_code_from_path(impact_dir)
    out_dir <- if (!is.null(fp)) {
      footprint_figure_dir(fp, "04_impact")
    } else if (!is.null(inf)) {
      figure_dir(inf, "04_impact")
    } else {
      impact_dir
    }
  }
  dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
  suffix <- ""
}

alloc <- dat$alloc %>% filter(.data$sample_scope == "full_grid")
summ <- dat$summ

p1 <- NULL
p2 <- NULL
h1_plot <- NA_real_
h2_plot <- NA_real_

if (nrow(alloc) == 0) {
  warning("No rows with sample_scope == full_grid in Table4b; Fig 1 skipped.")
} else {
  alloc <- alloc %>%
    mutate(
      region_code = if ("region_code" %in% names(.)) .data$region_code else .data$region,
      region_code = ifelse(is.na(.data$region_code) | .data$region_code == "",
        "unknown", as.character(.data$region_code)
      )
    )
  alloc$city_label <- city_labels_for_regions(alloc$region_code, lookup)

  # WorldPop green / Meta pink (same palette as other pipeline R figures)
  col_wp <- "#798234"
  col_meta <- "#D46780"

  seg <- alloc %>%
    mutate(
      city_ord = reorder(.data$city_label, .data$share_wp_high_poverty + .data$share_meta_high_poverty)
    )

  pts <- seg %>%
    pivot_longer(
      cols = c("share_wp_high_poverty", "share_meta_high_poverty"),
      names_to = "source_key",
      values_to = "share"
    ) %>%
    mutate(
      source = factor(ifelse(.data$source_key == "share_wp_high_poverty", "WorldPop", "Meta"),
        levels = c("WorldPop", "Meta")
      ),
      city_ord = .data$city_ord
    )

  p1 <- ggplot(seg) +
    geom_segment(
      aes(
        y = .data$city_ord,
        yend = .data$city_ord,
        x = .data$share_wp_high_poverty,
        xend = .data$share_meta_high_poverty
      ),
      linewidth = 0.85,
      colour = "grey55",
      lineend = "round"
    ) +
    geom_point(data = pts, aes(x = .data$share, y = .data$city_ord, colour = .data$source), size = 3.2, stroke = 0) +
    scale_colour_manual(values = c(WorldPop = col_wp, Meta = col_meta), name = NULL) +
    scale_x_continuous(
      labels = percent_format(accuracy = 0.1),
      expand = expansion(mult = c(0.03, 0.08))
    ) +
    labs(
      title = "High-poverty allocation share",
      x = "Allocation share to high-poverty cells",
      y = NULL
    ) +
    theme_nature() +
    theme(legend.position = "top")

  # Tighter height without subtitle/caption under panel
  h1_plot <- max(3.2, 0.42 * nrow(seg) + 1.1)
  f1 <- file.path(out_dir, paste0("04_high_poverty_allocation_dumbbell", suffix, ".png"))
  ggsave(f1, p1, width = 7.2, height = h1_plot, dpi = 300, bg = "white")
  message("Saved: ", f1)
}

if (nrow(summ) == 0 || !"share_mass_redistribution_M" %in% names(summ)) {
  warning("Missing Table4 summary or share_mass_redistribution_M; Fig 2 skipped.")
} else {
  summ <- summ %>%
    mutate(
      region_code = if ("region_code" %in% names(.)) .data$region_code else .data$region,
      region_code = ifelse(is.na(.data$region_code) | .data$region_code == "",
        "unknown", as.character(.data$region_code)
      ),
      M = as.numeric(.data$share_mass_redistribution_M)
    )
  summ <- summ %>% filter(!is.na(.data$M))

  if (nrow(summ) == 0) {
    warning("No finite M values; Fig 2 skipped.")
  } else {
  summ$city_label <- city_labels_for_regions(summ$region_code, lookup)

  p2 <- ggplot(summ, aes(x = reorder(.data$city_label, .data$M), y = .data$M)) +
    geom_col(fill = "#798234", width = 0.72) +
    coord_flip() +
    scale_y_continuous(
      labels = percent_format(accuracy = 0.1),
      limits = c(0, NA),
      expand = expansion(mult = c(0, 0.04))
    ) +
    labs(
      title = "Redistribution magnitude \u2014 M",
      x = NULL,
      y = "M (half-L1 distance between share vectors)"
    ) +
    theme_nature()

  h2_plot <- max(3.0, 0.38 * nrow(summ) + 1.0)
  f2 <- file.path(out_dir, paste0("04_redistribution_M_bar", suffix, ".png"))
  ggsave(f2, p2, width = 6.8, height = h2_plot, dpi = 300, bg = "white")
  message("Saved: ", f2)
  }
}

# --- Combined Figure 6 (operational impact): dumbbell + M bar ---
if (!is.null(p1) && !is.null(p2)) {
  f6 <- file.path(out_dir, paste0("04_operation_impact", suffix, ".png"))
  # Side-by-side: total width ≈ sum of single-panel widths; height ≈ taller panel
  w_tot <- 7.2 + 6.8 + 1.0
  h_tot <- max(h1_plot, h2_plot) + 1.2

  if (requireNamespace("patchwork", quietly = TRUE)) {
    p6 <- (p1 | p2) +
      patchwork::plot_layout(widths = c(1, 1)) +
      patchwork::plot_annotation(
        title = "Operational allocation impact",
        tag_levels = "a",
        theme = ggplot2::theme(
          plot.title = ggplot2::element_text(face = "bold", size = 13, hjust = 0)
        )
      )
    ggplot2::ggsave(filename = f6, plot = p6, width = w_tot, height = h_tot, dpi = 300, bg = "white")
    message("Saved: ", f6)
  } else if (requireNamespace("cowplot", quietly = TRUE)) {
    title_canvas <- cowplot::ggdraw() +
      cowplot::draw_label(
        "Operational allocation impact",
        fontface = "bold",
        size = 13,
        x = 0,
        hjust = 0
      )
    panels <- cowplot::plot_grid(
      p1,
      p2,
      ncol = 2,
      align = "h",
      axis = "tb",
      labels = c("a", "b"),
      label_fontface = "bold",
      rel_widths = c(1, 1)
    )
    p6 <- cowplot::plot_grid(title_canvas, panels, ncol = 1, rel_heights = c(0.08, 1))
    ggplot2::ggsave(filename = f6, plot = p6, width = w_tot, height = h_tot, dpi = 300, bg = "white")
    message("Saved: ", f6)
  } else {
    warning(
      "04_operation_impact skipped: install patchwork or cowplot ",
      "(e.g. install.packages(c(\"patchwork\",\"cowplot\")))."
    )
  }
} else {
  message(
    "04_operation_impact skipped: need both high-poverty dumbbell data (Table4b full_grid) ",
    "and M summary (Table4_impact_population_summary)."
  )
}
