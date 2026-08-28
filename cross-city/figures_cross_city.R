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

# Top-k allocation share (shares renormalised to sum to 1).
top_share <- function(x, k) {
  x <- x[is.finite(x) & x > 0]
  if (length(x) == 0) return(NA_real_)
  s <- x / sum(x)
  k <- min(k, length(s))
  sum(sort(s, decreasing = TRUE)[seq_len(k)])
}

# Percentile bootstrap CI for Meta/WP top-10% concentration ratio.
concentration_ratio_ci <- function(wp, meta, pct = 0.1, B = 1000, conf = 0.95, seed = 1) {
  ok <- is.finite(wp) & is.finite(meta) & wp > 0 & meta > 0
  wp <- wp[ok]
  meta <- meta[ok]
  n <- length(wp)
  if (n < 10) {
    return(c(ratio = NA_real_, lo = NA_real_, hi = NA_real_, n = n, k = NA_real_))
  }
  k <- max(1L, as.integer(ceiling(pct * n)))
  ratio <- top_share(meta, k) / top_share(wp, k)
  set.seed(seed)
  ratios <- rep(NA_real_, B)
  for (b in seq_len(B)) {
    i <- sample.int(n, n, replace = TRUE)
    den <- top_share(wp[i], k)
    num <- top_share(meta[i], k)
    if (is.finite(den) && den > 0) ratios[b] <- num / den
  }
  alpha <- (1 - conf) / 2
  qs <- stats::quantile(ratios, probs = c(alpha, 1 - alpha), na.rm = TRUE, names = FALSE)
  c(ratio = ratio, lo = qs[[1]], hi = qs[[2]], n = n, k = k)
}

