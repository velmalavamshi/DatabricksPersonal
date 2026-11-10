"""Sample Lakeflow / DLT bronze pipeline (metadata loop).

Attach the ``utilities/Declarative Pipelines`` folder (or both Python files
in this folder) as the pipeline source. Databricks builds the graph when
this module is imported, so ``generate_bronze_table`` is called at **top
level**, not inside a ``@dlt.table`` function.

Defaults (override per config): ``mde_dev.bec_raw`` → ``mde_dev.bronze``.

Published tables expose ``dl_iscurrent``, ``dl_isdeleted``,
``dl_starttimeutc``, ``dl_endtimeutc``. Native ``__START_AT`` / ``__END_AT``
stay on the internal ``{table}__cdc`` landing table.

No ``bec_raw`` table names were found in this repo; ``bec_item`` (SCD1) and
``bec_customer`` (SCD2) are placeholders — replace with real Unity Catalog
tables before running.
"""

from __future__ import annotations

try:
    from pyspark import pipelines as dlt  # Lakeflow Declarative Pipelines
except ImportError:  # pragma: no cover - older DLT runtimes
    import dlt  # type: ignore  # noqa: F401

from bronze_dlt_factory import BronzeTableConfig, generate_bronze_table


# Graph construction must run at import time.
SAMPLE_TABLES: list[BronzeTableConfig] = [
    {
        "table_name": "olist_customers_dataset",
        "primary_keys": ["customer_id"],
        "sequence_column": "last_update_utc",
        "operation_column": "operation",
        "scd_type": 1,
        "comment": (
            "BEC item master (SCD Type 1). Latest state only; deletes remove "
            "the current row via apply_as_deletes."
        ),
        "cluster_by": ["item_id"],
    },
    {
        "table_name": "bec_customer",
        "primary_keys": ["customer_id"],
        "sequence_column": "last_update_utc",
        "operation_column": "operation",
        "scd_type": 2,
        "comment": (
            "BEC customer (SCD Type 2). Full change history; current rows "
            "have dl_endtimeutc IS NULL / dl_iscurrent = true."
        ),
        "cluster_by": ["customer_id"],
    },
]


for _table_config in SAMPLE_TABLES:
    generate_bronze_table(_table_config)
