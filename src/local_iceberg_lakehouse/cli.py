import click
import json
from .catalog import CatalogManager
from .query import QueryEngine
from .server import mcp

@click.group()
def cli():
    """Local Iceberg Lakehouse CLI"""
    pass

@cli.command()
def list_tables():
    """List all tables in the lakehouse."""
    cm = CatalogManager()
    tables = cm.list_tables()
    for table in tables:
        click.echo(table)

@cli.command()
@click.argument("table_name")
@click.option("--sql", required=True, help="SQL query to run")
def query(table_name, sql):
    """Run a query against a table."""
    cm = CatalogManager()
    qe = QueryEngine(cm)
    result = qe.query(sql, {table_name.split(".")[-1]: table_name})
    click.echo(result.to_pandas().to_string())

@cli.command()
def create_sample_table():
    """Create a sample people table."""
    from pyiceberg.schema import Schema
    from pyiceberg.types import NestedField, StringType, LongType
    
    cm = CatalogManager()
    schema = Schema(
        NestedField(field_id=1, name="id", field_type=LongType(), required=False),
        NestedField(field_id=2, name="name", field_type=StringType(), required=False),
    )
    table_name = "default.people"
    if not cm.table_exists(table_name):
        cm.create_table(table_name, schema)
        click.echo(f"Created table {table_name}")
    else:
        click.echo(f"Table {table_name} already exists")

@cli.command()
def start_server():
    """Start the MCP server."""
    click.echo("Starting MCP server...")
    mcp.run()

if __name__ == "__main__":
    cli()
