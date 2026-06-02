import duckdb
import pyarrow as pa
from typing import Optional, Union, Dict, Any
from pyiceberg.table import Table
from .catalog import CatalogManager

class QueryEngine:
    def __init__(self, catalog_manager: CatalogManager):
        self.catalog_manager = catalog_manager
        self.con = duckdb.connect(database=":memory:")
        # Install and load iceberg extension if needed, 
        # but for now we'll use Arrow integration
        # self.con.execute("INSTALL iceberg; LOAD iceberg;")

    def query(self, sql: str, table_mapping: Optional[Dict[str, str]] = None) -> pa.Table:
        """
        Execute a SQL query. If table_mapping is provided, it maps 
        logical table names in SQL to Iceberg table names.
        """
        if table_mapping:
            for logical_name, iceberg_name in table_mapping.items():
                table = self.catalog_manager.load_table(iceberg_name)
                # Scan table as Arrow and register as view in DuckDB
                arrow_table = table.scan().to_arrow()
                self.con.register(logical_name, arrow_table)
        
        return self.con.execute(sql).fetch_arrow_table()

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
        
        self.con.register("existing_data", existing_data)
        self.con.register("new_data", data)
        
        # SQL to perform upsert (merge)
        # For simplicity, we'll do: (existing EXCEPT matching_new) UNION new
        join_condition = " AND ".join([f"existing_data.{col} = new_data.{col}" for col in join_cols])
        
        upsert_sql = f"""
        SELECT * FROM new_data
        UNION ALL
        SELECT * FROM existing_data
        WHERE NOT EXISTS (
            SELECT 1 FROM new_data 
            WHERE {join_condition}
        )
        """
        
        merged_data = self.con.execute(upsert_sql).fetch_arrow_table()
        table.overwrite(merged_data)
