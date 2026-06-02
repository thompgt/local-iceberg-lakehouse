import os
import shutil
import pytest
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, StringType, IntegerType
from local_iceberg_lakehouse.catalog import CatalogManager

@pytest.fixture
def temp_warehouse(tmp_path):
    warehouse_path = tmp_path / "warehouse"
    return str(warehouse_path)

def test_catalog_initialization(temp_warehouse):
    cm = CatalogManager(warehouse_path=temp_warehouse)
    assert cm.warehouse_path == temp_warehouse
    assert os.path.exists(temp_warehouse)
    assert os.path.exists(os.path.join(temp_warehouse, "catalog.db"))

def test_create_and_list_table(temp_warehouse):
    cm = CatalogManager(warehouse_path=temp_warehouse)
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=IntegerType(), required=True),
        NestedField(field_id=2, name="name", field_type=StringType(), required=False),
    )
    table_name = "default.test_table"
    cm.create_table(table_name, schema)
    
    assert cm.table_exists(table_name)
    tables = cm.list_tables()
    assert table_name in tables

def test_drop_table(temp_warehouse):
    cm = CatalogManager(warehouse_path=temp_warehouse)
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=IntegerType(), required=True),
    )
    table_name = "default.drop_me"
    cm.create_table(table_name, schema)
    assert cm.table_exists(table_name)
    
    cm.drop_table(table_name)
    assert not cm.table_exists(table_name)
