#!/bin/bash
# Run the full analysis pipeline in correct order.
#
# NOTE: If you get "zsh: number expected", run with:  ./run --region KEN_Nairobi
#       or:  bash ./pipeline/run_all.sh --region KEN_Nairobi
#       (Avoid copying the "# Kenya (Nairobi)" comment - parentheses can confuse zsh)
if [ -n "${ZSH_VERSION:-}" ]; then
  exec /bin/bash "$0" "$@"
fi
# Usage: ./pipeline/run_all.sh [--no-basemap] [--ref-hour HOUR] [--region REGION | --all] [--start-from STEP]
#   --no-basemap      Skip basemap tiles (avoids memory limit)
#   --ref-hour HOUR   Reference hour for Meta baseline: 0, 8, or 16 (default: from config). Uses fb_baseline_median_h{HOUR:02d}.gpkg
#   --region REGION   Region code or country prefix from config/regions.json:
#                     PHI = both PHI cities; KEN = both Kenya cities; MEX, PRT = single region
#                     Full codes: PHI_CagayandeOroCity, PHI_DavaoCity, KEN_Nairobi, KEN_Mombasa, MEX, PRT
#   --all             Run pipeline for all regions (mutually exclusive with --region)
#   --start-from STEP Start from this step (skips earlier steps). STEP: 01, 02, 04, 03a, 03b, 03c, 03d, 03e, 03f
#                     Example: --start-from 03b runs 03b, 03b_plots, 03c, ... through 03f_plots

set -e
cd "$(dirname "$0")/.."
PROJECT_ROOT="$(pwd)"
SCRIPTS="$PROJECT_ROOT/pipeline"

# Parse optional args
R_ARGS=()
REGION=""
RUN_ALL=false
START_FROM=""
REF_HOUR=""
PASSTHROUGH=()
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
    --region)
      REGION="$2"
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
      echo "Usage: $0 [--no-basemap] [--ref-hour HOUR] [--region REGION | --all] [--start-from STEP]"
      echo "  HOUR: 0, 8, or 16 (Meta baseline reference hour)"
      echo "  REGION: PHI_CagayandeOroCity, PHI_DavaoCity, KEN_Nairobi, KEN_Mombasa, MEX, PRT — from config/regions.json"
      echo "  STEP: 01, 02, 04, 03a, 03b, 03c, 03d, 03e, 03f"
      exit 1
      ;;
  esac
done

if [[ "$RUN_ALL" == true && -n "$REGION" ]]; then
  echo "Error: Cannot use both --all and --region"
  exit 1
fi

