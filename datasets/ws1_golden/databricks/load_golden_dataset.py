# Databricks notebook source
# MAGIC %md
# MAGIC # Load the WS-1 Golden Dataset into Unity Catalog
# MAGIC Registers the source + truth tables from the uploaded golden dataset and leaves the
# MAGIC documents in a Volume. Run AFTER uploading the files (see `upload.sh` / README).
# MAGIC Produces:
# MAGIC - `<catalog>.<schema>.ws1_golden_documents` — one row per document (source table)
# MAGIC - `<catalog>.<schema>.ws1_golden_labels` — one row per ground-truth entity (truth table)
# MAGIC - documents remain at `/Volumes/<catalog>/<schema>/<volume>/documents/`

# COMMAND ----------

dbutils.widgets.text("catalog", "main")
dbutils.widgets.text("schema", "prince_houston")
dbutils.widgets.text("volume", "ws1_golden")

catalog = dbutils.widgets.get("catalog")
schema = dbutils.widgets.get("schema")
volume = dbutils.widgets.get("volume")
base = f"/Volumes/{catalog}/{schema}/{volume}"

# COMMAND ----------

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {catalog}.{schema}")
spark.sql(f"CREATE VOLUME IF NOT EXISTS {catalog}.{schema}.{volume}")

# COMMAND ----------

# JSONL → Delta. spark.read.json reads newline-delimited JSON directly.
docs = spark.read.json(f"{base}/manifest.jsonl")
(
    docs.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{catalog}.{schema}.ws1_golden_documents")
)

labels = spark.read.json(f"{base}/labels.jsonl")
(
    labels.write.mode("overwrite")
    .option("overwriteSchema", "true")
    .saveAsTable(f"{catalog}.{schema}.ws1_golden_labels")
)

# COMMAND ----------

# MAGIC %md ## Verify
print("documents:", spark.table(f"{catalog}.{schema}.ws1_golden_documents").count())
print("labels:", spark.table(f"{catalog}.{schema}.ws1_golden_labels").count())
display(spark.table(f"{catalog}.{schema}.ws1_golden_documents").limit(10))