# ---- Concentration ratio (95% bootstrap CI) ----
fig1_data <- lapply(names(city_to_reg), function(city) {
  reg <- city_to_reg[[city]]
  path <- find_artifact(reg, "02", "harmonised_with_residual.gpkg")
  if (is.null(path)) return(NULL)
  message("Bootstrap concentration ratio CI: ", city)
  gdf <- st_read(path, quiet = TRUE)
  ci <- concentration_ratio_ci(gdf$worldpop_share, gdf$meta_share, conf = 0.95)
  if (is.na(ci[["ratio"]])) return(NULL)
  data.frame(
    City = city,
    Region = as.character(reg),
    Ratio = unname(ci[["ratio"]]),
    lo = unname(ci[["lo"]]),
    hi = unname(ci[["hi"]]),
    n = unname(ci[["n"]]),
    k = unname(ci[["k"]]),
    stringsAsFactors = FALSE
  )
})
fig1_data <- bind_rows(Filter(Negate(is.null), fig1_data))
if (nrow(fig1_data) > 0) {
  fig1_data <- fig1_data %>% arrange(desc(Ratio))
  fig1_data$Label <- city_n_label(fig1_data$City)
  fig1_data$Label <- factor(fig1_data$Label, levels = fig1_data$Label)
  fills <- city_fill(fig1_data$City)
  y_top <- max(fig1_data$hi, fig1_data$Ratio, na.rm = TRUE)
  p1 <- ggplot(fig1_data, aes(x = Label, y = Ratio, fill = City)) +
    geom_col(width = 0.7, alpha = 0.85) +
    geom_errorbar(aes(ymin = lo, ymax = hi), width = 0.18, linewidth = 0.45, colour = "grey25") +
    geom_hline(yintercept = 1, linetype = "dashed", linewidth = 0.6, colour = "gray30") +
    geom_text(aes(y = hi, label = sprintf("%.2f", Ratio)), vjust = -0.45, size = 2.8, fontface = "bold") +
    scale_fill_manual(values = fills, guide = "none") +
    scale_y_continuous(expand = expansion(mult = c(0.02, 0.16))) +
    coord_cartesian(ylim = c(0, y_top * 1.08), clip = "off") +
    labs(
      title = "Structural Concentration Comparison",
      subtitle = paste0(
        "Ratio = Meta/WP share in the top 10% of cells. ",
        "Error bars = 95% percentile bootstrap CI (cell resampling).\n",
        ">1 = more concentration in Meta."
      ),
      x = NULL, y = "Concentration ratio"
    ) +
    theme_minimal(base_size = 11) +
    theme(
      plot.title = element_text(face = "bold", size = 10, hjust = 0),
      plot.subtitle = element_text(colour = "gray40", size = 8, hjust = 0, lineheight = 1.15),
      panel.grid.major.x = element_blank(),
      axis.text.x = element_text(angle = 40, hjust = 1, size = 7.5),
      plot.margin = margin(6, 8, 6, 6)
    )
  ggsave(file.path(fig_dir, "02_concentration_ratio.png"), p1,
    width = max(7.4, 0.62 * nrow(fig1_data) + 2), height = 4.7, dpi = 300)
  message("Saved: ", file.path(fig_dir, "02_concentration_ratio.png"))
  fig1_data$Country <- country_of(fig1_data$City)
  ci_path <- file.path(tbl_dir, "Table_concentration_ratio_ci.csv")
  dir.create(tbl_dir, recursive = TRUE, showWarnings = FALSE)
  write.csv(
    fig1_data[, c("Country", "City", "Region", "Ratio", "lo", "hi", "n", "k")],
    ci_path, row.names = FALSE
  )
  message("Saved: ", ci_path)
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

# ---- Residual maps (combined panel only; per-city maps live in figure/city/{COUNTRY}/{city}/02/) ----
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

# ---- SEM τ vs city GRDI (context) and within-city GRDI gap (dose) ----
# τ is a within-city contrast (top GRDI quartile vs rest). Median GRDI is city
# context; the T=1 vs T=0 median gap is the treatment contrast on the same cells.
if (nrow(fig4_data) > 0) {
  has_ggrepel <- requireNamespace("ggrepel", quietly = TRUE)
  grdi_rows <- lapply(seq_len(nrow(fig4_data)), function(i) {
    city <- fig4_data$City[[i]]
    reg <- city_to_reg[[city]]
    if (is.null(reg)) return(NULL)
    path <- find_artifact(reg, "02", "harmonised_with_residual.gpkg")
    if (is.null(path)) return(NULL)
    gdf <- st_read(path, quiet = TRUE)
    if (!("poverty_mean" %in% names(gdf))) return(NULL)
    pov <- as.numeric(gdf$poverty_mean)
    res <- if ("allocation_residual" %in% names(gdf)) {
      as.numeric(gdf$allocation_residual)
    } else {
      rep(0, length(pov))
    }
    ok <- is.finite(pov) & is.finite(res)
    if ("poverty_n_pixels" %in% names(gdf)) {
      ok <- ok & is.finite(as.numeric(gdf$poverty_n_pixels)) &
        as.numeric(gdf$poverty_n_pixels) > 0
    }
    pov <- pov[ok]
    if (length(pov) < 8) return(NULL)
    q75 <- as.numeric(stats::quantile(pov, 0.75, names = FALSE, type = 7))
    high <- pov >= q75
    if (!any(high) || !any(!high)) return(NULL)
    data.frame(
      City = city,
      Region = as.character(reg),
      n_grdi = length(pov),
      median_grdi = stats::median(pov),
      q75_grdi = q75,
      median_grdi_high = stats::median(pov[high]),
      median_grdi_other = stats::median(pov[!high]),
      grdi_gap = stats::median(pov[high]) - stats::median(pov[!high]),
      stringsAsFactors = FALSE
    )
  })
  df_grdi <- bind_rows(Filter(Negate(is.null), grdi_rows))
  if (nrow(df_grdi) >= 2) {
    df_tg <- fig4_data %>%
      inner_join(df_grdi, by = "City")
    df_tg$sig_lab <- ifelse(df_tg$sig, "p < 0.05", "p >= 0.05")
    df_tg$sig_lab <- factor(df_tg$sig_lab, levels = c("p < 0.05", "p >= 0.05"))
    country_order <- c(
      "Philippines", "Kenya", "Mexico", "Indonesia",
      "Sri Lanka", "Colombia", "Ecuador", "South Africa"
    )
    df_tg$Country <- factor(
      df_tg$Country,
      levels = c(
        intersect(country_order, unique(as.character(df_tg$Country))),
        setdiff(unique(as.character(df_tg$Country)), country_order)
      )
    )
    grdi_csv <- df_tg[, c(
      "Country", "City", "Region", "tau", "SE", "p", "CI_lo", "CI_hi", "sig",
      "n_grdi", "median_grdi", "q75_grdi", "median_grdi_high",
      "median_grdi_other", "grdi_gap"
    )]
    grdi_path <- file.path(tbl_dir, "Table_tau_vs_city_grdi.csv")
    dir.create(tbl_dir, recursive = TRUE, showWarnings = FALSE)
    write.csv(grdi_csv, grdi_path, row.names = FALSE)
    message("Saved: ", grdi_path)

    y_lo <- min(df_tg$CI_lo, na.rm = TRUE)
    y_hi <- max(df_tg$CI_hi, na.rm = TRUE)
    y_pad <- 0.08 * if (y_hi > y_lo) y_hi - y_lo else 1
    theme_tg <- theme_minimal(base_size = 11) +
      theme(
        plot.title = element_text(face = "bold", size = 11, hjust = 0),
        plot.subtitle = element_text(colour = "grey40", size = 9, hjust = 0),
        panel.grid.minor = element_blank(),
        legend.position = "bottom",
        legend.justification = "left",
        legend.box = "vertical"
      )
    scatter_tau_grdi <- function(df, x_col, title, subtitle, xlab) {
      p <- ggplot(df, aes(x = .data[[x_col]], y = tau, colour = Country, shape = sig_lab)) +
        geom_hline(yintercept = 0, linetype = "dashed", colour = "grey55", linewidth = 0.5) +
        geom_linerange(
          aes(ymin = CI_lo, ymax = CI_hi),
          linewidth = 0.45, alpha = 0.7, show.legend = FALSE
        ) +
        geom_point(size = 2.8, stroke = 0.95) +
        scale_colour_manual(
          values = ARMYROSE_COUNTRY, breaks = levels(df$Country), name = NULL
        ) +
        scale_shape_manual(
          values = c("p < 0.05" = 16, "p >= 0.05" = 1), name = NULL
        ) +
        guides(
          colour = guide_legend(override.aes = list(shape = 16, linetype = 0), nrow = 2),
          shape = guide_legend(override.aes = list(colour = "grey30"))
        ) +
        coord_cartesian(ylim = c(y_lo - y_pad, y_hi + y_pad)) +
        labs(title = title, subtitle = subtitle, x = xlab, y = "SEM \u03c4  (high-poverty quartile vs rest)") +
        theme_tg
      if (has_ggrepel) {
        p <- p + ggrepel::geom_text_repel(
          aes(label = City),
          size = 2.45, seed = 1, max.overlaps = Inf,
          min.segment.length = 0.15, box.padding = 0.28, point.padding = 0.25,
          segment.colour = "grey70", segment.size = 0.3,
          show.legend = FALSE
        )
      } else {
        p <- p + geom_text(
          aes(label = City),
          nudge_y = y_pad * 0.35, size = 2.4, show.legend = FALSE
        )
      }
      p
    }
    p_ctx <- scatter_tau_grdi(
      df_tg, "median_grdi",
      "A. City-level deprivation",
      "Same analysis cells as the SEM. No fitted line.",
      "Median GRDI (analysis cells)"
    )
    p_dose <- scatter_tau_grdi(
      df_tg, "grdi_gap",
      "B. Within-city deprivation contrast",
      "Median GRDI of the high-poverty quartile minus the rest.",
      "GRDI gap  (T = 1 \u2212 T = 0)"
    )
    f_tg <- file.path(fig_dir, "03c_tau_vs_city_grdi.png")
    if (has_patchwork) {
      p_tg <- (p_ctx | p_dose) +
        patchwork::plot_layout(guides = "collect") +
        patchwork::plot_annotation(
          title = "Poverty bias vs city deprivation",
          subtitle = "\u03c4 is a within-city contrast (top GRDI quartile vs rest). Left: how deprived the city is. Right: how large that quartile contrast is."
        ) &
        theme(
          legend.position = "bottom",
          plot.title = element_text(face = "bold", size = 12, hjust = 0),
          plot.subtitle = element_text(colour = "grey40", size = 9, hjust = 0)
        )
      ggsave(f_tg, p_tg, width = 11.8, height = 6.4, dpi = 300, bg = "white")
      message("Saved: ", f_tg)
    } else {
      f_ctx <- file.path(fig_dir, "03c_tau_vs_median_grdi.png")
      f_dose <- file.path(fig_dir, "03c_tau_vs_grdi_gap.png")
      ggsave(f_ctx, p_ctx, width = 6.4, height = 5.6, dpi = 300, bg = "white")
      ggsave(f_dose, p_dose, width = 6.4, height = 5.6, dpi = 300, bg = "white")
      message("Saved: ", f_ctx)
      message("Saved: ", f_dose)
    }
  }
}

# ---- 04b crisis inference sensitivity (cross-city) ----
tbl4c_path <- file.path(tbl_dir, "Table4c_crisis_inference_sensitivity.csv")
if (file.exists(tbl4c_path)) {
  t4c <- read.csv(tbl4c_path, stringsAsFactors = FALSE)
  need4c <- c("country", "city", "direction_flip_pct")
  if (all(need4c %in% names(t4c)) && nrow(t4c) > 0) {
    country_order <- c(
      "Philippines", "Kenya", "Mexico", "Indonesia",
      "Sri Lanka", "Colombia", "Ecuador", "South Africa"
    )
    t4c$country <- factor(
      t4c$country,
      levels = c(intersect(country_order, unique(t4c$country)), setdiff(unique(t4c$country), country_order))
    )
    t4c <- t4c[order(t4c$country, t4c$city), ]
    axis_rows <- list()
    city_rows <- list()
    y <- 0
    first_group <- TRUE
    for (country in levels(t4c$country)) {
      sub <- t4c[t4c$country == country, , drop = FALSE]
      if (nrow(sub) == 0) next
      if (!first_group) y <- y - 0.22
      first_group <- FALSE
      hex <- unname(ARMYROSE_COUNTRY[country])
      if (length(hex) != 1 || is.na(hex)) hex <- ARMYROSE[[7]]
      axis_rows[[length(axis_rows) + 1]] <- data.frame(
        y = y, Label = country, label_color = hex, face = "bold",
        stringsAsFactors = FALSE
      )
      y <- y - 0.58
      for (i in seq_len(nrow(sub))) {
        row <- sub[i, ]
        city_rows[[length(city_rows) + 1]] <- data.frame(
          y = y,
          city = row$city,
          country = as.character(row$country),
          hex = hex,
          flip = if ("median_F_t" %in% names(row) && is.finite(as.numeric(row$median_F_t))) {
            as.numeric(row$median_F_t)
          } else {
            as.numeric(row$direction_flip_pct)
          },
          j_inc = if ("jaccard_increase_top10" %in% names(row)) as.numeric(row$jaccard_increase_top10) else NA_real_,
          j_dec = if ("jaccard_decrease_top10" %in% names(row)) as.numeric(row$jaccard_decrease_top10) else NA_real_,
          delta_s = if ("delta_S" %in% names(row)) as.numeric(row$delta_S) else NA_real_,
          delta_f = if ("delta_F" %in% names(row)) as.numeric(row$delta_F) else NA_real_,
          f_min = if ("F_t_min" %in% names(row)) as.numeric(row$F_t_min) else NA_real_,
          f_max = if ("F_t_max" %in% names(row)) as.numeric(row$F_t_max) else NA_real_,
          f_iqr_lo = if ("F_t_iqr_lo" %in% names(row)) as.numeric(row$F_t_iqr_lo) else NA_real_,
          f_iqr_hi = if ("F_t_iqr_hi" %in% names(row)) as.numeric(row$F_t_iqr_hi) else NA_real_,
          stringsAsFactors = FALSE
        )
        axis_rows[[length(axis_rows) + 1]] <- data.frame(
          y = y,
          Label = paste0("  ", row$city),
          label_color = "grey25",
          face = "plain",
          stringsAsFactors = FALSE
        )
        y <- y - 0.70
      }
    }
    axis_df4 <- bind_rows(axis_rows)
    city_df4 <- bind_rows(city_rows)
    h4 <- max(4.8, 0.28 * nrow(axis_df4) + 1.6)
    y_lim <- c(y + 0.28, 0.38)
    theme_04b <- theme_minimal(base_size = 11) +
      theme(
        plot.title = element_text(face = "bold", size = 11, hjust = 0),
        plot.subtitle = element_text(size = 9, colour = "grey35", hjust = 0),
        panel.grid.major.y = element_blank(),
        panel.grid.minor = element_blank(),
        axis.text.y = element_blank(),
        axis.ticks.y = element_blank(),
        legend.position = "bottom",
        legend.justification = "left",
        plot.margin = margin(6, 10, 6, 88)
      )

    xmax_f <- max(c(city_df4$flip, city_df4$f_max), na.rm = TRUE)
    pad_f <- 0.08 * if (is.finite(xmax_f) && xmax_f > 0) xmax_f else 1
    p_flip <- ggplot() +
      geom_segment(
        data = city_df4 %>% filter(is.finite(f_min), is.finite(f_max)),
        aes(x = f_min, xend = f_max, y = y, yend = y),
        colour = "grey70", linewidth = 0.45
      ) +
      geom_segment(
        data = city_df4 %>% filter(is.finite(f_iqr_lo), is.finite(f_iqr_hi)),
        aes(x = f_iqr_lo, xend = f_iqr_hi, y = y, yend = y),
        colour = "grey35", linewidth = 1.35
      ) +
      geom_point(
        data = city_df4,
        aes(x = flip, y = y, colour = hex),
        size = 2.6
      ) +
      geom_text(
        data = axis_df4,
        aes(x = -pad_f * 0.15, y = y, label = Label, colour = label_color, fontface = face),
        hjust = 1, size = 3.05
      ) +
      scale_colour_identity() +
      coord_cartesian(xlim = c(0, xmax_f + pad_f * 1.2), ylim = y_lim, clip = "off") +
      labs(
        title = "A. Direction instability",
        subtitle = "Dot: median daily flip rate. Thick bar: IQR. Thin bar: min\u2013max.",
        x = "Cells changing inferred direction (%)",
        y = NULL
      ) +
      theme_04b

    jac_long <- bind_rows(
      city_df4 %>% transmute(y, hex, val = j_inc, kind = "Increase hotspots"),
      city_df4 %>% transmute(y, hex, val = j_dec, kind = "Decrease hotspots")
    )
    jac_long$kind <- factor(jac_long$kind, levels = c("Increase hotspots", "Decrease hotspots"))
    p_jac <- ggplot() +
      geom_point(
        data = jac_long %>% filter(is.finite(val)),
        aes(x = val, y = y, shape = kind, colour = hex),
        size = 2.5, stroke = 0.9
      ) +
      geom_text(
        data = axis_df4,
        aes(x = -0.04, y = y, label = Label, colour = label_color, fontface = face),
        hjust = 1, size = 3.05
      ) +
      scale_shape_manual(values = c("Increase hotspots" = 16, "Decrease hotspots" = 17), name = NULL) +
      scale_colour_identity() +
      coord_cartesian(xlim = c(0, 1.05), ylim = y_lim, clip = "off") +
      labs(
        title = "B. Crisis hotspot agreement",
        x = expression(J[10]),
        y = NULL
      ) +
      theme_04b

    f_04b2 <- file.path(fig_dir, "04b_cross_city_crisis_sensitivity.png")
    if (has_patchwork) {
      p04b2 <- (p_flip | p_jac) +
        patchwork::plot_annotation(
          title = "Baseline representation substantially changes inferred crisis patterns"
        )
      ggsave(f_04b2, p04b2, width = 13.6, height = h4 + 0.35, dpi = 300, bg = "white")
    } else if (requireNamespace("cowplot", quietly = TRUE)) {
      p04b2 <- cowplot::plot_grid(p_flip, p_jac, ncol = 2, align = "h")
      ggsave(f_04b2, p04b2, width = 13.6, height = h4, dpi = 300, bg = "white")
    } else {
      ggsave(file.path(fig_dir, "04b_direction_instability.png"), p_flip, width = 7.2, height = h4, dpi = 300, bg = "white")
      ggsave(file.path(fig_dir, "04b_hotspot_agreement.png"), p_jac, width = 7.2, height = h4, dpi = 300, bg = "white")
    }
    message("Saved: ", f_04b2)

    if (any(is.finite(city_df4$delta_f))) {
      xmax_fdelta <- max(abs(city_df4$delta_f), na.rm = TRUE)
      pad_fd <- 0.12 * if (is.finite(xmax_fdelta) && xmax_fdelta > 0) xmax_fdelta else 1
      p_df <- ggplot() +
        geom_vline(xintercept = 0, linetype = "dashed", colour = "grey55", linewidth = 0.5) +
        geom_point(
          data = city_df4 %>% filter(is.finite(delta_f)),
          aes(x = delta_f, y = y, colour = hex),
          size = 2.6
        ) +
        geom_text(
          data = axis_df4,
          aes(x = -xmax_fdelta - pad_fd * 0.35, y = y, label = Label, colour = label_color, fontface = face),
          hjust = 1, size = 3.05
        ) +
        scale_colour_identity() +
        coord_cartesian(
          xlim = c(-xmax_fdelta - pad_fd, xmax_fdelta + pad_fd),
          ylim = y_lim,
          clip = "off"
        ) +
        labs(
          title = "Difference in direction-flip probability",
          subtitle = "Positive: deprived cells more likely to change inference. Negative: other cells more likely.",
          x = "\u0394F (percentage points; high deprivation \u2212 other)",
          y = NULL
        ) +
        theme_04b
      f_04b3 <- file.path(fig_dir, "04b_socioeconomic_sensitivity.png")
      ggsave(f_04b3, p_df, width = 8.6, height = h4, dpi = 300, bg = "white")
      message("Saved: ", f_04b3)
    }

    if (any(is.finite(city_df4$delta_s))) {
      xmax_s <- max(abs(city_df4$delta_s), na.rm = TRUE)
      pad_s <- 0.12 * if (is.finite(xmax_s) && xmax_s > 0) xmax_s else 0.05
      p_ds <- ggplot() +
        geom_vline(xintercept = 0, linetype = "dashed", colour = "grey55", linewidth = 0.5) +
        geom_point(
          data = city_df4 %>% filter(is.finite(delta_s)),
          aes(x = delta_s, y = y, colour = hex),
          size = 2.6
        ) +
        geom_text(
          data = axis_df4,
          aes(x = -xmax_s - pad_s * 0.35, y = y, label = Label, colour = label_color, fontface = face),
          hjust = 1, size = 3.05
        ) +
        scale_colour_identity() +
        coord_cartesian(
          xlim = c(-xmax_s - pad_s, xmax_s + pad_s),
          ylim = y_lim,
          clip = "off"
        ) +
        labs(
          title = "Socioeconomic patterning of baseline-induced change-metric divergence",
          subtitle = "S = |G_Meta \u2212 G_WP|; C cancels, so this is baseline discrepancy, not crisis inference",
          x = expression(Delta * S[c] ~ "(high deprivation \u2212 other)"),
          y = NULL
        ) +
        theme_04b
      f_04b_s <- file.path(fig_dir, "04b_baseline_divergence_socioeconomic.png")
      ggsave(f_04b_s, p_ds, width = 8.6, height = h4, dpi = 300, bg = "white")
      message("Saved: ", f_04b_s)
    }
  }
} else {
  message("Table 4c not found; skipping 04b cross-city figures.")
}

message("\nCross-city figures saved to: ", fig_dir)
