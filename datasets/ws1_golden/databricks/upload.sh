#!/usr/bin/env bash
# Upload the WS-1 golden dataset to a Unity Catalog Volume, then you run the load notebook.
#
# Prereqs (you do this — the token is yours, never shared):
#   pip install databricks-cli            # or: brew install databricks/tap/databricks
#   databricks configure                  # enter your workspace host + a PAT/OAuth
#     host e.g. https://<your-workspace>.cloud.databricks.com   (workspace id 7474656897795818)
#
# Then set the target and run this script from the repo root:
#   CATALOG=main SCHEMA=prince_houston VOLUME=ws1_golden bash datasets/ws1_golden/databricks/upload.sh
set -euo pipefail

: "${CATALOG:?set CATALOG (e.g. main)}"
: "${SCHEMA:?set SCHEMA (e.g. prince_houston)}"
VOLUME="${VOLUME:-ws1_golden}"

# Optional named auth profile (from `databricks auth login [--profile NAME]`). If you
# authenticated to a profile named after your email, run with PROFILE=that-name.
if [[ -n "${PROFILE:-}" ]]; then export DATABRICKS_CONFIG_PROFILE="${PROFILE}"; fi

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # datasets/ws1_golden
VOL="/Volumes/${CATALOG}/${SCHEMA}/${VOLUME}"

# Preflight: fail fast with a clear message instead of a cryptic basic-auth error.
if ! databricks current-user me >/dev/null 2>&1; then
  echo "ERROR: Databricks auth not working (token/OAuth required — basic auth is disabled)." >&2
  echo "Fix: databricks auth login --host <workspace-url> --profile DEFAULT" >&2
  echo "  or authenticate a named profile and re-run with PROFILE=<name>." >&2
  exit 1
fi
echo "Authenticated as: $(databricks current-user me | sed -n 's/.*\"userName\": *\"\([^\"]*\)\".*/\1/p' | head -1)"

echo "Ensuring schema + volume exist..."
databricks schemas create "${SCHEMA}" "${CATALOG}" 2>/dev/null || true
databricks volumes create "${CATALOG}" "${SCHEMA}" "${VOLUME}" MANAGED 2>/dev/null || true

echo "Uploading golden dataset -> ${VOL}"
databricks fs cp --overwrite --recursive "${HERE}/documents" "dbfs:${VOL}/documents"
databricks fs cp --overwrite "${HERE}/manifest.jsonl" "dbfs:${VOL}/manifest.jsonl"
databricks fs cp --overwrite "${HERE}/labels.jsonl"   "dbfs:${VOL}/labels.jsonl"
databricks fs cp --overwrite "${HERE}/NOTICE.md"      "dbfs:${VOL}/NOTICE.md"

echo "Done. Now run the notebook datasets/ws1_golden/databricks/load_golden_dataset.py"
echo "with widgets catalog=${CATALOG} schema=${SCHEMA} volume=${VOLUME} to create the tables."
