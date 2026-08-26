# region_config.R — Load map_bbox and region settings from config/regions.json
#
# Usage: source("pipeline/region_config.R") or from project root: source("region_config.R", chdir = TRUE)
#
# get_map_bbox(region_code)     -> c(xmin, ymin, xmax, ymax) or NULL
# get_map_bbox_from_path(path)  -> bbox for region inferred from path (outputs/KEN/02/... -> KEN)
# get_map_bbox_from_data(gdf)   -> bbox for region inferred from data centroid (lon_range, lat_range)
# get_map_bbox_for_plot()       -> when a city clip is set, uses data extent instead of map_bbox
# coord_from_bbox(bbox)         -> coord_sf for ggplot
# clip_gdf_to_bbox(gdf, bbox)   -> clipped sf object for plotting

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
config_path <- file.path(project_root, "config", "regions.json")
GLOBAL_KEYS <- c("data_root", "poverty_source", "poverty_grdi", "clip_source", "footprints", "ghsl_smod", "ghsl_ucdb")

#' Load regions.json. Returns list of region configs.
load_regions <- function() {
  if (!file.exists(config_path)) return(list())
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    warning("jsonlite required for region_config. Install with: install.packages(\"jsonlite\")")
    return(list())
  }
  jsonlite::read_json(config_path, simplifyVector = TRUE)
}

#' Region codes only (excludes top-level config keys).
region_codes <- function(regions = NULL) {
  if (is.null(regions)) regions <- load_regions()
  setdiff(names(regions), GLOBAL_KEYS)
}

#' Get map_bbox for region code (PHL_CagayandeOroCity, KEN_Nairobi, MEX). Returns c(xmin, ymin, xmax, ymax) or NULL.
get_map_bbox <- function(region_code) {
  regions <- load_regions()
  if (is.null(regions) || !region_code %in% region_codes(regions)) return(NULL)
  bbox <- regions[[region_code]]$map_bbox
  if (is.null(bbox) || length(bbox) != 4) return(NULL)
  setNames(as.numeric(bbox), c("xmin", "ymin", "xmax", "ymax"))
}

#' Infer region code from a pipeline artifact path
#' (outputs|figure|data/processed)/city/COUNTRY/CITY/...
get_region_from_path <- function(path) {
  region_from_artifact_path(path)
}

layout_parts <- function(code) {
  country <- sub("_.*$", "", code)
  if (grepl("_", code)) {
    return(list(country = country, place = sub("^[^_]+_", "", code)))
  }
  list(country = country, place = code)
}

region_from_layout <- function(country, place) {
  if (identical(place, country)) return(country)
  paste0(country, "_", place)
}

region_from_artifact_path <- function(path) {
  if (is.null(path) || !nzchar(path)) return(NULL)
  parts <- strsplit(path, "[/\\\\]")[[1]]
  reserved <- c("city", "footprints", "cross-city", "cross-country", "paper", "_archive", "_snapshots", "qa", "meta", "geographies")
  for (root in c("outputs", "figure", "processed")) {
    idx <- match(root, parts)
    if (is.na(idx) || (idx + 1) > length(parts)) next
    nxt <- parts[[idx + 1]]
    if (identical(nxt, "city") && (idx + 3) <= length(parts)) {
      country <- parts[[idx + 2]]
      place <- parts[[idx + 3]]
    } else if (identical(nxt, "footprints") && (idx + 2) <= length(parts)) {
      code <- parts[[idx + 2]]
      if (!code %in% c("qa", "meta")) return(code)
      next
    } else if (nxt %in% reserved) {
      next
    } else if ((idx + 2) <= length(parts)) {
      country <- parts[[idx + 1]]
      place <- parts[[idx + 2]]
    } else {
      next
    }
    if (place %in% c("01", "02", "cross-city") || place %in% reserved) next
    return(region_from_layout(country, place))
  }
  NULL
}

csv_dir <- function(code, step = NULL) {
  p <- layout_parts(code)
  d <- file.path(project_root, "outputs", "city", p$country, p$place)
  if (!is.null(step)) d <- file.path(d, step)
  d
}

figure_dir <- function(code, step = NULL) {
  p <- layout_parts(code)
  d <- file.path(project_root, "figure", "city", p$country, p$place)
  if (!is.null(step)) d <- file.path(d, step)
  d
}

geo_dir <- function(code, step = NULL) {
  p <- layout_parts(code)
  d <- file.path(project_root, "data", "processed", "city", p$country, p$place)
  if (!is.null(step)) d <- file.path(d, step)
  d
}

