#!/bin/bash
# Run the full analysis pipeline in correct order.
#
# NOTE: If you get "zsh: number expected", run with:  ./run --region KEN
#       (Avoid copying comments with parentheses — they can confuse zsh)
if [ -n "${ZSH_VERSION:-}" ]; then
  exec /bin/bash "$0" "$@"
fi
# Usage: ./pipeline/run_all.sh --region COUNTRY [--all] [options]
#   --region COUNTRY  All selected cities in that country:
#                     PHI, KEN, MEX, IDN, LKA, COL, ECU, ZAF
#   --region COUNTRY --all
#                     Unclipped Meta extract (all cells). IDN, LKA, COL, ECU, ZAF only.
#   --all             All selected cities in every country (no event extracts)
#   --one CODE        Internal / resume: run a single city or extract folder
#   --no-basemap --ref-hour --poverty-source --clip-source --clip-refresh --start-from
# Missing Meta baseline GPKGs are built from the PDC zip before step 01.

set -e
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
SCRIPTS="$PROJECT_ROOT/pipeline"
PYTHON="${PYTHON:-python}"

# Parse optional args
R_ARGS=()
REGION=""
ONE=""
RUN_ALL=false
START_FROM=""
REF_HOUR=""
POVERTY_SOURCE=""
CLIP_SOURCE=""
CLIP_REFRESH=false
PASSTHROUGH=()
USAGE="Usage: $0 --region COUNTRY [--all] [--no-basemap] [--ref-hour HOUR] [--poverty-source grdi|rwi] [--clip-source local|osm|geob] [--start-from STEP]
  COUNTRY: PHI, KEN, MEX, IDN, LKA, COL, ECU, ZAF
  --region COUNTRY       all selected cities in that country
  --region COUNTRY --all unclipped Meta extract (all cells); IDN, LKA, COL, ECU, ZAF
  --all                  all selected cities in every country"
while [[ $# -gt 0 ]]; do
  case $1 in
    --no-basemap)
      R_ARGS+=(--no-basemap)
      PASSTHROUGH+=(--no-basemap)
      shift
      ;;
    --ref-hour)
      REF_HOUR="$2"
      PASSTHROUGH+=(--ref-hour "$2")
      shift 2
      ;;
    --poverty-source)
      POVERTY_SOURCE="$2"
      PASSTHROUGH+=(--poverty-source "$2")
      shift 2
      ;;
    --clip-source)
      CLIP_SOURCE="$2"
      PASSTHROUGH+=(--clip-source "$2")
      shift 2
      ;;
    --clip-refresh)
      CLIP_REFRESH=true
      PASSTHROUGH+=(--clip-refresh)
      shift
      ;;
    --region)
      REGION="$2"
      shift 2
      ;;
    --one)
      ONE="$2"
      shift 2
      ;;
    --all)
      RUN_ALL=true
      shift
      ;;
    --start-from)
      START_FROM="$2"
      PASSTHROUGH+=(--start-from "$2")
      shift 2
      ;;
    *)
      echo "Unknown option: $1"
      echo "$USAGE"
      exit 1
      ;;
  esac
done

_run_each() {
  local label="$1"
  shift
  echo "=========================================="
  echo "$label"
  echo "=========================================="
  local r
  for r in "$@"; do
    echo ""
    echo ">>> Region: $r <<<"
    /bin/bash "$0" --one "$r" "${PASSTHROUGH[@]}"
  done
  echo ""
  echo "=========================================="
  echo "Pipeline complete."
  echo "=========================================="
}

# Single folder (internal / resume). Do not expand.
if [[ -n "$ONE" ]]; then
  REGION="$ONE"
elif [[ -n "$REGION" && "$REGION" == *_* ]]; then
  prefix="${REGION%%_*}"
  echo "Error: '$REGION' is a city code. Use --region $prefix for all selected cities in that country."
  echo "  Resume one folder only if needed:  ./run --one $REGION"
  exit 1
elif [[ "$RUN_ALL" == true && -z "$REGION" ]]; then
  REGIONS=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/pipeline')
import region_config
print(' '.join(region_config.list_cities()))
")
  _run_each "Running pipeline for all selected cities: $REGIONS" $REGIONS
  exit 0
