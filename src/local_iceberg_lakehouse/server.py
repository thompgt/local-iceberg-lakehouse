import logging
import os
import json
import pyarrow as pa
from typing import List, Optional, Dict, Any
from mcp.server.fastmcp import FastMCP
from .catalog import CatalogManager
from .query import QueryEngine

logger = logging.getLogger(__name__)

# Initialize MCP server
mcp = FastMCP("Local Iceberg Lakehouse")

# Initialize Catalog and Query Engine
# Default to ~/.lakehouse/warehouse
catalog_manager = CatalogManager()
query_engine = QueryEngine(catalog_manager)

@mcp.tool()
def list_tables() -> str:
    """List all tables in the lakehouse."""
    tables = catalog_manager.list_tables()
    return json.dumps(tables, indent=2)

@mcp.tool()
def get_table_schema(table_name: str) -> str:
    """Get the schema of a specific table."""
    try:
        table = catalog_manager.load_table(table_name)
        schema_dict = {field.name: str(field.field_type) for field in table.schema().fields}
        return json.dumps(schema_dict, indent=2)
    except Exception as e:
        logger.exception("get_table_schema failed for table '%s'.", table_name)
        return f"Error: {str(e)}"

@mcp.tool()
def query(sql: str, table_mapping: Optional[Dict[str, str]] = None) -> str:
    """
    Execute a read-only SQL query against the lakehouse.
    Example: query("SELECT * FROM my_table", {"my_table": "default.my_iceberg_table"})
    """
    try:
        result_table = query_engine.query(sql, table_mapping)
        # Convert to list of dicts for LLM readability (up to a limit)
        data = result_table.to_pylist()
        if len(data) > 100:
            return json.dumps(data[:100], indent=2) + "\n... (truncated)"
        return json.dumps(data, indent=2)
    except Exception as e:
        logger.exception("query failed for sql=%r table_mapping=%r.", sql, table_mapping)
        return f"Error: {str(e)}"

@mcp.tool()
def upsert(table_name: str, records: List[Dict[str, Any]], join_cols: List[str]) -> str:
    """
    Insert or update records in a table.
    'records' is a list of dictionaries.
    'join_cols' are the columns to use for matching existing records.
    """
    try:
        data = pa.Table.from_pylist(records)
        query_engine.upsert_data(table_name, data, join_cols)
        return f"Successfully upserted {len(records)} records into {table_name}."
    except Exception as e:
        logger.exception("upsert failed for table '%s'.", table_name)
        return f"Error: {str(e)}"

@mcp.tool()
def rollback(table_name: str, snapshot_id: int) -> str:
    """Rollback a table to a specific snapshot ID."""
    try:
        table = catalog_manager.load_table(table_name)
        table.rollback_to_snapshot(snapshot_id)
        return f"Successfully rolled back {table_name} to snapshot {snapshot_id}."
    except Exception as e:
        logger.exception("rollback failed for table '%s' to snapshot %s.", table_name, snapshot_id)
        return f"Error: {str(e)}"

@mcp.tool()
def get_history(table_name: str) -> str:
    """Get the history of snapshots for a table."""
    try:
        table = catalog_manager.load_table(table_name)
        history = []
        for snapshot in table.snapshots():
            history.append({
                "snapshot_id": snapshot.snapshot_id,
                "timestamp_ms": snapshot.timestamp_ms,
                "summary": snapshot.summary
            })
        return json.dumps(history, indent=2)
    except Exception as e:
        logger.exception("get_history failed for table '%s'.", table_name)
        return f"Error: {str(e)}"

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    mcp.run()
