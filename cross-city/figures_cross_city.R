#!/usr/bin/env Rscript
# Cross-city figures for every selected city that has data.
#
# Tables are read from outputs/cross-city/.
# Figures are written to figure/cross-city/.
#
# Usage: Rscript cross-city/figures_cross_city.R
#        Rscript cross-city/figures_cross_city.R -o figure/cross-city/

suppressPackageStartupMessages({
  library(sf)
  library(ggplot2)
  library(dplyr)
  library(tidyr)
})
has_patchwork <- requireNamespace("patchwork", quietly = TRUE)
if (has_patchwork) library(patchwork)

args <- commandArgs(trailingOnly = TRUE)
fig_dir_arg <- NA_character_
if (length(args) >= 2 && args[1] == "-o") {
  fig_dir_arg <- args[2]
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

source(file.path(project_root, "pipeline", "region_config.R"))

tbl_dir <- file.path(project_root, "outputs", "cross-city")
fig_dir <- if (!is.na(fig_dir_arg) && nzchar(fig_dir_arg)) {
  if (grepl("^/", fig_dir_arg)) fig_dir_arg else file.path(project_root, fig_dir_arg)
} else {
  file.path(project_root, "figure", "cross-city")
}
dir.create(fig_dir, recursive = TRUE, showWarnings = FALSE)

armyrose <- ARMYROSE

tbl1_path <- file.path(tbl_dir, "Table1_cross_city_table.csv")
tbl2_path <- file.path(tbl_dir, "Table2_poverty_effect_spatially_corrected.csv")
if (!file.exists(tbl1_path)) {
  stop("No ", tbl1_path, ". Run python cross-city/run_cross_city_table.py --aggregate-only first.")
}
tbl1 <- read.csv(tbl1_path, check.names = FALSE)
if (!("City" %in% names(tbl1))) stop("Table 1 needs a City column")

region_for_city <- function(city) {
  if ("Region" %in% names(tbl1)) {
    hit <- tbl1$Region[tbl1$City == city]
    if (length(hit) && !is.na(hit[[1]]) && nzchar(as.character(hit[[1]]))) {
      return(as.character(hit[[1]]))
    }
  }
  regions <- load_regions()
  for (code in region_codes(regions)) {
    lab <- regions[[code]]$city_label
    if (!is.null(lab) && identical(as.character(lab), city)) return(code)
    if (!is.null(lab) && identical(paste0(lab, " (full)"), city)) return(code)
  }
  NULL
}

save_wrapped <- function(plots, filename, ncol = 4, per_w = 3.4, per_h = 3.4,
                         title = NULL, subtitle = NULL, guides = "keep") {
  n <- length(plots)
  if (n == 0) return(invisible(NULL))
  ncol <- min(ncol, n)
  nrow <- ceiling(n / ncol)
  dest <- file.path(fig_dir, filename)
  if (has_patchwork) {
    combined <- Reduce(`+`, unname(plots)) +
      patchwork::plot_layout(ncol = ncol, guides = guides)
    if (!is.null(title) || !is.null(subtitle)) {
      combined <- combined +
        patchwork::plot_annotation(title = title, subtitle = subtitle) &
        theme(
          plot.title = element_text(face = "bold", size = 12),
          plot.subtitle = element_text(colour = "gray40", size = 9)
        )
    }
    ggsave(dest, combined, width = per_w * ncol, height = per_h * nrow + 0.6, dpi = 300)
  } else if (requireNamespace("gridExtra", quietly = TRUE)) {
    png(dest, width = per_w * ncol, height = per_h * nrow + 0.4, units = "in", res = 300)
    do.call(gridExtra::grid.arrange, c(unname(plots), list(ncol = ncol, top = title)))
    dev.off()
  } else {
    ggsave(dest, plots[[1]], width = 6, height = 5, dpi = 300)
    message("Install patchwork or gridExtra for multi-panel figures; saved first panel only")
  }
  message("Saved: ", dest)
}

cities <- as.character(tbl1$City)
city_to_reg <- setNames(lapply(cities, region_for_city), cities)
city_to_reg <- city_to_reg[!vapply(city_to_reg, is.null, logical(1))]
if (!length(city_to_reg)) {
  stop("Could not map Table 1 cities to region codes. Re-run the aggregator so Table 1 includes Region.")
}

city_fill <- function(cities) {
  cols <- vapply(as.character(cities), function(city) {
    reg <- city_to_reg[[city]]
    nm <- country_display_name(reg)
    col <- unname(ARMYROSE_COUNTRY[nm])
    if (length(col) != 1 || is.na(col)) ARMYROSE[[7]] else col
  }, character(1))
  setNames(cols, as.character(cities))
}

n_hits <- names(tbl1)[grepl("N cells \\(valid\\)", names(tbl1), ignore.case = TRUE)]
if (!length(n_hits)) {
  n_hits <- names(tbl1)[grepl("N cells \\(total\\)", names(tbl1), ignore.case = TRUE)]
}
n_col <- if (length(n_hits)) n_hits[[1]] else NA_character_
n_for <- function(city) {
  if (is.na(n_col) || !n_col %in% names(tbl1)) return(NA_integer_)
  hit <- tbl1[[n_col]][tbl1$City == city]
  if (!length(hit) || is.na(hit[[1]])) return(NA_integer_)
  as.integer(round(as.numeric(hit[[1]])))
}
city_n_label <- function(cities) {
  vapply(as.character(cities), function(city) {
    n <- n_for(city)
    if (is.na(n)) city else sprintf("%s (n=%d)", city, n)
  }, character(1))
}

country_of <- function(cities) {
  vapply(as.character(cities), function(city) {
    country_display_name(city_to_reg[[city]])
  }, character(1))
}

save_city_hbar <- function(df, filename, title, xlab, xmin, xmax) {
  df <- df[!is.na(df$val), , drop = FALSE]
  if (nrow(df) == 0) return(invisible(NULL))
  df$Country <- country_of(df$City)
  df$Label <- factor(as.character(df$Label), levels = rev(unique(as.character(df$Label))))
  p <- ggplot(df, aes(x = val, y = Label, fill = Country)) +
    geom_col(orientation = "y", width = 0.7, alpha = 0.85) +
    geom_text(aes(label = sprintf("%.2f", val)), hjust = -0.12, size = 3) +
    scale_fill_manual(values = ARMYROSE_COUNTRY, breaks = unique(df$Country), name = NULL) +
    scale_x_continuous(expand = expansion(mult = c(0.01, 0.12))) +
    coord_cartesian(xlim = c(xmin, xmax), clip = "off") +
    labs(title = title, x = xlab, y = NULL) +
    theme_minimal(base_size = 11) +
    theme(
      plot.title = element_text(face = "bold", size = 12, hjust = 0),
      panel.grid.major.y = element_blank(),
      legend.position = "bottom",
      legend.justification = "left",
      plot.margin = margin(6, 18, 6, 6)
    )
  ggsave(
    file.path(fig_dir, filename), p,
    width = 8.2, height = max(4.2, 0.38 * nrow(df) + 1.4), dpi = 300
  )
  message("Saved: ", file.path(fig_dir, filename))
}

# ---- FIGURE 1: Spatial Agreement (log-log scatter) ----
fig1_plots <- list()
for (city in names(city_to_reg)) {
  reg <- city_to_reg[[city]]
  path <- find_artifact(reg, "02", "harmonised_with_residual.gpkg")
  if (is.null(path)) next
  gdf <- st_read(path, quiet = TRUE)
  df <- data.frame(wp = gdf$worldpop_share, meta = gdf$meta_share)
  df <- df[df$wp > 0 & df$meta > 0, ]
  if (nrow(df) < 2) next
  df$log_wp <- log(df$wp)
  df$log_meta <- log(df$meta)
  lim <- range(c(df$log_wp, df$log_meta), na.rm = TRUE)
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
  spearman_col <- names(tbl1)[grepl("Spearman", names(tbl1), ignore.case = TRUE)][1]
  pearson_col <- names(tbl1)[grepl("Pearson", names(tbl1), ignore.case = TRUE)][1]
  row <- tbl1[tbl1$City == city, ]
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
  fig1_plots[[city]] <- p
}
if (length(fig1_plots) > 0) {
  save_wrapped(
    fig1_plots, "02_spatial_agreement.png", ncol = min(4, length(fig1_plots)),
    title = "Spatial Agreement (log-log scatter)",
    subtitle = "Meta share vs WorldPop share. Dashed = 1:1 line; shaded = regression line."
  )
  if (has_patchwork && length(fig1_plots) <= 8) {
    save_wrapped(
      fig1_plots, "02_spatial_agreement_row.png",
      ncol = length(fig1_plots), per_w = 3.2, per_h = 3.6,
      title = "Spatial Agreement (log-log scatter)",
      subtitle = "Meta share vs WorldPop share. Dashed = 1:1 line; shaded = regression line."
    )
  }
}

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

# ---- Concentration ratio ----
fig1_data <- lapply(names(city_to_reg), function(city) {
  reg <- city_to_reg[[city]]
  path <- find_artifact(reg, "02", "02_top_share_concentration.csv")
  if (is.null(path)) return(NULL)
  d <- read.csv(path)
  row10 <- d[d$Top_pct == 0.1, ]
  if (nrow(row10) == 0) return(NULL)
  ratio <- row10$Share_Meta / row10$Share_WP
  data.frame(City = city, Share_WP = row10$Share_WP, Share_Meta = row10$Share_Meta, Ratio = ratio)
})
fig1_data <- bind_rows(Filter(Negate(is.null), fig1_data))
if (nrow(fig1_data) > 0) {
  fig1_data <- fig1_data %>% arrange(desc(Ratio))
  fig1_data$Label <- city_n_label(fig1_data$City)
  fig1_data$Label <- factor(fig1_data$Label, levels = fig1_data$Label)
  fills <- city_fill(fig1_data$City)
  p1 <- ggplot(fig1_data, aes(x = Label, y = Ratio, fill = City)) +
    geom_col(width = 0.7, alpha = 0.85) +
    geom_hline(yintercept = 1, linetype = "dashed", linewidth = 0.6, colour = "gray30") +
    geom_text(aes(label = sprintf("%.2f", Ratio)), vjust = -0.5, size = 3.2, fontface = "bold") +
    scale_fill_manual(values = fills, guide = "none") +
    scale_y_continuous(expand = expansion(mult = c(0.02, 0.12))) +
    labs(
      title = "Structural Concentration Comparison",
      subtitle = "Ratio = Meta/WP share in the top 10% of cells. >1 = more concentration in Meta. n = valid cells.",
      x = NULL, y = "Concentration ratio"
    ) +
    theme_minimal(base_size = 11) +
    theme(
      plot.title = element_text(face = "bold", size = 10, hjust = 0),
      plot.subtitle = element_text(colour = "gray40", size = 8, hjust = 0),
      panel.grid.major.x = element_blank(),
      axis.text.x = element_text(angle = 40, hjust = 1, size = 7.5)
    )
  ggsave(file.path(fig_dir, "02_concentration_ratio.png"), p1,
    width = max(7, 0.62 * nrow(fig1_data) + 2), height = 4.0, dpi = 300)
  message("Saved: ", file.path(fig_dir, "02_concentration_ratio.png"))
}

# ---- Lorenz ----
dg_col <- names(tbl1)[grepl("Gini", names(tbl1), ignore.case = TRUE)][1]
delta_gini <- setNames(rep(NA_real_, length(city_to_reg)), names(city_to_reg))
if (!is.na(dg_col) && dg_col %in% names(tbl1)) {
  for (i in seq_len(nrow(tbl1))) {
    city <- as.character(tbl1$City[i])
    if (city %in% names(delta_gini)) delta_gini[city] <- as.numeric(tbl1[[dg_col]][i])
  }
}
fig2_plots <- list()
for (city in names(city_to_reg)) {
  reg <- city_to_reg[[city]]
  path <- find_artifact(reg, "02", "harmonised_with_residual.gpkg")
  if (is.null(path)) next
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
if (length(fig2_plots) > 0) {
  if (length(fig2_plots) >= 1 && has_patchwork) {
    fig2_plots[[1]] <- fig2_plots[[1]] + theme(legend.position = "bottom")
  }
  save_wrapped(
    fig2_plots, "02_lorenz_curves.png", ncol = min(4, length(fig2_plots)),
    title = "Lorenz Curves",
    subtitle = "WorldPop vs Meta allocation shares on the analysis grid",
    guides = "collect"
  )
}

# ---- Residual maps (combined panel only; per-city maps live in figure/{COUNTRY}/{city}/02/) ----
residual_maps <- list()
for (city in names(city_to_reg)) {
  path <- find_artifact(city_to_reg[[city]], "02", "harmonised_with_residual.gpkg")
  if (is.null(path)) next
  gdf <- st_read(path, quiet = TRUE)
  p <- plot_allocation_residual_map(gdf, title = city)
  if (!is.null(p)) residual_maps[[city]] <- p
}
if (length(residual_maps) > 0) {
  save_wrapped(
    residual_maps, "02_residual_maps.png",
    ncol = min(4, length(residual_maps)), per_w = 4.2, per_h = 4.2,
    title = "Allocation Residual Maps",
    subtitle = "log(meta_share / worldpop_share)",
    guides = "collect"
  )
}

# ---- SEM forest (grouped by country; left panel of 03c_forest_scatter) ----
p4 <- NULL
fig4_data <- lapply(names(city_to_reg), function(city) {
  reg <- city_to_reg[[city]]
  path <- find_artifact(reg, "03c_spatial_regression", "Table_tau_comparison.csv")
  if (is.null(path)) return(NULL)
  d <- read.csv(path)
  sem <- d[grepl("SEM", d$Model), ]
  if (nrow(sem) == 0) return(NULL)
  pval <- if ("p_value" %in% names(sem)) sem$p_value[[1]] else sem$p[[1]]
  country <- country_display_name(reg)
  hex <- unname(ARMYROSE_COUNTRY[country])
  if (length(hex) != 1 || is.na(hex)) hex <- ARMYROSE[[7]]
  data.frame(
    City = city,
    Country = country,
    hex = hex,
    tau = sem$tau[[1]],
    SE = sem$SE[[1]],
    p = as.numeric(pval),
    exp_tau = sem$exp_tau[[1]],
    CI_lo = sem$tau[[1]] - 1.96 * sem$SE[[1]],
    CI_hi = sem$tau[[1]] + 1.96 * sem$SE[[1]],
    stringsAsFactors = FALSE
  )
})
fig4_data <- bind_rows(Filter(Negate(is.null), fig4_data))
if (nrow(fig4_data) > 0) {
  fig4_data$sig <- !is.na(fig4_data$p) & fig4_data$p < 0.05
  countries <- unique(fig4_data$Country)
  axis_rows <- list()
  city_rows <- list()
  y <- 0
  first_group <- TRUE
  for (country in countries) {
    sub <- fig4_data[fig4_data$Country == country, , drop = FALSE]
    if (nrow(sub) == 0) next
    if (!first_group) y <- y - 0.22
    first_group <- FALSE
    axis_rows[[length(axis_rows) + 1]] <- data.frame(
      y = y,
      Label = country,
      label_color = sub$hex[[1]],
      face = "bold",
      stringsAsFactors = FALSE
    )
    y <- y - 0.58
    for (i in seq_len(nrow(sub))) {
      row <- sub[i, ]
      p_txt <- if (is.na(row$p)) "" else if (row$p < 0.001) "p<0.001" else sprintf("p=%.3f", row$p)
      city_rows[[length(city_rows) + 1]] <- data.frame(
        y = y,
        tau = row$tau,
        CI_lo = row$CI_lo,
        CI_hi = row$CI_hi,
        fill = if (row$sig) row$hex else "white",
        edge = row$hex,
        annot = sprintf("%.2f  %s", row$tau, p_txt),
        stringsAsFactors = FALSE
      )
      axis_rows[[length(axis_rows) + 1]] <- data.frame(
        y = y,
        Label = paste0("  ", city_n_label(row$City)),
        label_color = "grey25",
        face = "plain",
        stringsAsFactors = FALSE
      )
      y <- y - 0.70
    }
  }
  axis_df <- bind_rows(axis_rows)
  city_df <- bind_rows(city_rows)
  xmax <- max(city_df$CI_hi, na.rm = TRUE)
  xmin <- min(city_df$CI_lo, na.rm = TRUE)
  pad <- 0.08 * if (xmax > xmin) xmax - xmin else 1
  lab_x <- xmin - pad * 0.55
  legend_df <- data.frame(
    x = xmax + pad * 1.6,
    y = c(0.02, -0.55),
    fill = c("grey30", "white"),
    edge = c("grey30", "grey30"),
    lab = c("p < 0.05", "p \u2265 0.05"),
    stringsAsFactors = FALSE
  )
  p4 <- ggplot() +
    geom_vline(xintercept = 0, linetype = "dashed", colour = "grey55", linewidth = 0.5) +
    geom_segment(
      data = city_df,
      aes(x = CI_lo, xend = CI_hi, y = y, yend = y),
      colour = "grey35", linewidth = 0.55
    ) +
    geom_point(
      data = city_df,
      aes(x = tau, y = y, fill = fill, colour = edge),
      shape = 21, size = 2.5, stroke = 1.05
    ) +
    geom_text(
      data = city_df,
      aes(x = CI_hi, y = y, label = annot),
      hjust = -0.12, size = 2.35, colour = "grey50"
    ) +
    geom_text(
      data = axis_df,
      aes(x = lab_x, y = y, label = Label, colour = label_color, fontface = face),
      hjust = 1, size = 3.05
    ) +
    geom_point(
      data = legend_df,
      aes(x = x, y = y, fill = fill, colour = edge),
      shape = 21, size = 2.4, stroke = 1.0
    ) +
    geom_text(
      data = legend_df,
      aes(x = x, y = y, label = lab),
      hjust = -0.35, size = 2.5, colour = "grey30"
    ) +
    scale_fill_identity() +
    scale_colour_identity() +
    coord_cartesian(
      xlim = c(xmin - pad * 0.15, xmax + pad * 4.4),
      ylim = c(y + 0.28, 0.38),
      clip = "off"
    ) +
    labs(
      title = "Poverty effect on Meta vs WorldPop allocation, by city",
      x = "SEM \u03c4  (high-poverty quartile vs rest), 95% CI",
      y = NULL
    ) +
    theme_minimal(base_size = 11) +
    theme(
      plot.title = element_text(face = "bold", size = 11, hjust = 0),
      panel.grid.major.y = element_blank(),
      panel.grid.minor = element_blank(),
      axis.text.y = element_blank(),
      axis.ticks.y = element_blank(),
      plot.margin = margin(6, 8, 6, 92)
    )
  ggsave(
    file.path(fig_dir, "03c_sem_forest.png"), p4,
    width = 9.0, height = max(4.2, 0.26 * nrow(axis_df) + 1.4), dpi = 300
  )
  message("Saved: ", file.path(fig_dir, "03c_sem_forest.png"))
  tau_csv <- fig4_data
  tau_csv$Region <- unname(vapply(tau_csv$City, function(city) {
    reg <- city_to_reg[[city]]
    if (is.null(reg)) NA_character_ else as.character(reg)
  }, character(1)))
  tau_csv <- tau_csv[, c("Country", "City", "Region", "tau", "SE", "p", "CI_lo", "CI_hi", "exp_tau", "sig")]
  tau_path <- file.path(tbl_dir, "Table_sem_tau_all_cities.csv")
  dir.create(tbl_dir, recursive = TRUE, showWarnings = FALSE)
  write.csv(tau_csv, tau_path, row.names = FALSE)
  message("Saved: ", tau_path)
}

# ---- Spearman ρ (cross-city bar) ----
sp_col <- names(tbl1)[grepl("Spearman", names(tbl1), ignore.case = TRUE)][1]
if (length(sp_col) && sp_col %in% names(tbl1)) {
  sp <- data.frame(
    City = names(city_to_reg),
    val = as.numeric(tbl1[[sp_col]][match(names(city_to_reg), tbl1$City)]),
    stringsAsFactors = FALSE
  )
  sp <- sp[sp$City %in% names(city_to_reg), ]
  sp$Label <- sp$City
  lo <- min(0.5, min(sp$val, na.rm = TRUE) - 0.05)
  save_city_hbar(
    sp, "02_spearman.png", "Spatial agreement",
    "Spearman \u03c1  (log Meta share vs log WorldPop share)", lo, 1.0
  )
}

# ---- Hotspot Jaccard ----
rank_path <- file.path(tbl_dir, "Table_rank_instability_cross_city.csv")
if (file.exists(rank_path)) {
  tr <- read.csv(rank_path, check.names = FALSE)
  jac_col <- names(tr)[grepl("jaccard_top_10", names(tr), ignore.case = TRUE)][1]
  if (length(jac_col) && jac_col %in% names(tr)) {
    have <- names(city_to_reg)[names(city_to_reg) %in% tr$City]
    jac <- data.frame(
      City = have,
      val = as.numeric(tr[[jac_col]][match(have, tr$City)]),
      stringsAsFactors = FALSE
    )
    jac$Label <- city_n_label(jac$City)
    save_city_hbar(
      jac, "03b_hotspot_jaccard.png", "Hotspot overlap",
      "Jaccard overlap of top 10% cells (Meta vs WorldPop)", 0, 1.08
    )
  }
}

# ---- Spearman vs SEM τ ----
if (nrow(fig4_data) > 0 && length(sp_col) && sp_col %in% names(tbl1)) {
  df_st <- data.frame(
    City = fig4_data$City,
    Country = fig4_data$Country,
    tau = fig4_data$tau,
    spearman = as.numeric(tbl1[[sp_col]][match(fig4_data$City, tbl1$City)]),
    stringsAsFactors = FALSE
  )
  df_st <- df_st[complete.cases(df_st), ]
  if (nrow(df_st) >= 2) {
    p_st <- ggplot(df_st, aes(x = spearman, y = tau, colour = Country, label = City)) +
      geom_hline(yintercept = 0, linetype = "dashed", colour = "grey55", linewidth = 0.5) +
      geom_vline(xintercept = 0.75, linetype = "dotted", colour = "grey80", linewidth = 0.5) +
      geom_point(size = 3.2) +
      geom_text(nudge_x = 0.008, nudge_y = 0.012, hjust = 0, vjust = 0, size = 2.7, show.legend = FALSE) +
      scale_colour_manual(values = ARMYROSE_COUNTRY, breaks = unique(df_st$Country), name = NULL) +
      labs(
        title = "Agreement vs poverty bias",
        x = "Spearman \u03c1  (spatial agreement)",
        y = "SEM \u03c4  (poverty effect)"
      ) +
      theme_minimal(base_size = 11) +
      theme(
        plot.title = element_text(face = "bold", size = 12, hjust = 0),
        panel.grid.minor = element_blank(),
        legend.position = "bottom",
        legend.justification = "left"
      )
    ggsave(file.path(fig_dir, "03c_spearman_vs_tau.png"), p_st, width = 7.4, height = 5.4, dpi = 300)
    message("Saved: ", file.path(fig_dir, "03c_spearman_vs_tau.png"))
  }
}

# ---- Scatter Delta Gini vs Poverty tau ----
p5 <- NULL
if (file.exists(tbl2_path)) {
  t2 <- read.csv(tbl2_path, check.names = FALSE)
  dg_col <- names(tbl1)[grepl("Gini", names(tbl1), ignore.case = TRUE)][1]
  tau_col <- names(t2)[grepl("SEM τ|SEM.τ|^SEM", names(t2))][1]
  if (is.na(tau_col) || !nzchar(tau_col)) tau_col <- names(t2)[grepl("SEM", names(t2), ignore.case = TRUE)][1]
  if (length(dg_col) && dg_col %in% names(tbl1) && length(tau_col) && tau_col %in% names(t2)) {
    df_scatter <- tbl1 %>% select(City, Delta_Gini = all_of(dg_col)) %>%
      inner_join(t2 %>% select(City, tau = all_of(tau_col)), by = "City")
    df_scatter$Delta_Gini <- as.numeric(df_scatter$Delta_Gini)
    df_scatter$tau <- as.numeric(df_scatter$tau)
    df_scatter <- df_scatter[complete.cases(df_scatter), ]
    if (nrow(df_scatter) >= 2) {
      fills <- city_fill(df_scatter$City)
      p5 <- ggplot(df_scatter, aes(x = Delta_Gini, y = tau, colour = City, label = City)) +
        geom_hline(yintercept = 0, linetype = "dashed", colour = "gray50", linewidth = 0.5) +
        geom_vline(xintercept = 0, linetype = "dashed", colour = "gray50", linewidth = 0.5) +
        geom_point(size = 4, shape = 21, fill = "white", stroke = 1.2) +
        geom_text(nudge_y = -0.01, vjust = 1, hjust = 0.5, size = 3.0, show.legend = FALSE) +
        scale_colour_manual(values = fills, guide = "none") +
        scale_x_continuous(expand = expansion(mult = c(0.2, 0.35))) +
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
      ggsave(file.path(fig_dir, "03c_delta_gini_vs_tau.png"), p5, width = 6.5, height = 5.2, dpi = 300)
      message("Saved: ", file.path(fig_dir, "03c_delta_gini_vs_tau.png"))
    }
  }
}

if (!is.null(p4) && !is.null(p5) && has_patchwork) {
  n_axis <- if (exists("axis_df")) nrow(axis_df) else nrow(fig4_data)
  forest_h <- max(7.4, 0.26 * n_axis + 1.6)
  combined45 <- p4 + (p5 / patchwork::plot_spacer() + patchwork::plot_layout(heights = c(1.45, 1))) +
    patchwork::plot_layout(ncol = 2, widths = c(1.4, 1))
  ggsave(
    file.path(fig_dir, "03c_forest_scatter.png"), combined45,
    width = 13.2, height = forest_h, dpi = 300
  )
  message("Saved: ", file.path(fig_dir, "03c_forest_scatter.png"))
}

message("\nCross-city figures saved to: ", fig_dir)
