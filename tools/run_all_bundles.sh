#!/usr/bin/env bash
set -u -o pipefail
CONDA_ENV="${CONDA_ENV:-gestion-stock-py310}"
# Mode tests sans Redis ni services réseau
DJANGO_SETTINGS_MODULE="${DJANGO_SETTINGS_MODULE:-alfenna.settings.test_cli}"
export DJANGO_SETTINGS_MODULE
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_ROOT" || { echo "no project root" >&2; exit 1; }
timestamp="$(date +"%Y-%m-%d_%H-%M-%S")"
REPORT_DIR="reports"
LOG_DIR="$REPORT_DIR/bundles_logs_${timestamp}"
REPORT_FILE="$REPORT_DIR/bundles_report_${timestamp}.md"
mkdir -p "$REPORT_DIR" "$LOG_DIR"
echo "# Bundles run_all — ${timestamp}" > "$REPORT_FILE"
{
  echo
  echo "- Conda env: \`$CONDA_ENV\`"
  echo "- DJANGO_SETTINGS_MODULE: \`$DJANGO_SETTINGS_MODULE\`"
  echo
  echo "| Bundle | Status | Duration (s) | Log |"
  echo "|---|---|---:|---|"
} >> "$REPORT_FILE"

# Trouver un interpréteur Python exécutable (priorité: conda env ciblé)
PY_CANDIDATES=(
  "$HOME/miniforge3_x86_64/envs/$CONDA_ENV/bin/python"
  "$HOME/miniforge3/envs/$CONDA_ENV/bin/python"
  "$HOME/mambaforge/envs/$CONDA_ENV/bin/python"
  "$HOME/anaconda3/envs/$CONDA_ENV/bin/python"
  "$HOME/miniconda3/envs/$CONDA_ENV/bin/python"
  "$(command -v python3 || true)"
  "$(command -v python || true)"
)
PY_BIN=""
for c in "${PY_CANDIDATES[@]}"; do
  if [ -n "${c}" ] && [ -x "${c}" ]; then PY_BIN="${c}"; break; fi
done
if [ -z "${PY_BIN}" ]; then
  echo "No usable python found for env '$CONDA_ENV'." >&2
  exit 1
fi
targets=(
  "apps.atelier.scripts.components.run_all"
  "apps.atelier.scripts.formfront.run_all"
  "apps.atelier.scripts.images.run_all"
  "apps.atelier.scripts.phase3.run_all"
  "apps.atelier.scripts.phase6.run_all"
  "apps.atelier.scripts.phase7.run_all"
  "apps.atelier.scripts.phase8.run_all"
  "apps.atelier.scripts.suite.run_all"
  "apps.flowforms.scripts.run_flowforms_all"
  "apps.accounts.scripts.suite.run_all"
  "apps.billing.scripts.suite.run_all"
  "apps.catalog.scripts.suite.run_all"
  "apps.content.scripts.gating.run_all"
  "apps.leads.scripts.suite.run_all"
  "apps.learning.scripts.suite.run_all"
  "apps.marketing.scripts.suite.run_all"
)
for dotted in "${targets[@]}"; do
  log_file="$LOG_DIR/${dotted//./_}.log"
  start=$(date +%s)
  env DJANGO_SETTINGS_MODULE="$DJANGO_SETTINGS_MODULE" \
       "$PY_BIN" manage.py runscript "$dotted" > "$log_file" 2>&1
  cmd_status=$?
  end=$(date +%s); dur=$((end-start))
  status="PASS"
  if grep -q "ECHEC" "$log_file"; then status="FAIL"; fi
  if [ $cmd_status -ne 0 ] && [ "$status" = "PASS" ]; then status="FAIL"; fi
  echo "| \`$dotted\` | $status | $dur | [log]($log_file) |" >> "$REPORT_FILE"
done
echo "Report written to: $REPORT_FILE"
