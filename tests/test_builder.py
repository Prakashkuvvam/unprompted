"""
Tests for unprompted.builder

Covers: file creation, dry-run, force flag,
        directory creation, zip output, conflict handling.
"""

import zipfile
from pathlib import Path

import pytest
from unprompted.builder import build_project
from unprompted.models import FileObject


def _make_file(path: str, content: str = "# test") -> FileObject:
    """Helper to build a FileObject for testing."""
    return FileObject(path=path, content=content)


class TestDryRun:
    """--dry-run must not touch the filesystem."""

    def test_no_files_written_in_dry_run(self, tmp_path: Path) -> None:
        files = [_make_file("app.py", "print('hi')")]
        result = build_project(files, tmp_path, dry_run=True)
        assert not (tmp_path / "app.py").exists()

    def test_dry_run_result_lists_files(self, tmp_path: Path) -> None:
        files = [_make_file("app.py")]
        result = build_project(files, tmp_path, dry_run=True)
        assert "app.py" in result.created

    def test_dry_run_flag_set_on_result(self, tmp_path: Path) -> None:
        result = build_project([], tmp_path, dry_run=True)
        assert result.dry_run is True


class TestFileCreation:
    """Normal file writing."""

    def test_creates_single_file(self, tmp_path: Path) -> None:
        files = [_make_file("app.py", "print('hello')")]
        result = build_project(files, tmp_path)
        assert (tmp_path / "app.py").exists()
        assert (tmp_path / "app.py").read_text() == "print('hello')"

    def test_creates_multiple_files(self, tmp_path: Path) -> None:
        files = [
            _make_file("app.py", "x = 1"),
            _make_file("config.py", "y = 2"),
        ]
        build_project(files, tmp_path)
        assert (tmp_path / "app.py").exists()
        assert (tmp_path / "config.py").exists()

    def test_creates_nested_directories(self, tmp_path: Path) -> None:
        files = [_make_file("src/routes/user.py", "# user routes")]
        build_project(files, tmp_path)
        assert (tmp_path / "src" / "routes" / "user.py").exists()

    def test_content_written_exactly(self, tmp_path: Path) -> None:
        code = "def foo():\n    return 42\n"
        files = [_make_file("foo.py", code)]
        build_project(files, tmp_path)
        assert (tmp_path / "foo.py").read_text() == code

    def test_result_tracks_created(self, tmp_path: Path) -> None:
        files = [_make_file("app.py")]
        result = build_project(files, tmp_path)
        assert "app.py" in result.created

    def test_empty_file_list(self, tmp_path: Path) -> None:
        result = build_project([], tmp_path)
        assert result.created == []
        assert result.errors == []


class TestForceFlag:
    """--force overwrites; without it existing files are skipped."""

    def test_existing_file_skipped_without_force(self, tmp_path: Path) -> None:
        target = tmp_path / "app.py"
        target.write_text("original")
        files = [_make_file("app.py", "new content")]
        result = build_project(files, tmp_path, force=False)
        assert target.read_text() == "original"
        assert "app.py" in result.skipped

    def test_existing_file_overwritten_with_force(self, tmp_path: Path) -> None:
        target = tmp_path / "app.py"
        target.write_text("original")
        files = [_make_file("app.py", "new content")]
        result = build_project(files, tmp_path, force=True)
        assert target.read_text() == "new content"
        assert "app.py" in result.created


class TestZipOutput:
    """--zip creates a valid zip archive."""

    def test_zip_created(self, tmp_path: Path) -> None:
        files = [_make_file("app.py", "x = 1")]
        build_project(files, tmp_path, as_zip=True)
        assert (tmp_path / "project.zip").exists()

    def test_zip_contains_correct_files(self, tmp_path: Path) -> None:
        files = [
            _make_file("app.py", "x = 1"),
            _make_file("src/utils.py", "y = 2"),
        ]
        build_project(files, tmp_path, as_zip=True)
        with zipfile.ZipFile(tmp_path / "project.zip") as zf:
            names = zf.namelist()
        assert "app.py" in names
        assert "src/utils.py" in names

    def test_zip_content_correct(self, tmp_path: Path) -> None:
        files = [_make_file("hello.py", "print('zip')")]
        build_project(files, tmp_path, as_zip=True)
        with zipfile.ZipFile(tmp_path / "project.zip") as zf:
            content = zf.read("hello.py").decode()
        assert content == "print('zip')"

    def test_zip_dry_run_not_created(self, tmp_path: Path) -> None:
        files = [_make_file("app.py")]
        build_project(files, tmp_path, as_zip=True, dry_run=True)
        assert not (tmp_path / "project.zip").exists()

    def test_existing_zip_skipped_without_force(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "project.zip"
        zip_path.write_bytes(b"old")
        files = [_make_file("app.py")]
        result = build_project(files, tmp_path, as_zip=True, force=False)
        assert zip_path.read_bytes() == b"old"
        assert "project.zip" in result.skipped

    def test_existing_zip_overwritten_with_force(self, tmp_path: Path) -> None:
        zip_path = tmp_path / "project.zip"
        zip_path.write_bytes(b"old")
        files = [_make_file("app.py", "new")]
        build_project(files, tmp_path, as_zip=True, force=True)
        assert zipfile.is_zipfile(zip_path)