# When --all: run pipeline for each region
if [[ "$RUN_ALL" == true ]]; then
  REGIONS=$(python3 -c "
import json
with open('$PROJECT_ROOT/config/regions.json') as f:
    r = json.load(f)
print(' '.join(k for k in r if k != 'data_root'))
")
  echo "=========================================="
  echo "Running pipeline for all regions"
  echo "=========================================="
  for r in $REGIONS; do
    echo ""
    echo ">>> Region: $r <<<"
    /bin/bash "$0" --region "$r" "${PASSTHROUGH[@]}"
  done
  echo ""
  echo "=========================================="
  echo "Pipeline complete for all regions."
  echo "=========================================="
  exit 0
fi

# When --region: resolve prefix to region list (PHI -> both PHI cities, KEN -> both Kenya cities)
if [[ -n "$REGION" ]]; then
  REGIONS=$(python3 -c "
import json, sys
with open('$PROJECT_ROOT/config/regions.json') as f:
    r = json.load(f)
keys = [k for k in r if k != 'data_root']
region = '$REGION'
if region in keys:
    print(region)
else:
    matches = [k for k in keys if k.startswith(region)]
    if not matches:
        print('', file=sys.stderr)
        sys.exit(1)
    print(' '.join(matches))
")
  if [[ $? -ne 0 || -z "$REGIONS" ]]; then
    echo "Error: No region matches '$REGION'. Use PHI, KEN, MEX, PRT or full codes like PHI_CagayandeOroCity."
    exit 1
  fi
  REGION_COUNT=$(echo "$REGIONS" | wc -w | tr -d ' ')
  if [[ "$REGION_COUNT" -gt 1 ]]; then
    echo "=========================================="
    echo "Running pipeline for $REGION ($REGION_COUNT regions): $REGIONS"
    echo "=========================================="
    for r in $REGIONS; do
      echo ""
      echo ">>> Region: $r <<<"
      /bin/bash "$0" --region "$r" "${PASSTHROUGH[@]}"
    done
    echo ""
    echo "=========================================="
    echo "Pipeline complete for $REGION."
    echo "=========================================="
    exit 0
  else
    REGION="$REGIONS"
  fi
fi

# Output paths: region-specific (outputs/PHI/01, ...) or flat (outputs/01, ...) when no --region
if [[ -n "$REGION" ]]; then
  OUT_01="$PROJECT_ROOT/outputs/$REGION/01"
  OUT_02="$PROJECT_ROOT/outputs/$REGION/02"
  OUT_ROOT="$PROJECT_ROOT/outputs/$REGION"
  GPKG_01="$OUT_01/harmonised_meta_worldpop.gpkg"
  GPKG_02="$OUT_02/harmonised_with_residual.gpkg"
  R_REGION_ARGS=(--region "$REGION")
else
  OUT_01="$PROJECT_ROOT/outputs/01"
  OUT_02="$PROJECT_ROOT/outputs/02"
  OUT_ROOT="$PROJECT_ROOT/outputs"
  GPKG_01="$OUT_01/harmonised_meta_worldpop.gpkg"
  GPKG_02="$OUT_02/harmonised_with_residual.gpkg"
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
[[ -n "$REGION" ]] && echo "Region: $REGION (outputs in $OUT_ROOT/)" && echo ""
[[ -n "$REF_HOUR" ]] && echo "Ref hour: $REF_HOUR (fb_baseline_median_h$(printf '%02d' "$REF_HOUR").gpkg)" && echo ""
[[ -n "$START_FROM" ]] && echo "Starting from step: $START_FROM" && echo ""

# 1. Harmonise
if _run_step "01"; then
  echo ""
  echo "[1/15] Harmonising datasets..."
  if [[ -n "$REGION" ]]; then
    HARMONISE_ARGS=(--region "$REGION")
    [[ -n "$REF_HOUR" ]] && HARMONISE_ARGS+=(--ref-hour "$REF_HOUR")
    python "$SCRIPTS/01_harmonise_datasets.py" "${HARMONISE_ARGS[@]}"
  else
    python "$SCRIPTS/01_harmonise_datasets.py"
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
    python "$SCRIPTS/02_compare_meta_worldpop.py" --region "$REGION"
  else
    python "$SCRIPTS/02_compare_meta_worldpop.py" -i "$GPKG_01"
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
    python "$SCRIPTS/04_impact.py" --region "$REGION"
  else
    python "$SCRIPTS/04_impact.py" -i "$GPKG_02" -o "$OUT_ROOT"
  fi
else
  echo ""
  echo "[5/15] 04 impact skipped (--start-from $START_FROM)"
fi

# 3a. Regression
if _run_step "03a"; then
  echo ""
  echo "[6/15] Regression (03a)..."
  python "$SCRIPTS/03a_regression.py" -i "$GPKG_02" -o "$OUT_ROOT"

  echo ""
  echo "[7/15] 03a plots..."
  Rscript "$SCRIPTS/03a_plots.R" -i "$OUT_ROOT/03a_regression" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[6/15] 03a regression skipped"
  echo "[7/15] 03a plots skipped"
fi

# 3b. Stratified
if _run_step "03b"; then
  echo ""
  echo "[8/15] Stratified analysis (03b)..."
  python "$SCRIPTS/03b_stratified.py" -i "$GPKG_02" -o "$OUT_ROOT"

  echo ""
  echo "[9/15] 03b plots..."
  Rscript "$SCRIPTS/03b_plots.R" -i "$OUT_ROOT/03b_stratified" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[8/15] 03b stratified skipped"
  echo "[9/15] 03b plots skipped"
fi

# 3c. Spatial regression
if _run_step "03c"; then
  echo ""
  echo "[10/15] Spatial regression (03c)..."
  python "$SCRIPTS/03c_spatial_regression.py" -i "$GPKG_02" -o "$OUT_ROOT"

  echo ""
  echo "[11/15] 03c plots..."
  Rscript "$SCRIPTS/03c_plots.R" -i "$OUT_ROOT/03c_spatial_regression" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[10/15] 03c spatial skipped"
  echo "[11/15] 03c plots skipped"
fi

# 3d. Bivariate map
if _run_step "03d"; then
  echo ""
  echo "[12/15] Bivariate map (03d)..."
  Rscript "$SCRIPTS/03d_bivariate_map_poverty_residual.R" -i "$GPKG_02" -o "$OUT_ROOT/03d_bivariate" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[12/15] 03d bivariate skipped"
fi

# 3e. Causal
if _run_step "03e"; then
  echo ""
  echo "[13/15] Causal analysis (03e)..."
  python "$SCRIPTS/03e_causal.py" -i "$GPKG_02" -o "$OUT_ROOT"
  Rscript "$SCRIPTS/03e_plots.R" -i "$OUT_ROOT/03e_causal" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[13/15] 03e causal skipped"
fi

# 3f. Robustness
if _run_step "03f"; then
  echo ""
  echo "[14/15] Robustness (03f)..."
  python "$SCRIPTS/03f_robustness.py" -i "$GPKG_02" -o "$OUT_ROOT"

  echo ""
  echo "[15/15] 03f plots..."
  Rscript "$SCRIPTS/03f_plots.R" -i "$OUT_ROOT/03f_robustness" "${R_REGION_ARGS[@]}"
else
  echo ""
  echo "[14/15] 03f robustness skipped"
  echo "[15/15] 03f plots skipped"
fi

echo ""
echo "=========================================="
echo "Pipeline complete. Outputs in $OUT_ROOT/"
echo "=========================================="
