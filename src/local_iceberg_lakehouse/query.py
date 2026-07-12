import re

import duckdb
import pyarrow as pa

from .catalog import CatalogManager

# Only allow a single read-only SELECT/WITH statement through query().
# This is a deliberately conservative allow-list (not a full SQL parser):
# it blocks statements that mutate data/catalog state or touch the local
# filesystem/extensions (COPY, ATTACH, INSTALL, PRAGMA, etc.).
_READ_ONLY_PREFIX_RE = re.compile(r"^\s*(with|select)\b", re.IGNORECASE)
_BLOCKED_KEYWORDS = (
    "attach", "detach", "copy", "install", "load", "pragma", "export", "import",
    "create", "insert", "update", "delete", "drop", "alter", "call", "set",
    "execute", "vacuum", "checkpoint",
)


def _validate_read_only_sql(sql: str) -> None:
    statements = [s.strip() for s in sql.split(";") if s.strip()]
    if len(statements) != 1:
        raise ValueError("Only a single SQL statement is allowed.")
    statement = statements[0]
    if not _READ_ONLY_PREFIX_RE.match(statement):
        raise ValueError("Only read-only SELECT/WITH statements are allowed.")
    lowered = statement.lower()
    for keyword in _BLOCKED_KEYWORDS:
        if re.search(rf"\b{keyword}\b", lowered):
            raise ValueError(f"Statement contains disallowed keyword: '{keyword}'.")


class QueryEngine:
    def __init__(self, catalog_manager: CatalogManager):
        self.catalog_manager = catalog_manager
        self.con = duckdb.connect(database=":memory:")

    def query(self, sql: str, table_mapping: dict[str, str] | None = None) -> pa.Table:
        """
        Execute a read-only SQL query. If table_mapping is provided, it maps
        logical table names in SQL to Iceberg table names.
        """
        _validate_read_only_sql(sql)

        if table_mapping:
            for logical_name, iceberg_name in table_mapping.items():
                table = self.catalog_manager.load_table(iceberg_name)
                # Scan table as Arrow and register as view in DuckDB
                arrow_table = table.scan().to_arrow()
                self.con.register(logical_name, arrow_table)
        
        return self.con.execute(sql).to_arrow_table()

    def append_data(self, table_name: str, data: pa.Table):
        table = self.catalog_manager.load_table(table_name)
        table.append(data)

    def overwrite_data(self, table_name: str, data: pa.Table):
        table = self.catalog_manager.load_table(table_name)
        table.overwrite(data)

    def upsert_data(self, table_name: str, data: pa.Table, join_cols: list):
        """
        A simple upsert implementation for local use.
        1. Load existing data.
        2. Merge with new data in DuckDB.
        3. Overwrite the Iceberg table.
        """
        table = self.catalog_manager.load_table(table_name)
        existing_data = table.scan().to_arrow()

        valid_columns = set(table.schema().column_names)
        invalid_cols = [col for col in join_cols if col not in valid_columns]
        if invalid_cols:
            raise ValueError(
                f"join_cols contains columns not present in table '{table_name}': {invalid_cols}"
            )

        self.con.register("existing_data", existing_data)

        # Dedup new_data on join_cols first (last row wins) so that a
        # batch containing multiple updates to the same key doesn't end
        # up with duplicate rows for that key after the merge below.
        ordinal = pa.array(range(data.num_rows), type=pa.int64())
        self.con.register("new_data_raw", data.append_column("_upsert_row_ordinal", ordinal))
        quoted_join_cols = ", ".join(f'"{col}"' for col in join_cols)
        data_columns = ", ".join(f'"{col}"' for col in data.column_names)
        dedup_sql = f"""
        SELECT {data_columns} FROM (
            SELECT *, ROW_NUMBER() OVER (
                PARTITION BY {quoted_join_cols}
                ORDER BY _upsert_row_ordinal DESC
            ) AS _upsert_rn
            FROM new_data_raw
        )
        WHERE _upsert_rn = 1
        """
        deduped_new_data = self.con.execute(dedup_sql).to_arrow_table()
        self.con.register("new_data", deduped_new_data)

        # SQL to perform upsert (merge)
        # For simplicity, we'll do: (existing EXCEPT matching_new) UNION new
        join_condition = " AND ".join(
            [f'existing_data."{col}" = new_data."{col}"' for col in join_cols]
        )
        
        upsert_sql = f"""
        SELECT * FROM new_data
        UNION ALL
        SELECT * FROM existing_data
        WHERE NOT EXISTS (
            SELECT 1 FROM new_data 
            WHERE {join_condition}
        )
        """
        
        merged_data = self.con.execute(upsert_sql).to_arrow_table()
        table.overwrite(merged_data)
