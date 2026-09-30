-- Load the WS-1 golden dataset tables from the uploaded Volume files.
-- Run in the Databricks SQL Editor (attach a SQL warehouse). Adjust the catalog/schema/
-- volume in the paths + names if you uploaded elsewhere.

CREATE SCHEMA IF NOT EXISTS workspace.prince_houston;

-- Source table: one row per document.
CREATE OR REPLACE TABLE workspace.prince_houston.ws1_golden_documents AS
SELECT *
FROM read_files(
  '/Volumes/workspace/prince_houston/ws1_golden/manifest.jsonl',
  format => 'json'
);

-- Truth table: one row per ground-truth entity.
CREATE OR REPLACE TABLE workspace.prince_houston.ws1_golden_labels AS
SELECT *
FROM read_files(
  '/Volumes/workspace/prince_houston/ws1_golden/labels.jsonl',
  format => 'json'
);

-- Verify (expect 48 documents, 332 labels).
SELECT 'documents' AS tbl, count(*) AS rows FROM workspace.prince_houston.ws1_golden_documents
UNION ALL
SELECT 'labels', count(*) FROM workspace.prince_houston.ws1_golden_labels;
