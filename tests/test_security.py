"""
Security tests for unprompted.

Tests that malicious input cannot:
- Write files outside the output directory
- Perform path traversal attacks
- Execute zip slip attacks
- Crash with oversized input
- Follow symlinks
"""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import pytest

from unprompted.builder import _is_safe_path, _sanitize_zip_path, build_project
from unprompted.models import FileObject
from unprompted.parser import _MAX_FILE_SIZE_BYTES, parse_file
from unprompted.utils import normalise_path


# ---------------------------------------------------------------------------
# Path Traversal Tests
# ---------------------------------------------------------------------------


class TestPathTraversal:
    """Ensure path traversal is blocked at every stage."""

    def test_normalise_strips_traversal(self) -> None:
        assert normalise_path("../../etc/passwd") == "etc/passwd"

    def test_normalise_strips_absolute_unix(self) -> None:
        assert normalise_path("/etc/passwd") == "etc/passwd"

    def test_normalise_strips_windows_absolute(self) -> None:
        result = normalise_path("C:/Windows/System32/evil.exe")
        assert not result.startswith("C:")
        assert "Windows" in result

    def test_normalise_strips_null_byte(self) -> None:
        with pytest.raises(ValueError, match="null byte"):
            normalise_path("app\x00.py")

    def test_normalise_nested_traversal(self) -> None:
        result = normalise_path("safe/../../etc/passwd")
        assert ".." not in result

    def test_builder_blocks_traversal(self, tmp_path: Path) -> None:
        evil = FileObject(
            path="../../evil.txt",
            content="hacked",
        )
        result = build_project([evil], tmp_path, force=True)
        # File must NOT exist outside tmp_path
        assert not (tmp_path.parent.parent / "evil.txt").exists()
        # Must be recorded as an error
        assert len(result.errors) > 0

    def test_builder_blocks_absolute_path(self, tmp_path: Path) -> None:
        evil = FileObject(
            path="/etc/evil.txt",
            content="hacked",
        )
        result = build_project([evil], tmp_path, force=True)
        assert not Path("/etc/evil.txt").exists()


# ---------------------------------------------------------------------------
# Safe Path Check Tests
# ---------------------------------------------------------------------------


class TestIsSafePath:
    """Tests for the _is_safe_path boundary check."""

    def test_safe_file_in_output(self, tmp_path: Path) -> None:
        target = tmp_path / "app.py"
        assert _is_safe_path(tmp_path, target) is True

    def test_safe_nested_file(self, tmp_path: Path) -> None:
        target = tmp_path / "src" / "routes" / "user.py"
        assert _is_safe_path(tmp_path, target) is True

    def test_unsafe_parent_traversal(self, tmp_path: Path) -> None:
        target = tmp_path.parent / "evil.py"
        assert _is_safe_path(tmp_path, target) is False

    def test_unsafe_absolute_path(self, tmp_path: Path) -> None:
        target = Path("/etc/passwd")
        assert _is_safe_path(tmp_path, target) is False

    def test_unsafe_deep_traversal(self, tmp_path: Path) -> None:
        target = Path("/root/.bashrc")
        assert _is_safe_path(tmp_path, target) is False


# ---------------------------------------------------------------------------
# Zip Slip Tests
# ---------------------------------------------------------------------------


class TestZipSlip:
    """Ensure zip archives cannot contain path traversal entries."""

    def test_sanitize_normal_path(self) -> None:
        assert _sanitize_zip_path("src/app.py") == "src/app.py"

    def test_sanitize_blocks_traversal(self) -> None:
        assert _sanitize_zip_path("../../etc/passwd") is None

    def test_sanitize_blocks_absolute(self) -> None:
        assert _sanitize_zip_path("/etc/passwd") is None

    def test_sanitize_blocks_dot_dot(self) -> None:
        assert _sanitize_zip_path("safe/../../../evil.txt") is None

    def test_zip_output_contains_safe_files(
        self, tmp_path: Path
    ) -> None:
        files = [
            FileObject(path="app.py", content="x=1"),
            FileObject(path="../../evil.py", content="evil"),
        ]
        build_project(files, tmp_path, as_zip=True, force=True)
        zip_path = tmp_path / "project.zip"
        with zipfile.ZipFile(zip_path) as zf:
            names = zf.namelist()
        # Safe file must be present
        assert "app.py" in names
        # Evil path must NOT be present
        assert "../../evil.py" not in names
        # No traversal sequences in any name
        for name in names:
            assert ".." not in name


# ---------------------------------------------------------------------------
# Symlink Tests
# ---------------------------------------------------------------------------


class TestSymlinkProtection:
    """Ensure symlinks in output directory are not followed."""

    @pytest.mark.skipif(
        os.name == "nt",
        reason=(
            "Windows requires admin privileges to create symlinks. "
            "Symlink protection is still active on Windows — "
            "this test is skipped because the test itself cannot "
            "create symlinks without elevated rights."
        ),
    )
    def test_symlink_write_blocked(self, tmp_path: Path) -> None:
        # Create a real file outside tmp_path
        real_target = tmp_path.parent / "real_file.txt"
        real_target.write_text("original")

        # Create a symlink inside tmp_path pointing outside
        symlink = tmp_path / "symlink.py"
        symlink.symlink_to(real_target)

        # Try to write through the symlink
        evil = FileObject(path="symlink.py", content="hacked")
        result = build_project([evil], tmp_path, force=True)

        # Original file must be completely untouched
        assert real_target.read_text() == "original"
        # Must be recorded as an error
        assert len(result.errors) > 0

        # Cleanup
        real_target.unlink()


# ---------------------------------------------------------------------------
# DoS / Size Limit Tests
# ---------------------------------------------------------------------------


class TestSizeLimits:
    """Ensure oversized input is rejected gracefully."""

    def test_large_file_rejected(self, tmp_path: Path) -> None:
        big_file = tmp_path / "big_input.txt"
        # Write one byte over the limit
        big_file.write_bytes(b"x" * (_MAX_FILE_SIZE_BYTES + 1))
        with pytest.raises(ValueError, match="too large"):
            parse_file(big_file)

    def test_normal_size_file_accepted(self, tmp_path: Path) -> None:
        normal_file = tmp_path / "normal.txt"
        normal_file.write_text(
            "### app.py\n```python\nx=1\n```"
        )
        result = parse_file(normal_file)
        assert len(result.blocks) == 1
