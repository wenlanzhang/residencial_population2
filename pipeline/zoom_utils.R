# zoom_utils.R — Shared Philippines zoom for map figures
# Use: source("pipeline/zoom_utils.R") or paste into pipeline scripts that produce maps
#
# Philippines Mindanao: center 7.0647° N, 125.6088° E, buffer ±0.6°

PHILIPPINES_CENTER_LAT <- 7.0647
PHILIPPINES_CENTER_LON <- 125.6088
PHILIPPINES_BUFFER <- 0.6
PHILIPPINES_BBOX <- c(
  xmin = PHILIPPINES_CENTER_LON - PHILIPPINES_BUFFER,
  ymin = PHILIPPINES_CENTER_LAT - PHILIPPINES_BUFFER,
  xmax = PHILIPPINES_CENTER_LON + PHILIPPINES_BUFFER,
  ymax = PHILIPPINES_CENTER_LAT + PHILIPPINES_BUFFER
)

#' Create coord_sf for Philippines zoom
coord_philippines <- function() {
  coord_sf(
    xlim = PHILIPPINES_BBOX[c("xmin", "xmax")],
    ylim = PHILIPPINES_BBOX[c("ymin", "ymax")],
    expand = FALSE
  )
}

#' Create clip geometry for Philippines (for zoom-first, legend from zoomed data)
#' Returns an sfc object
create_philippines_clip <- function(target_crs) {
  bb <- st_bbox(c(
    xmin = as.numeric(PHILIPPINES_BBOX["xmin"]),
    ymin = as.numeric(PHILIPPINES_BBOX["ymin"]),
    xmax = as.numeric(PHILIPPINES_BBOX["xmax"]),
    ymax = as.numeric(PHILIPPINES_BBOX["ymax"])
  ))
  clip_poly <- st_as_sfc(bb)
  clip_poly <- st_set_crs(clip_poly, 4326)
  st_transform(clip_poly, target_crs)
}

#' Detect region from data centroid (lon 118-127, lat 5-20 = Philippines)
detect_region <- function(gdf) {
  b <- st_bbox(gdf)
  centroid_lon <- (b["xmin"] + b["xmax"]) / 2
  centroid_lat <- (b["ymin"] + b["ymax"]) / 2
  if (centroid_lon >= 118 && centroid_lon <= 127 && centroid_lat >= 5 && centroid_lat <= 20) {
    "philippines"
  } else {
    "full"
  }
}

#' Get plot data: zoomed (clipped) when Philippines, else full. Calculations use full data.
get_plot_data <- function(gdf_full, region = NULL) {
  if (is.null(region)) region <- detect_region(gdf_full)
  if (region != "philippines") return(gdf_full)
  clip_union <- st_union(create_philippines_clip(st_crs(gdf_full)))
  tmp <- suppressWarnings(st_intersection(gdf_full, clip_union))
  if (nrow(tmp) > 0) tmp else gdf_full
}
