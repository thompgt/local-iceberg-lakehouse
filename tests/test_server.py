import json

import pytest
from pyiceberg.schema import Schema
from pyiceberg.types import LongType, NestedField, StringType

from local_iceberg_lakehouse.server import (
    catalog_manager,
    get_history,
    get_table_schema,
    list_tables,
    query,
    query_engine,
    rollback,
    upsert,
)


@pytest.fixture(autouse=True)
def setup_catalog(tmp_path):
    # Override catalog_manager and query_engine with temp ones for testing
    warehouse_path = tmp_path / "warehouse"
    catalog_manager.__init__(warehouse_path=str(warehouse_path))
    query_engine.__init__(catalog_manager)

def test_list_tables_tool():
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
    )
    catalog_manager.create_table("default.test_server", schema)
    
    res = list_tables()
    tables = json.loads(res)
    assert "default.test_server" in tables

def test_upsert_and_query_tools():
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
        NestedField(field_id=2, name="val", field_type=StringType(), required=False),
    )
    table_name = "default.data"
    catalog_manager.create_table(table_name, schema)
    
    upsert(table_name, [{"id": 1, "val": "A"}, {"id": 2, "val": "B"}], ["id"])
    
    res = query("SELECT * FROM t ORDER BY id", {"t": table_name})
    data = json.loads(res)
    assert len(data) == 2
    assert data[0]["val"] == "A"
    
    # Update
    upsert(table_name, [{"id": 1, "val": "A_updated"}], ["id"])
    res = query("SELECT val FROM t WHERE id = 1", {"t": table_name})
    data = json.loads(res)
    assert data[0]["val"] == "A_updated"

def test_rollback_tool():
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
        NestedField(field_id=2, name="val", field_type=StringType(), required=False),
    )
    table_name = "default.rollback_me"
    catalog_manager.create_table(table_name, schema)

    upsert(table_name, [{"id": 1, "val": "A"}], ["id"])
    table = catalog_manager.load_table(table_name)
    first_snapshot_id = table.current_snapshot().snapshot_id

    upsert(table_name, [{"id": 1, "val": "A_updated"}], ["id"])
    res = query("SELECT val FROM t WHERE id = 1", {"t": table_name})
    assert json.loads(res)[0]["val"] == "A_updated"

    result = rollback(table_name, first_snapshot_id)
    assert "Successfully rolled back" in result

    res = query("SELECT val FROM t WHERE id = 1", {"t": table_name})
    assert json.loads(res)[0]["val"] == "A"

def test_get_table_schema_nonexistent_table_returns_error():
    result = get_table_schema("default.does_not_exist")
    assert result.startswith("Error:")

def test_get_table_schema_returns_schema():
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
    )
    catalog_manager.create_table("default.schema_check", schema)

    result = get_table_schema("default.schema_check")
    parsed = json.loads(result)
    assert "id" in parsed

def test_get_history_nonexistent_table_returns_error():
    result = get_history("default.does_not_exist")
    assert result.startswith("Error:")

def test_get_history_returns_serializable_summary():
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
    )
    table_name = "default.history_check"
    catalog_manager.create_table(table_name, schema)
    upsert(table_name, [{"id": 1}], ["id"])

    result = get_history(table_name)
    history = json.loads(result)
    assert len(history) == 1
    assert history[0]["summary"]["operation"] == "append"

def test_rollback_nonexistent_table_returns_error():
    result = rollback("default.does_not_exist", 123)
    assert result.startswith("Error:")

def test_query_tool_rejects_non_read_only_sql():
    result = query("DROP TABLE default.people")
    assert result.startswith("Error:")

def test_upsert_tool_rejects_invalid_join_cols():
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
    )
    table_name = "default.upsert_error_check"
    catalog_manager.create_table(table_name, schema)

    result = upsert(table_name, [{"id": 1}], ["nonexistent_column"])
    assert result.startswith("Error:")
