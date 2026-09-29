# Load the WS-1 Golden Dataset into Databricks

Target workspace id: **7474656897795818** (use its host URL, e.g.
`https://<your-workspace>.cloud.databricks.com`).

This puts the golden dataset into Unity Catalog as:
- `<catalog>.<schema>.ws1_golden_documents` — source table (one row per document)
- `<catalog>.<schema>.ws1_golden_labels` — truth table (one row per ground-truth entity)
- documents in a Volume: `/Volumes/<catalog>/<schema>/<volume>/documents/`

## Steps (you run these — your credentials stay yours)

1. **Install + authenticate the CLI** (once):
   ```bash
   pip install databricks-cli
   databricks configure        # host = your workspace URL; token = a PAT you create
   ```
2. **Upload the files** to a Volume:
   ```bash
   CATALOG=main SCHEMA=prince_houston VOLUME=ws1_golden \
     bash datasets/ws1_golden/databricks/upload.sh
   ```
3. **Create the tables** — import `load_golden_dataset.py` as a notebook in the workspace
   (or use the Databricks VS Code / CLI bundle) and run it with widgets
   `catalog / schema / volume` matching step 2. It reads the uploaded `*.jsonl` and writes
   the two Delta tables; the binary documents stay in the Volume, referenced by
   `documents.path`.

## Notes
- The JSONL files load directly with `spark.read.json` (newline-delimited).
- Later, the WS-1 pipeline's source reader can point at
  `<catalog>.<schema>.ws1_golden_documents` + the Volume to run over this as the source
  (that source-connector work is separate and tracked elsewhere).
- Everything here is synthetic (see ../NOTICE.md) — safe to upload.
