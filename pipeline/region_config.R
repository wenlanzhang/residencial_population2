# region_config.R — Load map_bbox and region settings from config/regions.json
#
# Usage: source("pipeline/region_config.R") or from project root: source("region_config.R", chdir = TRUE)
#
# get_map_bbox(region_code)     -> c(xmin, ymin, xmax, ymax) or NULL
# get_map_bbox_from_path(path)  -> bbox for region inferred from path (outputs/KEN/02/... -> KEN)
# get_map_bbox_from_data(gdf)   -> bbox for region inferred from data centroid (lon_range, lat_range)
# get_map_bbox_for_plot()       -> when clip_shape is set, uses data extent instead of map_bbox
# coord_from_bbox(bbox)         -> coord_sf for ggplot
# clip_gdf_to_bbox(gdf, bbox)   -> clipped sf object for plotting

project_root <- "/Users/wenlanzhang/PycharmProjects/Residential_population2"
config_path <- file.path(project_root, "config", "regions.json")

#' Load regions.json. Returns list of region configs.
load_regions <- function() {
  if (!file.exists(config_path)) return(list())
  if (!requireNamespace("jsonlite", quietly = TRUE)) {
    warning("jsonlite required for region_config. Install with: install.packages(\"jsonlite\")")
    return(list())
  }
  jsonlite::read_json(config_path, simplifyVector = TRUE)
}

#' Get map_bbox for region code (PHI, KEN, MEX). Returns c(xmin, ymin, xmax, ymax) or NULL.
get_map_bbox <- function(region_code) {
  regions <- load_regions()
  if (is.null(regions) || !region_code %in% names(regions)) return(NULL)
  bbox <- regions[[region_code]]$map_bbox
  if (is.null(bbox) || length(bbox) != 4) return(NULL)
  setNames(as.numeric(bbox), c("xmin", "ymin", "xmax", "ymax"))
}

#' Infer region code from input path. E.g. outputs/KEN/02/harmonised_with_residual.gpkg -> KEN
get_region_from_path <- function(path) {
  parts <- strsplit(path, "[/\\\\]")[[1]]
  idx <- match("outputs", parts)
  if (is.na(idx) || idx >= length(parts)) return(NULL)
  cand <- parts[idx + 1]
  regions <- load_regions()
  if (!is.null(regions) && cand %in% names(regions)) return(cand)
  # Backward compat: KEN -> KEN_Nairobi
  if (cand == "KEN") return("KEN_Nairobi")
  if (toupper(cand) %in% c("PHI", "MEX", "PRT")) return(toupper(cand))
  NULL
}

#' Infer region from data centroid using lon_range/lat_range in config.
get_region_from_data <- function(gdf) {
  if (!inherits(gdf, "sf")) return(NULL)
  b <- sf::st_bbox(gdf)
  clon <- (b["xmin"] + b["xmax"]) / 2
  clat <- (b["ymin"] + b["ymax"]) / 2
  regions <- load_regions()
  if (is.null(regions)) return(NULL)
  for (code in names(regions)) {
    if (code == "data_root") next
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
#' When clip_shape is set for the region: uses data extent (data is already clipped) instead of map_bbox.
get_map_bbox_for_plot <- function(region_arg = NULL, input_path = NULL, gdf = NULL) {
  regions <- load_regions()
  reg <- NULL
  if (!is.null(region_arg) && nzchar(region_arg)) reg <- toupper(region_arg)
  if (is.null(reg) && !is.null(input_path)) reg <- get_region_from_path(input_path)
  if (is.null(reg) && !is.null(gdf)) reg <- get_region_from_data(gdf)
  # When clip_shape is set: use data extent (data is already clipped to study area)
  if (!is.null(reg) && reg %in% names(regions) && !is.null(regions[[reg]]$clip_shape) &&
      !is.null(gdf) && inherits(gdf, "sf") && nrow(gdf) > 0) {
    return(as.numeric(sf::st_bbox(gdf)))
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
