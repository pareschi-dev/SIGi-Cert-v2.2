from typer.testing import CliRunner

from certhub.main import app

runner = CliRunner()


def test_version_command():
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert "CertHub v" in result.stdout


def test_help_command():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "CertHub" in result.stdout


def test_list_portals_command():
    result = runner.invoke(app, ["listar-portais"])
    assert result.exit_code == 0
    assert "fgts" in result.stdout
