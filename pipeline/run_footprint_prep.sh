#!/bin/bash
# Event-footprint run for ONE country (same idea as ./run --region COUNTRY).
# Prep (01 + GHSL labels) then the same 02–03f analysis as the city pipeline.
# Writes outputs/figure/footprints/{CODE}/ so it does not overwrite city folders.
#
# Usage (from repo root):
#   bash pipeline/run_footprint_prep.sh KEN
#   bash pipeline/run_footprint_prep.sh PHL
#   WORKERS=4 bash pipeline/run_footprint_prep.sh KEN
#   bash pipeline/run_footprint_prep.sh KEN --download-smod
#   bash pipeline/run_footprint_prep.sh KEN --baseline-method shift
#   bash pipeline/run_footprint_prep.sh KEN --prep-only
if [ -n "${ZSH_VERSION:-}" ]; then
  exec /bin/bash "$0" "$@"
fi

set -e
cd "$(dirname "$0")/.."
if [ -z "${1:-}" ] || [[ "${1}" == -* ]]; then
  echo "Usage: bash pipeline/run_footprint_prep.sh COUNTRY [--download-smod] [--prep-only] [--no-basemap]"
  echo "  COUNTRY is any city-pipeline country (PHL, KEN, MEX, IDN, LKA, COL, ECU, ZAF)."
  echo "  Default: prep + 02–03f figures/CSVs (no satellite basemap). --prep-only stops after labels."
  exit 1
fi
FOOTPRINT="$1"
shift
WORKERS="${WORKERS:-4}"
PYTHON="${PYTHON:-python}"
SCRIPTS="$(pwd)/pipeline"
BASELINE_METHOD="n_baseline"
PREP_ONLY=false
SKIP_BASEMAP=true
GEO_ARGS=()
while [[ $# -gt 0 ]]; do
  case $1 in
    --baseline-method)
      BASELINE_METHOD="$2"
      shift 2
      ;;
    --prep-only)
      PREP_ONLY=true
      shift
      ;;
    --no-basemap)
      SKIP_BASEMAP=true
      shift
      ;;
    --basemap)
      SKIP_BASEMAP=false
      shift
      ;;
    *)
      GEO_ARGS+=("$1")
      shift
      ;;
  esac
done

R_ARGS=()
if [[ "$SKIP_BASEMAP" == true ]]; then
  R_ARGS+=(--no-basemap)
fi
R_FP=(--footprint "$FOOTPRINT")

echo "=========================================="
echo "Footprint: $FOOTPRINT  (workers=$WORKERS)"
echo "=========================================="

ALIGNED="data/processed/footprints/${FOOTPRINT}_aligned.parquet"
ALIGNED_LEGACY="data/processed/${FOOTPRINT}_aligned.parquet"
if [[ -f "$ALIGNED" || -f "$ALIGNED_LEGACY" ]]; then
  echo ""
  echo "[1/2] Aligned parquet already present — skip 01."
else
  echo ""
  echo "[1/2] Harmonise Meta + WorldPop + GRDI (no city clip) ..."
  "$PYTHON" pipeline/01_harmonise_datasets.py --footprint "$FOOTPRINT" --workers "$WORKERS" --worldpop-method centre --baseline-method "$BASELINE_METHOD"
fi

echo ""
echo "[2/2] Add GHSL / admin / city geography labels ..."
"$PYTHON" pipeline/02_add_geographies.py --footprint "$FOOTPRINT" --workers "$WORKERS" --save-gpkg "${GEO_ARGS[@]}"

GPKG_GEO="outputs/footprints/${FOOTPRINT}/geographies/aligned_with_geographies.gpkg"
GPKG_01="outputs/footprints/${FOOTPRINT}/01/harmonised_meta_worldpop.gpkg"
if [[ -f "$GPKG_GEO" ]]; then
  GPKG_01_IN="$GPKG_GEO"
elif [[ -f "$GPKG_01" ]]; then
  GPKG_01_IN="$GPKG_01"
else
  GPKG_01_IN="$ALIGNED"
