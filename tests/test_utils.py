"""
Tests for unprompted.utils

Covers: is_valid_filepath, language_to_extension,
        normalise_path, deduplicate_path, auto_filename
"""

import pytest
from unprompted.utils import (
    auto_filename,
    deduplicate_path,
    is_valid_filepath,
    language_to_extension,
    normalise_path,
)


# ---------------------------------------------------------------------------
# is_valid_filepath
# ---------------------------------------------------------------------------

class TestIsValidFilepath:
    """Tests for the filepath heuristic detector."""

    # --- Should ACCEPT ---

    def test_simple_python_file(self) -> None:
        assert is_valid_filepath("app.py") is True

    def test_nested_path(self) -> None:
        assert is_valid_filepath("src/routes/user.py") is True

    def test_dotfile(self) -> None:
        assert is_valid_filepath(".env") is True

    def test_dotfile_with_extension(self) -> None:
        assert is_valid_filepath(".env.example") is True

    def test_dockerfile_path(self) -> None:
        assert is_valid_filepath("docker/Dockerfile") is True

    def test_deep_nested_path(self) -> None:
        assert is_valid_filepath("backend/api/v1/routes.py") is True

    def test_hyphenated_filename(self) -> None:
        assert is_valid_filepath("my-component.tsx") is True

    def test_underscored_filename(self) -> None:
        assert is_valid_filepath("my_module.py") is True

    def test_css_file(self) -> None:
        assert is_valid_filepath("static/style.css") is True

    def test_config_toml(self) -> None:
        assert is_valid_filepath("pyproject.toml") is True

    # --- Should REJECT ---

    def test_empty_string(self) -> None:
        assert is_valid_filepath("") is False

    def test_plain_prose_sentence(self) -> None:
        assert is_valid_filepath("The application starts here.") is False

    def test_sentence_with_dot(self) -> None:
        assert is_valid_filepath("Now let's create the routes.") is False

    def test_markdown_table_row(self) -> None:
        assert is_valid_filepath("| app.py | main entry |") is False

    def test_tree_character_line(self) -> None:
        assert is_valid_filepath("├── app.py") is False

    def test_line_with_spaces(self) -> None:
        assert is_valid_filepath("my file.py") is False

    def test_line_ending_with_colon(self) -> None:
        assert is_valid_filepath("here is the config:") is False

    def test_line_with_parentheses(self) -> None:
        assert is_valid_filepath("app.py (main entry)") is False

    def test_very_long_line(self) -> None:
        assert is_valid_filepath("a" * 201) is False

    def test_prose_starting_with_the(self) -> None:
        assert is_valid_filepath("the main.py file does X") is False

    def test_list_item(self) -> None:
        assert is_valid_filepath("- app.py") is False


# ---------------------------------------------------------------------------
# language_to_extension
# ---------------------------------------------------------------------------

class TestLanguageToExtension:
    """Tests for language hint → file extension mapping."""

    def test_python(self) -> None:
        assert language_to_extension("python") == ".py"

    def test_python_short(self) -> None:
        assert language_to_extension("py") == ".py"

    def test_javascript(self) -> None:
        assert language_to_extension("javascript") == ".js"

    def test_js_short(self) -> None:
        assert language_to_extension("js") == ".js"

    def test_typescript(self) -> None:
        assert language_to_extension("typescript") == ".ts"

    def test_bash(self) -> None:
        assert language_to_extension("bash") == ".sh"

    def test_html(self) -> None:
        assert language_to_extension("html") == ".html"

    def test_css(self) -> None:
        assert language_to_extension("css") == ".css"

    def test_json(self) -> None:
        assert language_to_extension("json") == ".json"

    def test_yaml(self) -> None:
        assert language_to_extension("yaml") == ".yaml"

    def test_dockerfile(self) -> None:
        assert language_to_extension("dockerfile") == ".dockerfile"

    def test_case_insensitive(self) -> None:
        assert language_to_extension("Python") == ".py"
        assert language_to_extension("PYTHON") == ".py"
        assert language_to_extension("JavaScript") == ".js"

    def test_unknown_language(self) -> None:
        assert language_to_extension("cobol") is None

    def test_none_input(self) -> None:
        assert language_to_extension(None) is None

    def test_empty_string(self) -> None:
        assert language_to_extension("") is None


# ---------------------------------------------------------------------------
# normalise_path
# ---------------------------------------------------------------------------

class TestNormalisePath:
    """Tests for path normalisation."""

    def test_strips_whitespace(self) -> None:
        assert normalise_path("  app.py  ") == "app.py"

    def test_strips_backticks(self) -> None:
        assert normalise_path("`app.py`") == "app.py"

    def test_strips_quotes(self) -> None:
        assert normalise_path('"app.py"') == "app.py"
        assert normalise_path("'app.py'") == "app.py"

    def test_converts_backslashes(self) -> None:
        assert normalise_path("src\\routes\\app.py") == "src/routes/app.py"

    def test_removes_leading_dot_slash(self) -> None:
        assert normalise_path("./app.py") == "app.py"

    def test_removes_leading_slash(self) -> None:
        assert normalise_path("/app.py") == "app.py"

    def test_collapses_double_slashes(self) -> None:
        assert normalise_path("src//app.py") == "src/app.py"

    def test_nested_path_unchanged(self) -> None:
        assert normalise_path("src/routes/user.py") == "src/routes/user.py"

    def test_dotfile_unchanged(self) -> None:
        assert normalise_path(".env.example") == ".env.example"


# ---------------------------------------------------------------------------
# deduplicate_path
# ---------------------------------------------------------------------------

class TestDeduplicatePath:
    """Tests for path deduplication."""

    def test_no_conflict(self) -> None:
        existing: set[str] = set()
        assert deduplicate_path("app.py", existing) == "app.py"

    def test_first_conflict(self) -> None:
        existing = {"app.py"}
        assert deduplicate_path("app.py", existing) == "app_1.py"

    def test_second_conflict(self) -> None:
        existing = {"app.py", "app_1.py"}
        assert deduplicate_path("app.py", existing) == "app_2.py"

    def test_nested_path_conflict(self) -> None:
        existing = {"src/app.py"}
        result = deduplicate_path("src/app.py", existing)
        assert result == "src/app_1.py"

    def test_no_mutation_of_existing(self) -> None:
        existing = {"app.py"}
        deduplicate_path("app.py", existing)
        assert existing == {"app.py"}  # caller must add the result


# ---------------------------------------------------------------------------
# auto_filename
# ---------------------------------------------------------------------------

class TestAutoFilename:
    """Tests for fallback filename generation."""

    def test_python_language(self) -> None:
        assert auto_filename(1, "python") == "file_1.py"

    def test_javascript_language(self) -> None:
        assert auto_filename(2, "javascript") == "file_2.js"

    def test_no_language_defaults_to_txt(self) -> None:
        assert auto_filename(1, None) == "file_1.txt"

    def test_unknown_language_defaults_to_txt(self) -> None:
        assert auto_filename(3, "cobol") == "file_3.txt"

    def test_counter_increments(self) -> None:
        assert auto_filename(1, "python") == "file_1.py"
        assert auto_filename(2, "python") == "file_2.py"
        assert auto_filename(10, "python") == "file_10.py"