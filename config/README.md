# Region configuration

`regions.json` defines data paths and map settings for each study region.

**Pipeline run order, manual commands, and outputs:** see [`pipeline/PIPELINE.md`](../pipeline/PIPELINE.md) (technical reference). This file focuses on **paths and adding regions**.

## Usage

```bash
# Run for Philippines — Cagayan de Oro
./pipeline/run_all.sh --region PHI_CagayandeOroCity

# Run for Philippines — Davao City
./pipeline/run_all.sh --region PHI_DavaoCity

# Run for Kenya (Nairobi or Mombasa)
./pipeline/run_all.sh --region KEN_Nairobi
./pipeline/run_all.sh --region KEN_Mombasa

# Run for Mexico
./pipeline/run_all.sh --region MEX
```

## Path resolution

- **data_root** (top-level): Base path for external data. Paths for `worldpop`, `poverty`, and `pdc_raw_dir` are relative to this.
- **Project paths**: `meta`, `clip_shape`, `pdc_processed_csv` are relative to the project root.
- **meta** includes the reference hour: `outputs/{REGION}/fb_baseline_median_h{00|08|16}.gpkg`. Use the default-hour file for the pipeline, or pass `--meta` to 01_harmonise when using a different hour.
- To use a different data location, change `data_root` only.

## Adding a new region

1. Add an entry to `regions.json`:

```json
"XXX": {
  "name": "Country Name",
  "worldpop": "/path/to/worldpop_raster.tif",
  "meta": "outputs/fb_baseline_median_XXX.gpkg",
  "poverty": "/path/to/rwi_or_poverty.csv",
  "pdc_raw_dir": "/path/to/raw/PDC/CSV/folder",
  "pdc_processed_csv": "outputs/PDC_XXX.csv",
  "pdc_use_baseline_column": false,
  "map_bbox": [xmin, ymin, xmax, ymax],
  "map_bbox_label": "Study area name",
  "lon_range": [min_lon, max_lon],
  "lat_range": [min_lat, max_lat]
}
```

2. Paths can be absolute or relative to the project root.
3. `clip_shape` (optional): path to a shapefile (.shp, .gpkg, or .geojson) to clip the study area. Only quadkeys intersecting this boundary are analysed (e.g. city boundary instead of whole nation). Set to `null` to use full extent. When set, all figures (Python and R) use the clipped data extent instead of `map_bbox`. To extract boundaries from a .gdb geodatabase, use `data_prep/extract_boundary_from_gdb.py`.
4. `lon_range` / `lat_range`: used for auto-detecting region from data centroid.
5. **PDC (Meta baseline)**: `pdc_raw_dir` = folder of raw PDC CSVs; `pdc_processed_csv` = optional intermediate. `pdc_use_baseline_column` (optional): if omitted, auto-detected — data spans 14+ days → 7-day shift; under 14 days → use n_baseline from CSV (if present). Set `true` or `false` to override.

6. **PHI variants**: `PHI_CagayandeOroCity` and `PHI_DavaoCity` share the same WorldPop, poverty, and PDC data; only `clip_shape` differs. Build the Meta baseline once per region (or copy): `python data_prep/build_fb_baseline_median.py --region PHI_CagayandeOroCity` and `--region PHI_DavaoCity`.

## Output layout

With `--region REGION`, outputs go to `outputs/REGION/01/`, `outputs/REGION/02/`, etc.
E.g. `--region PHI_CagayandeOroCity` → `outputs/PHI_CagayandeOroCity/01/`, `outputs/PHI_CagayandeOroCity/02/`, etc.
Without `--region`, outputs use the flat layout `outputs/01/`, `outputs/02/`, etc.
