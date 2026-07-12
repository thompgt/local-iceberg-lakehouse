import pytest
import pyarrow as pa
from pyiceberg.schema import Schema
from pyiceberg.types import NestedField, StringType, LongType
from local_iceberg_lakehouse.catalog import CatalogManager
from local_iceberg_lakehouse.query import QueryEngine

@pytest.fixture
def lakehouse(tmp_path):
    warehouse_path = tmp_path / "warehouse"
    cm = CatalogManager(warehouse_path=str(warehouse_path))
    qe = QueryEngine(cm)
    return cm, qe

def test_append_and_query(lakehouse):
    cm, qe = lakehouse
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
        NestedField(field_id=2, name="name", field_type=StringType(), required=False),
    )
    table_name = "default.people"
    cm.create_table(table_name, schema)
    
    data = pa.Table.from_pydict({
        "id": [1, 2],
        "name": ["Alice", "Bob"]
    })
    qe.append_data(table_name, data)
    
    result = qe.query("SELECT COUNT(*) FROM people", table_mapping={"people": table_name})
    assert result.to_pydict()["count_star()"][0] == 2

def test_upsert(lakehouse):
    cm, qe = lakehouse
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
        NestedField(field_id=2, name="name", field_type=StringType(), required=False),
    )
    table_name = "default.people_upsert"
    cm.create_table(table_name, schema)
    
    initial_data = pa.Table.from_pydict({
        "id": [1, 2],
        "name": ["Alice", "Bob"]
    })
    qe.append_data(table_name, initial_data)
    
    upsert_data = pa.Table.from_pydict({
        "id": [2, 3],
        "name": ["Bobby", "Charlie"]
    })
    qe.upsert_data(table_name, upsert_data, join_cols=["id"])
    
    result = qe.query("SELECT * FROM people ORDER BY id", table_mapping={"people": table_name}).to_pydict()
    assert result["id"] == [1, 2, 3]
    assert result["name"] == ["Alice", "Bobby", "Charlie"]

def test_upsert_rejects_invalid_join_cols(lakehouse):
    cm, qe = lakehouse
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
        NestedField(field_id=2, name="name", field_type=StringType(), required=False),
    )
    table_name = "default.people_injection"
    cm.create_table(table_name, schema)

    initial_data = pa.Table.from_pydict({
        "id": [1],
        "name": ["Alice"]
    })
    qe.append_data(table_name, initial_data)

    malicious_data = pa.Table.from_pydict({
        "id": [1],
        "name": ["Eve"]
    })
    with pytest.raises(ValueError):
        qe.upsert_data(table_name, malicious_data, join_cols=["id) OR 1=1 --"])

@pytest.mark.parametrize(
    "sql",
    [
        "ATTACH '/etc/passwd' AS pwned",
        "COPY (SELECT 1) TO '/tmp/exfil.csv'",
        "INSTALL httpfs",
        "PRAGMA database_list",
        "SELECT 1; DROP TABLE people",
        "DELETE FROM people",
    ],
)
def test_query_rejects_non_read_only_sql(lakehouse, sql):
    cm, qe = lakehouse
    with pytest.raises(ValueError):
        qe.query(sql)

def test_query_allows_select(lakehouse):
    cm, qe = lakehouse
    result = qe.query("SELECT 1 AS n").to_pydict()
    assert result["n"] == [1]
