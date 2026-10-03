import hashlib
from pathlib import Path

from certhub.config import (
    BASE_DIR,
    create_consultation_directory,
    downloads_directory,
    find_consultation_directory,
    resolve_project_path,
)
from certhub.web import OUTPUT_ROOT, _database_path


def test_relative_project_paths_are_independent_of_current_directory(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("CERTHUB_DB_PATH", raising=False)

    assert resolve_project_path("config/config.yaml") == BASE_DIR / "config" / "config.yaml"
    assert _database_path() == BASE_DIR / "data" / "consultas_demo.sqlite3"
    assert OUTPUT_ROOT == downloads_directory()


def test_absolute_database_override_is_preserved(monkeypatch, tmp_path):
    database = tmp_path / "custom.sqlite3"
    monkeypatch.setenv("CERTHUB_DB_PATH", str(database))

    assert _database_path() == database


def test_relative_database_override_is_project_relative(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("CERTHUB_DB_PATH", "custom/consultas.sqlite3")

    assert _database_path() == BASE_DIR / "custom" / "consultas.sqlite3"


def test_downloads_override_is_used_and_single_folder_has_required_name(monkeypatch, tmp_path):
    downloads = tmp_path / "operator-downloads"
    monkeypatch.setenv("CERTHUB_DOWNLOADS_DIR", str(downloads))

    folder, started_at = create_consultation_directory("12345678000195")

    assert folder.parent == downloads
    assert folder.name == f"12345678000195_{started_at:%Y-%m-%d_%H-%M-%S}"
    assert folder.is_dir()


def test_consultation_folder_lookup_uses_hash_without_persisted_document(tmp_path):
    document = "12345678000195"
    folder, started_at = create_consultation_directory(document, tmp_path)
    digest = hashlib.sha256(document.encode("ascii")).hexdigest()

    assert find_consultation_directory(digest, started_at.isoformat(), tmp_path) == folder
    assert find_consultation_directory("0" * 64, started_at.isoformat(), tmp_path) is None