import logging
import os
from typing import List, Optional
from pyiceberg.catalog import load_catalog
from pyiceberg.exceptions import (
    NamespaceAlreadyExistsError,
    NoSuchNamespaceError,
    NoSuchTableError,
)
from pyiceberg.table import Table
from pyiceberg.schema import Schema
from pyiceberg.partitioning import PartitionSpec

logger = logging.getLogger(__name__)

class CatalogManager:
    def __init__(self, catalog_name: str = "local", warehouse_path: Optional[str] = None):
        self.catalog_name = catalog_name
        if warehouse_path is None:
            warehouse_path = os.path.expanduser("~/.lakehouse/warehouse")
        
        self.warehouse_path = warehouse_path
        os.makedirs(self.warehouse_path, exist_ok=True)
        
        self.catalog = load_catalog(
            catalog_name,
            **{
                "type": "sql",
                "uri": f"sqlite:///{os.path.join(self.warehouse_path, 'catalog.db')}",
                "warehouse": f"file://{self.warehouse_path}",
            },
        )

    def create_table(self, table_name: str, schema: Schema, partition_spec: PartitionSpec = PartitionSpec()) -> Table:
        namespace = ".".join(table_name.split(".")[:-1])
        if namespace:
            try:
                self.catalog.create_namespace(namespace)
            except NamespaceAlreadyExistsError:
                logger.debug("Namespace '%s' already exists, skipping creation.", namespace)

        return self.catalog.create_table(
            identifier=table_name,
            schema=schema,
            partition_spec=partition_spec,
        )

    def load_table(self, table_name: str) -> Table:
        return self.catalog.load_table(table_name)

    def list_tables(self, namespace: str = "default") -> List[str]:
        # list_tables returns list of tuples representing table identifiers
        # e.g., [('default', 'test_table')]
        try:
            return [".".join(t) for t in self.catalog.list_tables(namespace)]
        except NoSuchNamespaceError:
            logger.debug("Namespace '%s' does not exist yet, no tables to list.", namespace)
            return []
        except Exception:
            logger.exception("Failed to list tables in namespace '%s'.", namespace)
            return []

    def drop_table(self, table_name: str):
        self.catalog.drop_table(table_name)

    def table_exists(self, table_name: str) -> bool:
        try:
            self.load_table(table_name)
            return True
        except NoSuchTableError:
            return False
