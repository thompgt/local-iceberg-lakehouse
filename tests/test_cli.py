from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner

from local_iceberg_lakehouse import cli as cli_module


@pytest.fixture(autouse=True)
def redirect_home(tmp_path, monkeypatch):
    # CLI commands construct CatalogManager() with no override, which defaults
    # to ~/.lakehouse/warehouse. Redirect HOME/USERPROFILE so tests never touch
    # the real user's home directory.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))


@pytest.fixture
def runner():
    return CliRunner()


def test_create_sample_table_then_already_exists(runner):
    first = runner.invoke(cli_module.cli, ["create-sample-table"])
    assert first.exit_code == 0
    assert "Created table default.people" in first.output

    second = runner.invoke(cli_module.cli, ["create-sample-table"])
    assert second.exit_code == 0
    assert "already exists" in second.output


def test_list_tables_shows_created_table(runner):
    runner.invoke(cli_module.cli, ["create-sample-table"])

    result = runner.invoke(cli_module.cli, ["list-tables"])
    assert result.exit_code == 0
    assert "default.people" in result.output


def test_list_tables_empty_lakehouse(runner):
    result = runner.invoke(cli_module.cli, ["list-tables"])
    assert result.exit_code == 0
    assert result.output.strip() == ""


def test_query_command_against_sample_table(runner):
    runner.invoke(cli_module.cli, ["create-sample-table"])

    result = runner.invoke(cli_module.cli, ["query", "default.people", "--sql", "SELECT COUNT(*) FROM people"])
    assert result.exit_code == 0
    assert "0" in result.output


def test_start_server_invokes_mcp_run(runner, monkeypatch):
    mock_run = MagicMock()
    monkeypatch.setattr(cli_module.mcp, "run", mock_run)

    result = runner.invoke(cli_module.cli, ["start-server"])
    assert result.exit_code == 0
    assert "Starting MCP server..." in result.output
    mock_run.assert_called_once()
