"""
Tests for unprompted.parser

Covers: block extraction, language detection,
        tree/shell discarding, unclosed fences.
"""

import pytest
from unprompted.parser import parse_text


class TestParseText:
    """Tests for the parse_text() function."""

    def test_rejects_empty_input(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            parse_text("")

    def test_rejects_whitespace_only(self) -> None:
        with pytest.raises(ValueError, match="empty"):
            parse_text("   \n\n  ")

    def test_single_block_no_language(self) -> None:
        text = "```\nhello world\n```"
        result = parse_text(text)
        assert len(result.blocks) == 1
        assert result.blocks[0].content == "hello world"
        assert result.blocks[0].language is None

    def test_single_block_with_language(self) -> None:
        text = "```python\nprint('hi')\n```"
        result = parse_text(text)
        assert len(result.blocks) == 1
        assert result.blocks[0].language == "python"
        assert result.blocks[0].content == "print('hi')"

    def test_multiple_blocks(self) -> None:
        text = (
            "```python\nprint('a')\n```\n"
            "some text\n"
            "```js\nconsole.log('b')\n```"
        )
        result = parse_text(text)
        assert len(result.blocks) == 2
        assert result.blocks[0].language == "python"
        assert result.blocks[1].language == "js"

    def test_context_captured(self) -> None:
        text = "### app.py\n```python\nprint('hi')\n```"
        result = parse_text(text)
        assert len(result.blocks) == 1
        assert any("app.py" in line for line in result.blocks[0].context_before)

    def test_indentation_preserved(self) -> None:
        text = "```python\ndef foo():\n    return 42\n```"
        result = parse_text(text)
        assert "    return 42" in result.blocks[0].content

    def test_empty_block_discarded(self) -> None:
        text = "```python\n```"
        result = parse_text(text)
        assert len(result.blocks) == 0

    def test_whitespace_only_block_discarded(self) -> None:
        text = "```python\n   \n\n   \n```"
        result = parse_text(text)
        assert len(result.blocks) == 0

    def test_directory_tree_block_discarded(self) -> None:
        text = (
            "```\n"
            "project/\n"
            "├── app.py\n"
            "├── config.py\n"
            "└── requirements.txt\n"
            "```"
        )
        result = parse_text(text)
        assert len(result.blocks) == 0

    def test_real_code_not_discarded_despite_slash(self) -> None:
        text = "```python\nimport os\npath = os.path.join('a', 'b')\n```"
        result = parse_text(text)
        assert len(result.blocks) == 1

    def test_unclosed_fence_saved(self) -> None:
        text = "### app.py\n```python\nprint('unclosed')"
        result = parse_text(text)
        assert len(result.blocks) == 1
        assert "unclosed" in result.blocks[0].content

    def test_block_index_assigned(self) -> None:
        text = (
            "```python\nblock_a\n```\n"
            "```python\nblock_b\n```"
        )
        result = parse_text(text)
        assert result.blocks[0].block_index == 0
        assert result.blocks[1].block_index == 1

    def test_no_blocks_returns_empty_list(self) -> None:
        text = "Just some plain text with no code blocks at all."
        result = parse_text(text)
        assert result.blocks == []

    def test_language_case_preserved(self) -> None:
        # Language hint should be preserved as-is (lowercasing
        # is the extractor's/utils' job)
        text = "```Python\nprint('hi')\n```"
        result = parse_text(text)
        assert result.blocks[0].language == "Python"