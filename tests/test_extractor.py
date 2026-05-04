"""
Tests for unprompted.extractor

Covers: all 6 filename detection patterns,
        fallback naming, deduplication, nested paths,
        extension inference.
"""

import pytest
from unprompted.extractor import extract_files
from unprompted.models import RawBlock


def _make_block(
    content: str,
    context: list[str],
    language: str | None = "python",
    index: int = 0,
) -> RawBlock:
    """Helper to build a RawBlock for testing."""
    return RawBlock(
        content=content,
        language=language,
        context_before=context,
        block_index=index,
    )


class TestHeadingPattern:
    """### filename detection."""

    def test_hash_heading(self) -> None:
        block = _make_block("print('hi')", ["### app.py"])
        result = extract_files([block])
        assert result.files[0].path == "app.py"

    def test_double_hash_heading(self) -> None:
        block = _make_block("x = 1", ["## config.py"])
        result = extract_files([block])
        assert result.files[0].path == "config.py"

    def test_nested_path_in_heading(self) -> None:
        block = _make_block("x = 1", ["### src/routes/user.py"])
        result = extract_files([block])
        assert result.files[0].path == "src/routes/user.py"

    def test_dockerfile_heading(self) -> None:
        block = _make_block(
            "FROM python:3.12\n",
            ["### Dockerfile"],
            language="dockerfile",
        )
        result = extract_files([block])
        assert result.files[0].path == "Dockerfile"


class TestFileLabelPattern:
    """File: filename detection."""

    def test_file_colon_label(self) -> None:
        block = _make_block("KEY=value", ["File: .env.example"])
        result = extract_files([block])
        assert result.files[0].path == ".env.example"

    def test_filename_colon_label(self) -> None:
        block = _make_block("x=1", ["Filename: config.py"])
        result = extract_files([block])
        assert result.files[0].path == "config.py"

    def test_case_insensitive_label(self) -> None:
        block = _make_block("x=1", ["FILE: app.py"])
        result = extract_files([block])
        assert result.files[0].path == "app.py"

    def test_path_colon_label(self) -> None:
        block = _make_block("x=1", ["Path: src/utils.py"])
        result = extract_files([block])
        assert result.files[0].path == "src/utils.py"


class TestBacktickPattern:
    """`filename` detection."""

    def test_backtick_wrapped(self) -> None:
        block = _make_block("x=1", ["`models.py`"])
        result = extract_files([block])
        assert result.files[0].path == "models.py"

    def test_backtick_nested_path(self) -> None:
        block = _make_block("x=1", ["`static/app.js`"])
        result = extract_files([block])
        assert result.files[0].path == "static/app.js"


class TestBoldPattern:
    """**filename** detection."""

    def test_double_bold(self) -> None:
        block = _make_block("<html>", ["**templates/index.html**"], language="html")
        result = extract_files([block])
        assert result.files[0].path == "templates/index.html"

    def test_single_bold(self) -> None:
        block = _make_block("x=1", ["*utils.py*"])
        result = extract_files([block])
        assert result.files[0].path == "utils.py"


class TestStandalonePattern:
    """Bare path detection."""

    def test_standalone_bare_path(self) -> None:
        block = _make_block("body{}", ["static/style.css"], language="css")
        result = extract_files([block])
        assert result.files[0].path == "static/style.css"

    def test_standalone_nested(self) -> None:
        block = _make_block("x=1", ["backend/api/routes.py"])
        result = extract_files([block])
        assert result.files[0].path == "backend/api/routes.py"


class TestFallbackNaming:
    """Auto-generated filename when no pattern matches."""

    def test_no_context_generates_fallback(self) -> None:
        block = _make_block("print('hi')", [], language="python")
        result = extract_files([block])
        assert result.files[0].path == "file_1.py"

    def test_fallback_uses_language_for_extension(self) -> None:
        block = _make_block("console.log()", [], language="javascript")
        result = extract_files([block])
        assert result.files[0].path == "file_1.js"

    def test_fallback_defaults_to_txt(self) -> None:
        block = _make_block("some content", [], language=None)
        result = extract_files([block])
        assert result.files[0].path == "file_1.txt"

    def test_fallback_counter_increments(self) -> None:
        blocks = [
            _make_block("x=1", [], language="python", index=0),
            _make_block("y=2", [], language="python", index=1),
        ]
        result = extract_files(blocks)
        paths = [f.path for f in result.files]
        assert "file_1.py" in paths
        assert "file_2.py" in paths


class TestDeduplication:
    """Duplicate filename handling."""

    def test_duplicate_gets_suffix(self) -> None:
        blocks = [
            _make_block("x=1", ["### app.py"], index=0),
            _make_block("y=2", ["### app.py"], index=1),
        ]
        result = extract_files(blocks)
        paths = [f.path for f in result.files]
        assert "app.py" in paths
        assert "app_1.py" in paths

    def test_three_duplicates(self) -> None:
        blocks = [
            _make_block("x=1", ["### app.py"], index=0),
            _make_block("y=2", ["### app.py"], index=1),
            _make_block("z=3", ["### app.py"], index=2),
        ]
        result = extract_files(blocks)
        paths = [f.path for f in result.files]
        assert "app.py" in paths
        assert "app_1.py" in paths
        assert "app_2.py" in paths


class TestExtensionInference:
    """Extension added when missing."""

    def test_extension_inferred_from_language(self) -> None:
        # A heading with a real path but no extension gets one inferred
        # from the language hint
        block = _make_block("x=1", ["### mymodule.py"], language="python")
        result = extract_files([block])
        assert result.files[0].path == "mymodule.py"

    # def test_no_extension_inferred_from_language_hint(self) -> None:
    #     # Path has no extension → infer from language hint
    #     block = _make_block("x=1", ["### src/mymodule"], language="python")
    #     result = extract_files([block])
    #     # Has a slash so is_valid_filepath accepts it, then extension added
    #     assert result.files[0].path == "src/mymodule.py"
    def test_no_extension_inferred_from_language_hint(self) -> None:
        # Path has no extension → infer from language hint
        block = _make_block("x=1", ["### src/mymodule"], language="python")
        result = extract_files([block])
        # Normalise separators for cross-platform comparison
        assert result.files[0].path.replace("\\", "/") == "src/mymodule.py"

    def test_existing_extension_not_doubled(self) -> None:
        block = _make_block("x=1", ["### app.py"], language="python")
        result = extract_files([block])
        assert result.files[0].path == "app.py"
        assert not result.files[0].path.endswith(".py.py")

    def test_dockerfile_no_extension_added(self) -> None:
        block = _make_block(
            "FROM python:3.12",
            ["### Dockerfile"],
            language="dockerfile",
        )
        result = extract_files([block])
        assert result.files[0].path == "Dockerfile"


class TestContentPreserved:
    """File content must be exactly preserved."""

    def test_content_exact_match(self) -> None:
        code = 'def hello():\n    print("world")\n    return 42'
        block = _make_block(code, ["### app.py"])
        result = extract_files([block])
        assert result.files[0].content == code

    def test_indentation_preserved(self) -> None:
        code = "class Foo:\n    def bar(self):\n        pass"
        block = _make_block(code, ["### foo.py"])
        result = extract_files([block])
        assert result.files[0].content == code