elif [[ -n "$REGION" ]]; then
  EVENT_PY=False
  [[ "$RUN_ALL" == true ]] && EVENT_PY=True
  REGIONS=$("$PYTHON" -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT/pipeline')
import region_config
try:
    matches = region_config.expand_region_to_list('$REGION', event=$EVENT_PY)
except ValueError as e:
    print(e, file=sys.stderr)
    sys.exit(1)
if not matches:
    sys.exit(1)
print(' '.join(matches))
")
  if [[ $? -ne 0 || -z "$REGIONS" ]]; then
    echo "Error: No run for --region $REGION. Use PHI, KEN, MEX, IDN, LKA, COL, ECU, or ZAF."
    echo "  Unclipped extract: ./run --region IDN --all   (also LKA, COL, ECU, ZAF)"
    exit 1
  fi
  REGION_COUNT=$(echo "$REGIONS" | wc -w | tr -d ' ')
  if [[ "$REGION_COUNT" -gt 1 ]]; then
    _run_each "Running pipeline for $REGION ($REGION_COUNT cities): $REGIONS" $REGIONS
    exit 0
  else
    REGION="$REGIONS"
  fi
fi

# Output paths: CSVs under outputs/{country}/{city|full}/, figures under figure/...
if [[ -n "$REGION" ]]; then
  eval "$("$PYTHON" -c "
import sys
sys.path.insert(0, r'$PROJECT_ROOT/pipeline')
import region_config as rc
r = '$REGION'
print('CSV_ROOT=' + str(rc.csv_dir(r)))
print('FIG_ROOT=' + str(rc.figure_dir(r)))
print('GEO_ROOT=' + str(rc.geo_dir(r)))
print('GPKG_01=' + str(rc.geo_dir(r, '01') / 'harmonised_meta_worldpop.gpkg'))
print('GPKG_02=' + str(rc.geo_dir(r, '02') / 'harmonised_with_residual.gpkg'))
print('CSV_03a=' + str(rc.csv_dir(r, '03a_regression')))
print('CSV_03b=' + str(rc.csv_dir(r, '03b_stratified')))
print('GEO_03c=' + str(rc.geo_dir(r, '03c_spatial_regression')))
print('CSV_03e=' + str(rc.csv_dir(r, '03e_causal')))
print('CSV_03f=' + str(rc.csv_dir(r, '03f_robustness')))
print('CSV_04=' + str(rc.csv_dir(r, '04_impact')))
print('OUT_ROOT=' + str(rc.csv_dir(r)))
")"
  R_REGION_ARGS=(--region "$REGION")
else
  CSV_ROOT="$PROJECT_ROOT/outputs"
  FIG_ROOT="$PROJECT_ROOT/figure"
  GEO_ROOT="$PROJECT_ROOT/data/processed"
  GPKG_01="$GEO_ROOT/01/harmonised_meta_worldpop.gpkg"
  GPKG_02="$GEO_ROOT/02/harmonised_with_residual.gpkg"
  CSV_03a="$CSV_ROOT/03a_regression"
  CSV_03b="$CSV_ROOT/03b_stratified"
  GEO_03c="$GEO_ROOT/03c_spatial_regression"
  CSV_03e="$CSV_ROOT/03e_causal"
  CSV_03f="$CSV_ROOT/03f_robustness"
  CSV_04="$CSV_ROOT/04_impact"
  OUT_ROOT="$CSV_ROOT"
  R_REGION_ARGS=()
fi

# Steps in order: 01 < 02 < 04 < 03a < 03b < 03c < 03d < 03e < 03f
_run_step() {
  local step="$1"
  if [ -z "$START_FROM" ]; then
    return 0
  fi
  case "$START_FROM" in
    01|02|04|03a|03b|03c|03d|03e|03f) ;;
    *) echo "Unknown --start-from: $START_FROM (use: 01, 02, 04, 03a, 03b, 03c, 03d, 03e, 03f)"; exit 1 ;;
  esac
  # Skip if this step is before START_FROM (case-based, no arithmetic)
  case "$step" in
    01) case "$START_FROM" in 02|04|03a|03b|03c|03d|03e|03f) return 1 ;; esac ;;
    02) case "$START_FROM" in 04|03a|03b|03c|03d|03e|03f) return 1 ;; esac ;;
    04) case "$START_FROM" in 03a|03b|03c|03d|03e|03f) return 1 ;; esac ;;
    03a) case "$START_FROM" in 03b|03c|03d|03e|03f) return 1 ;; esac ;;
    03b) case "$START_FROM" in 03c|03d|03e|03f) return 1 ;; esac ;;
    03c) case "$START_FROM" in 03d|03e|03f) return 1 ;; esac ;;
    03d) case "$START_FROM" in 03e|03f) return 1 ;; esac ;;
    03e) case "$START_FROM" in 03f) return 1 ;; esac ;;
  esac
  return 0
}