fi
GPKG_02="data/processed/footprints/${FOOTPRINT}/02/harmonised_with_residual.gpkg"
CSV_03a="outputs/footprints/${FOOTPRINT}/03a_regression"
CSV_03b="outputs/footprints/${FOOTPRINT}/03b_stratified"
GEO_03c="data/processed/footprints/${FOOTPRINT}/03c_spatial_regression"
CSV_03e="outputs/footprints/${FOOTPRINT}/03e_causal"
CSV_03f="outputs/footprints/${FOOTPRINT}/03f_robustness"
CSV_04="outputs/footprints/${FOOTPRINT}/04_impact"
CSV_04b="outputs/footprints/${FOOTPRINT}/04b_crisis_inference"

if [[ "$PREP_ONLY" == true ]]; then
  echo ""
  echo "Prep only. Skip 02–03f. QA: $PYTHON pipeline/qa_footprints.py --footprint $FOOTPRINT"
  exit 0
fi

echo ""
echo "[3] Descriptive plots (01_plot_descriptive.R)..."
Rscript "$SCRIPTS/01_plot_descriptive.R" -i "$GPKG_01_IN" "${R_FP[@]}" "${R_ARGS[@]}"

echo ""
echo "[4] Compare Meta vs WorldPop (02)..."
COMPARE_ARGS=(--footprint "$FOOTPRINT" -i "$GPKG_01_IN")
[[ "$SKIP_BASEMAP" == true ]] && COMPARE_ARGS+=(--no-basemap)
"$PYTHON" "$SCRIPTS/02_compare_meta_worldpop.py" "${COMPARE_ARGS[@]}"

echo ""
echo "[5] 02 plots..."
Rscript "$SCRIPTS/02_plots.R" -i "$GPKG_02" "${R_FP[@]}"

echo ""
echo "[6] 04a baseline allocation impact..."
"$PYTHON" "$SCRIPTS/04_impact.py" --footprint "$FOOTPRINT"
Rscript "$SCRIPTS/04_plots.R" -i "$CSV_04" "${R_FP[@]}"

echo ""
echo "[6b] 04b crisis inference sensitivity..."
"$PYTHON" "$SCRIPTS/04b_crisis_inference.py" --footprint "$FOOTPRINT"
Rscript "$SCRIPTS/04b_plots.R" -i "$CSV_04b" "${R_FP[@]}"

echo ""
echo "[7] 03a regression..."
"$PYTHON" "$SCRIPTS/03a_regression.py" -i "$GPKG_02" --footprint "$FOOTPRINT"
Rscript "$SCRIPTS/03a_plots.R" -i "$CSV_03a" "${R_FP[@]}"

echo ""
echo "[8] 03b stratified..."
"$PYTHON" "$SCRIPTS/03b_stratified.py" -i "$GPKG_02" --footprint "$FOOTPRINT"
Rscript "$SCRIPTS/03b_plots.R" -i "$CSV_03b" "${R_FP[@]}"

echo ""
echo "[9] 03c spatial regression (SLM/SEM; slow on large footprints)..."
"$PYTHON" "$SCRIPTS/03c_spatial_regression.py" -i "$GPKG_02" --footprint "$FOOTPRINT"
Rscript "$SCRIPTS/03c_plots.R" -i "$GEO_03c" "${R_FP[@]}"

echo ""
echo "[10] 03d bivariate map..."
Rscript "$SCRIPTS/03d_bivariate_map_poverty_residual.R" -i "$GPKG_02" "${R_FP[@]}" "${R_ARGS[@]}"

echo ""
echo "[11] 03e causal..."
"$PYTHON" "$SCRIPTS/03e_causal.py" -i "$GPKG_02" --footprint "$FOOTPRINT"
Rscript "$SCRIPTS/03e_plots.R" -i "$CSV_03e" "${R_FP[@]}"

echo ""
echo "[12] 03f robustness..."
"$PYTHON" "$SCRIPTS/03f_robustness.py" -i "$GPKG_02" --footprint "$FOOTPRINT"
Rscript "$SCRIPTS/03f_plots.R" -i "$CSV_03f" "${R_FP[@]}"

echo ""
echo "[13] Footprint QA tables + GHSL map..."
"$PYTHON" pipeline/qa_footprints.py --footprint "$FOOTPRINT"

echo ""
echo "Done."
echo "  data/processed/footprints/${FOOTPRINT}_aligned.parquet"
echo "  data/processed/footprints/${FOOTPRINT}/"
echo "  outputs/footprints/${FOOTPRINT}/"
echo "  figure/footprints/${FOOTPRINT}/"
echo "  QA: outputs/footprints/qa/  figure/footprints/qa/"