find_artifact <- function(code, step, filename) {
  ext <- tolower(tools::file_ext(filename))
  p <- layout_parts(code)
  if (ext %in% c("gpkg", "shp", "geojson", "tif", "tiff")) {
    candidates <- c(
      file.path(geo_dir(code, step), filename),
      file.path(project_root, "data", "processed", p$country, p$place, step, filename)
    )
  } else if (ext %in% c("png", "pdf", "svg", "jpg", "jpeg")) {
    candidates <- c(
      file.path(figure_dir(code, step), filename),
      file.path(project_root, "figure", p$country, p$place, step, filename)
    )
  } else {
    candidates <- c(
      file.path(csv_dir(code, step), filename),
      file.path(project_root, "outputs", p$country, p$place, step, filename)
    )
  }
  candidates <- c(candidates, file.path(project_root, "outputs", code, step, filename))
  for (path in candidates) {
    if (file.exists(path)) return(path)
  }
  NULL
}

footprint_figure_dir <- function(code, step = NULL) {
  d <- file.path(project_root, "figure", "footprints", code)
  if (!is.null(step)) d <- file.path(d, step)
  d
}

footprint_csv_dir <- function(code, step = NULL) {
  d <- file.path(project_root, "outputs", "footprints", code)
  if (!is.null(step)) d <- file.path(d, step)
  d
}

footprint_geo_dir <- function(code, step = NULL) {
  d <- file.path(project_root, "data", "processed", "footprints", code)
  if (!is.null(step)) d <- file.path(d, step)
  d
}

#' Footprint artifacts: outputs/figure/data/processed/footprints/{CODE}/{step}/.
find_footprint_artifact <- function(code, step, filename) {
  ext <- tolower(tools::file_ext(filename))
  if (ext %in% c("gpkg", "shp", "geojson", "tif", "tiff")) {
    candidates <- c(
      file.path(footprint_geo_dir(code, step), filename),
      file.path(project_root, "outputs", "footprints", code, step, filename)
    )
  } else if (ext %in% c("png", "pdf", "svg", "jpg", "jpeg")) {
    candidates <- c(file.path(footprint_figure_dir(code, step), filename))
  } else {
    candidates <- c(file.path(footprint_csv_dir(code, step), filename))
  }
  for (path in candidates) {
    if (file.exists(path)) return(path)
  }
  NULL
}

footprint_code_from_path <- function(path) {
  if (is.null(path) || !nzchar(path)) return(NULL)
  parts <- strsplit(path, "[/\\\\]")[[1]]
  idx <- match("footprints", parts)
  if (is.na(idx) || (idx + 1) > length(parts)) return(NULL)
  code <- parts[[idx + 1]]
  if (code %in% c("qa", "meta")) return(NULL)
  code
}

#' Figure folder for a plot script. Prefer --footprint / --region, then infer from -i path.
resolve_plot_out_dir <- function(region_arg, in_path, step, o_arg = NULL, footprint_arg = NULL) {
  if (!is.null(o_arg) && nzchar(o_arg)) return(o_arg)
  if (!is.null(footprint_arg) && nzchar(footprint_arg)) {
    return(footprint_figure_dir(footprint_arg, step))
  }
  fp <- footprint_code_from_path(in_path)
  if (!is.null(fp)) return(footprint_figure_dir(fp, step))
  if (!is.null(region_arg) && nzchar(region_arg)) return(figure_dir(region_arg, step))
  inf <- region_from_artifact_path(in_path)
  if (!is.null(inf)) {
    fp2 <- footprint_code_from_path(in_path)
    if (!is.null(fp2)) return(footprint_figure_dir(fp2, step))
    return(figure_dir(inf, step))
  }
  if (!is.null(in_path) && dir.exists(in_path)) return(in_path)
  if (!is.null(in_path)) return(dirname(in_path))
  file.path(project_root, "figure")
}

#' Infer region from data centroid using lon_range/lat_range in config.
get_region_from_data <- function(gdf) {
  if (!inherits(gdf, "sf")) return(NULL)
  b <- sf::st_bbox(gdf)
  clon <- (b["xmin"] + b["xmax"]) / 2
  clat <- (b["ymin"] + b["ymax"]) / 2
  regions <- load_regions()
  if (is.null(regions)) return(NULL)
  for (code in region_codes(regions)) {
    cfg <- regions[[code]]
    lon_r <- cfg$lon_range
    lat_r <- cfg$lat_range
    if (length(lon_r) == 2 && length(lat_r) == 2) {
      if (lon_r[1] <= clon && clon <= lon_r[2] && lat_r[1] <= clat && clat <= lat_r[2]) {
        return(code)
      }
    }
  }
  NULL
}

