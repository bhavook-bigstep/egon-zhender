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

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # datasets/ws1_golden
VOL="/Volumes/${CATALOG}/${SCHEMA}/${VOLUME}"

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
