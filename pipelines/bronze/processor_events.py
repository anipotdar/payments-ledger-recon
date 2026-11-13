# Databricks notebook source
# MAGIC %md
# MAGIC # Bronze: processor events
# MAGIC
# MAGIC Raw webhook lines into a Delta table, exactly as delivered. No dedup, no
# MAGIC parsing beyond what Auto Loader needs. Cleaning happens in silver.
# MAGIC
# MAGIC Decide and write down before coding:
# MAGIC 1. Keep `data` as a string or let Auto Loader infer a struct? What happens to
# MAGIC    the `payment_method` field that appears mid-period (SCHEMA_CHANGE)?
# MAGIC 2. Which lineage columns go on every row? At minimum: source file path and
# MAGIC    ingest timestamp (`_metadata.file_path`, `_metadata.file_modification_time`).
# MAGIC 3. `trigger(availableNow=True)` or continuous? Why, given files land in batches?
# MAGIC 4. What proves a replay of the same file changes nothing?

# COMMAND ----------

CATALOG = "workspace"
SCHEMA = "ledger_recon"
SOURCE = f"/Volumes/{CATALOG}/{SCHEMA}/landing/processor_events/"
CHECKPOINT = f"/Volumes/{CATALOG}/{SCHEMA}/checkpoints/bronze_processor_events"
TARGET = f"{CATALOG}.{SCHEMA}.bronze_processor_events"

# COMMAND ----------

# TODO(weekend 1): Auto Loader stream from SOURCE into TARGET.
# Shape to aim for:
#   spark.readStream.format("cloudFiles")
#       .option("cloudFiles.format", "json")
#       .option("cloudFiles.schemaLocation", CHECKPOINT + "/_schema")
#       ...
#   .writeStream ... .trigger(availableNow=True) ... .toTable(TARGET)
raise NotImplementedError("weekend 1")