#' Get map_bbox: first from region arg, then from path, then from data. Returns named vector or NULL.
#' When a city clip is configured: uses data extent (data is already clipped) instead of map_bbox.
get_map_bbox_for_plot <- function(region_arg = NULL, input_path = NULL, gdf = NULL, footprint_arg = NULL) {
  bbox_from_gdf <- function(x) {
    bb <- sf::st_bbox(x)
    stats::setNames(as.numeric(bb), c("xmin", "ymin", "xmax", "ymax"))
  }
  if (!is.null(footprint_arg) && nzchar(footprint_arg) && !is.null(gdf) && inherits(gdf, "sf") && nrow(gdf) > 0) {
    return(bbox_from_gdf(gdf))
  }
  if (!is.null(input_path) && grepl("footprints", input_path, fixed = TRUE) &&
      !is.null(gdf) && inherits(gdf, "sf") && nrow(gdf) > 0) {
    return(bbox_from_gdf(gdf))
  }
  regions <- load_regions()
  reg <- NULL
  if (!is.null(region_arg) && nzchar(region_arg)) reg <- toupper(region_arg)
  if (is.null(reg) && !is.null(input_path)) reg <- get_region_from_path(input_path)
  if (is.null(reg) && !is.null(gdf)) reg <- get_region_from_data(gdf)
  # When the region is clipped (local file or OSM/geoBoundaries): use data extent
  if (!is.null(reg) && reg %in% names(regions) && !is.null(gdf) && inherits(gdf, "sf") && nrow(gdf) > 0) {
    clip_src <- regions[[reg]]$clip_source
    if (is.null(clip_src)) clip_src <- regions$clip_source
    has_local <- !is.null(regions[[reg]]$clip_shape)
    has_online <- !is.null(clip_src) && clip_src %in% c("osm", "geob")
    if (has_local || has_online) {
      return(as.numeric(sf::st_bbox(gdf)))
    }
  }
  # 1. Explicit --region
  if (!is.null(reg)) {
    bbox <- get_map_bbox(reg)
    if (!is.null(bbox)) return(bbox)
  }
  # 2. From path (outputs/KEN/02/...)
  if (!is.null(input_path) && is.null(reg)) {
    reg <- get_region_from_path(input_path)
    if (!is.null(reg)) {
      bbox <- get_map_bbox(reg)
      if (!is.null(bbox)) return(bbox)
    }
  }
  # 3. From data centroid
  if (!is.null(gdf) && is.null(reg)) {
    reg <- get_region_from_data(gdf)
    if (!is.null(reg)) {
      bbox <- get_map_bbox(reg)
      if (!is.null(bbox)) return(bbox)
    }
  }
  NULL
}

#' Create coord_sf for ggplot from bbox. If bbox is NULL, returns coord_sf(expand = FALSE).
coord_from_bbox <- function(bbox) {
  if (is.null(bbox) || length(bbox) != 4) {
    return(ggplot2::coord_sf(expand = FALSE))
  }
  ggplot2::coord_sf(
    xlim = bbox[c("xmin", "xmax")],
    ylim = bbox[c("ymin", "ymax")],
    expand = FALSE
  )
}

#' Clip gdf to bbox for map plotting. Returns clipped sf or full gdf if bbox is NULL.
clip_gdf_to_bbox <- function(gdf, bbox) {
  if (is.null(bbox) || length(bbox) != 4 || !inherits(gdf, "sf")) return(gdf)
  xmin <- as.numeric(bbox["xmin"])
  ymin <- as.numeric(bbox["ymin"])
  xmax <- as.numeric(bbox["xmax"])
  ymax <- as.numeric(bbox["ymax"])
  if (any(is.na(c(xmin, ymin, xmax, ymax)))) return(gdf)
  # Create polygon from bbox (closed ring: 5 points)
  m <- matrix(c(xmin, ymin, xmax, ymin, xmax, ymax, xmin, ymax, xmin, ymin), ncol = 2, byrow = TRUE)
  clip <- sf::st_sfc(sf::st_polygon(list(m)), crs = 4326)
  clip <- sf::st_transform(clip, sf::st_crs(gdf))
  tmp <- suppressWarnings(sf::st_intersection(gdf, sf::st_union(clip)))
  if (nrow(tmp) > 0) tmp else gdf
}

ARMYROSE <- c("#798234", "#A3AD62", "#D0D3A2", "#FDFBE4", "#F0C6C3", "#DF91A3", "#D46780")
ARMYROSE_CAT <- ARMYROSE[c(1, 2, 3, 5, 6, 7)]
COUNTRY_LABEL <- c(
  PHL = "Philippines", KEN = "Kenya", MEX = "Mexico", IDN = "Indonesia",
  LKA = "Sri Lanka", COL = "Colombia", ECU = "Ecuador", ZAF = "South Africa"
)
ARMYROSE_COUNTRY <- c(
  Kenya = ARMYROSE[1],
  Philippines = ARMYROSE[7],
  Mexico = ARMYROSE[2],
  Indonesia = ARMYROSE[6],
  "Sri Lanka" = ARMYROSE[3],
  Colombia = ARMYROSE[5],
  Ecuador = "#5F6E28",
  "South Africa" = "#A33A58"
)