echo "=========================================="
echo "Residential Population Pipeline"
echo "=========================================="
[[ -n "$REGION" ]] && echo "Region: $REGION" && echo "  CSVs:     $OUT_ROOT/" && echo "  figures:  $FIG_ROOT/" && echo "  GPKGs:    $GEO_ROOT/" && echo ""
[[ -n "$REF_HOUR" ]] && echo "Ref hour: $REF_HOUR (fb_baseline_median_h$(printf '%02d' "$REF_HOUR").gpkg)" && echo ""
[[ -n "$POVERTY_SOURCE" ]] && echo "Poverty source: $POVERTY_SOURCE" && echo ""
[[ -n "$CLIP_SOURCE" ]] && echo "Clip source: $CLIP_SOURCE" && echo ""
[[ -n "$START_FROM" ]] && echo "Starting from step: $START_FROM" && echo ""

# 0. Meta baseline — build from the PDC zip if the GPKG is not there yet
if [[ -n "$REGION" ]] && _run_step "01"; then
  if [[ -n "$REF_HOUR" ]]; then
    META_GPKG=$("$PYTHON" -c "
import sys
sys.path.insert(0, r'$PROJECT_ROOT/pipeline')
import region_config
print(region_config.baseline_path('$REGION', int('$REF_HOUR')))
")
  else
    META_GPKG=$("$PYTHON" -c "
import sys
sys.path.insert(0, r'$PROJECT_ROOT/pipeline')
import region_config
cfg = region_config.get_region_config('$REGION')
print(cfg['meta'])
")
  fi
  if [[ ! -f "$META_GPKG" ]]; then
    echo ""
    echo "[0/15] Meta baseline missing — building from PDC zip..."
    BUILD_ARGS=(--region "$REGION" -o "$META_GPKG")
    [[ -n "$REF_HOUR" ]] && BUILD_ARGS+=(--ref-hour "$REF_HOUR")
    "$PYTHON" "$PROJECT_ROOT/data_prep/build_fb_baseline_median.py" "${BUILD_ARGS[@]}"
  else
    echo ""
    echo "[0/15] Meta baseline present: $META_GPKG"
  fi
fi

# 1. Harmonise
if _run_step "01"; then
  echo ""
  echo "[1/15] Harmonising datasets..."
  if [[ -n "$REGION" ]]; then
    HARMONISE_ARGS=(--region "$REGION")
    [[ -n "$REF_HOUR" ]] && HARMONISE_ARGS+=(--ref-hour "$REF_HOUR")
    [[ -n "$POVERTY_SOURCE" ]] && HARMONISE_ARGS+=(--poverty-source "$POVERTY_SOURCE")
    [[ -n "$CLIP_SOURCE" ]] && HARMONISE_ARGS+=(--clip-source "$CLIP_SOURCE")
    [[ "$CLIP_REFRESH" == true ]] && HARMONISE_ARGS+=(--clip-refresh)
    "$PYTHON" "$SCRIPTS/01_harmonise_datasets.py" "${HARMONISE_ARGS[@]}"
  else
    HARMONISE_ARGS=()
    [[ -n "$POVERTY_SOURCE" ]] && HARMONISE_ARGS+=(--poverty-source "$POVERTY_SOURCE")
    [[ -n "$CLIP_SOURCE" ]] && HARMONISE_ARGS+=(--clip-source "$CLIP_SOURCE")
    [[ "$CLIP_REFRESH" == true ]] && HARMONISE_ARGS+=(--clip-refresh)
    "$PYTHON" "$SCRIPTS/01_harmonise_datasets.py" "${HARMONISE_ARGS[@]}"
  fi
else
  echo ""
  echo "[1/15] Harmonise skipped (--start-from $START_FROM)"
fi

# 1b. Descriptive plots
if _run_step "02"; then
  echo ""
  echo "[2/15] Descriptive plots (01_plot_descriptive.R)..."
  Rscript "$SCRIPTS/01_plot_descriptive.R" -i "$GPKG_01" "${R_REGION_ARGS[@]}" "${R_ARGS[@]}"
else
  echo ""
  echo "[2/15] Descriptive plots skipped"
fi

# 2. Compare Meta vs WorldPop
if _run_step "02"; then
  echo ""
  echo "[3/15] Comparing Meta vs WorldPop..."
  if [[ -n "$REGION" ]]; then
    "$PYTHON" "$SCRIPTS/02_compare_meta_worldpop.py" --region "$REGION"
  else
    "$PYTHON" "$SCRIPTS/02_compare_meta_worldpop.py" -i "$GPKG_01"
  fi

  echo ""
  echo "[4/15] 02 Nature-style plots..."
  Rscript "$SCRIPTS/02_plots.R" -i "$GPKG_02" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[3/15] 02 compare skipped"
  echo "[4/15] 02 plots skipped"
fi

# 04. Person-level allocation impact (counterfactuals; needs GPKG_02)
if _run_step "04"; then
  echo ""
  echo "[5/15] Allocation impact in people (04_impact)..."
  if [[ -n "$REGION" ]]; then
    "$PYTHON" "$SCRIPTS/04_impact.py" --region "$REGION"
  else
    "$PYTHON" "$SCRIPTS/04_impact.py" -i "$GPKG_02" -o "$OUT_ROOT"
  fi
  echo ""
  echo "[5b/15] 04 allocation figures (04_plots.R)..."
  Rscript "$SCRIPTS/04_plots.R" -i "$CSV_04" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[5/15] 04 impact skipped (--start-from $START_FROM)"
fi

# 3a. Regression
if _run_step "03a"; then
  echo ""
  echo "[6/15] Regression (03a)..."
  "$PYTHON" "$SCRIPTS/03a_regression.py" -i "$GPKG_02" --region "$REGION"
  echo ""
  echo "[7/15] 03a plots..."
  Rscript "$SCRIPTS/03a_plots.R" -i "$CSV_03a" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[6/15] 03a regression skipped"
  echo "[7/15] 03a plots skipped"
fi

# 3b. Stratified
if _run_step "03b"; then
  echo ""
  echo "[8/15] Stratified analysis (03b)..."
  "$PYTHON" "$SCRIPTS/03b_stratified.py" -i "$GPKG_02" --region "$REGION"
  echo ""
  echo "[9/15] 03b plots..."
  Rscript "$SCRIPTS/03b_plots.R" -i "$CSV_03b" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[8/15] 03b stratified skipped"
  echo "[9/15] 03b plots skipped"
fi

# 3c. Spatial regression
if _run_step "03c"; then
  echo ""
  echo "[10/15] Spatial regression (03c)..."
  "$PYTHON" "$SCRIPTS/03c_spatial_regression.py" -i "$GPKG_02" --region "$REGION"
  echo ""
  echo "[11/15] 03c plots..."
  Rscript "$SCRIPTS/03c_plots.R" -i "$GEO_03c" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[10/15] 03c spatial skipped"
  echo "[11/15] 03c plots skipped"
fi

# 3d. Bivariate map
if _run_step "03d"; then
  echo ""
  echo "[12/15] Bivariate map (03d)..."
  Rscript "$SCRIPTS/03d_bivariate_map_poverty_residual.R" -i "$GPKG_02" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[12/15] 03d bivariate skipped"
fi

# 3e. Causal
if _run_step "03e"; then
  echo ""
  echo "[13/15] Causal analysis (03e)..."
  "$PYTHON" "$SCRIPTS/03e_causal.py" -i "$GPKG_02" --region "$REGION"
  Rscript "$SCRIPTS/03e_plots.R" -i "$CSV_03e" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[13/15] 03e causal skipped"
fi

# 3f. Robustness
if _run_step "03f"; then
  echo ""
  echo "[14/15] Robustness (03f)..."
  "$PYTHON" "$SCRIPTS/03f_robustness.py" -i "$GPKG_02" --region "$REGION"
  echo ""
  echo "[15/15] 03f plots..."
  Rscript "$SCRIPTS/03f_plots.R" -i "$CSV_03f" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[14/15] 03f robustness skipped"
  echo "[15/15] 03f plots skipped"
fi

echo ""
echo "=========================================="
echo "Pipeline complete."
echo "  CSVs:    $OUT_ROOT/"
echo "  figures: $FIG_ROOT/"
echo "  GPKGs:   $GEO_ROOT/"
echo "=========================================="