country_display_name <- function(code) {
  pref <- sub("_.*$", "", as.character(code)[1])
  lab <- unname(COUNTRY_LABEL[pref])
  if (length(lab) == 1 && !is.na(lab)) lab else pref
}

#' City label from config (e.g. "Cartagena", "General Santos").
city_display_label <- function(code) {
  regions <- load_regions()
  if (is.null(code) || !nzchar(code) || !code %in% names(regions)) return(code)
  lab <- regions[[code]]$city_label
  if (!is.null(lab) && nzchar(as.character(lab)[1])) return(as.character(lab)[1])
  code
}

utm_epsg <- function(gdf) {
  g <- sf::st_transform(gdf, 4326)
  b <- sf::st_bbox(g)
  clon <- as.numeric((b["xmin"] + b["xmax"]) / 2)
  clat <- as.numeric((b["ymin"] + b["ymax"]) / 2)
  zone <- max(1, min(60, floor((clon + 180) / 6) + 1))
  if (clat >= 0) 32600 + zone else 32700 + zone
}

#' Allocation residual choropleth (log meta/WP share). Same style as cross-city Figure 3.
plot_allocation_residual_map <- function(gdf, title = NULL) {
  resid_col <- if ("allocation_residual" %in% names(gdf)) {
    "allocation_residual"
  } else if ("allocation_log_ratio" %in% names(gdf)) {
    "allocation_log_ratio"
  } else {
    return(NULL)
  }
  gdf <- gdf[!is.na(gdf[[resid_col]]), ]
  if (nrow(gdf) == 0) return(NULL)
  v <- gdf[[resid_col]]
  vlim <- max(abs(range(v, na.rm = TRUE)), 0.5)
  vlim <- min(vlim, 2)
  crs_epsg <- utm_epsg(gdf)
  gdf_proj <- sf::st_transform(gdf, crs_epsg)
  gdf_proj$fill_resid <- pmin(pmax(gdf_proj[[resid_col]], -vlim), vlim)
  p <- ggplot2::ggplot(gdf_proj) +
    ggplot2::geom_sf(ggplot2::aes(fill = fill_resid), colour = NA) +
    ggplot2::geom_sf(data = gdf_proj, fill = NA, colour = "gray85", linewidth = 0.15) +
    ggplot2::scale_fill_gradientn(
      colours = ARMYROSE,
      values = seq(0, 1, length.out = 7),
      limits = c(-vlim, vlim), oob = scales::squish,
      name = expression(log(meta / wp))
    ) +
    ggplot2::coord_sf(
      crs = crs_epsg,
      datum = sf::st_crs(4326),
      label_graticule = "SW",
      label_axes = "SW"
    ) +
    ggplot2::labs(title = title) +
    ggplot2::theme_void() +
    ggplot2::theme(
      plot.title = ggplot2::element_text(face = "bold", hjust = 0.5, size = 11),
      legend.position = "bottom",
      legend.direction = "horizontal",
      legend.key.width = grid::unit(1.2, "cm"),
      legend.key.height = grid::unit(0.4, "cm"),
      panel.border = ggplot2::element_rect(fill = NA, colour = "gray30", linewidth = 0.8),
      axis.text = ggplot2::element_text(size = 7, colour = "gray30"),
      axis.ticks = ggplot2::element_line(colour = "gray50", linewidth = 0.3),
      axis.ticks.length = grid::unit(0.1, "cm")
    )
  bbox <- sf::st_bbox(gdf_proj)
  x_extent <- as.numeric(bbox["xmax"] - bbox["xmin"])
  y_extent <- as.numeric(bbox["ymax"] - bbox["ymin"])
  pad_frac <- 0.04
  scale_x0 <- as.numeric(bbox["xmin"]) + x_extent * pad_frac
  scale_y0 <- as.numeric(bbox["ymin"]) + y_extent * pad_frac
  scale_x1 <- scale_x0 + 10000
  p <- p +
    ggplot2::annotate(
      "segment", x = scale_x0, xend = scale_x1, y = scale_y0, yend = scale_y0,
      colour = "gray30", linewidth = 0.8
    ) +
    ggplot2::annotate(
      "text", x = (scale_x0 + scale_x1) / 2, y = scale_y0,
      label = "10 km", vjust = -0.8, size = 2.8, colour = "gray30"
    )
  if (requireNamespace("ggspatial", quietly = TRUE)) {
    p <- p +
      ggspatial::annotation_north_arrow(
        location = "tr",
        which_north = "true",
        height = grid::unit(0.9, "cm"),
        width = grid::unit(0.9, "cm"),
        style = ggspatial::north_arrow_orienteering
      )
  }
  p
}
