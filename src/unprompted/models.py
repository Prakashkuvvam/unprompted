"""
Data models for unprompted.

Defines the core data structures used across all stages
of the parsing and building pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class RawBlock:
    """
    Represents a single raw code block extracted from LLM output.

    Attributes:
        content:        The raw source code inside the triple backticks.
        language:       Optional language hint (e.g. 'python', 'js').
        context_before: The lines of text immediately preceding this block.
                        Used by the extractor to detect filenames.
        block_index:    Position of this block in the document (0-based).
    """

    content: str
    language: str | None
    context_before: list[str]
    block_index: int


@dataclass
class FileObject:
    """
    Represents a resolved file that should be written to disk.

    Attributes:
        path:       Relative path of the file (e.g. 'src/app.py').
        content:    Exact file content to write, indentation preserved.
        language:   Optional language hint carried from the raw block.
        source_block_index: Which RawBlock this came from (for debugging).
    """

    path: str
    content: str
    language: str | None = None
    source_block_index: int = 0

    def resolved_path(self, base: Path) -> Path:
        """Return the absolute path given a base output directory."""
        return base / self.path


@dataclass
class ParseResult:
    """
    Holds the full output of the parser stage.

    Attributes:
        blocks:     All RawBlocks found in the document.
        raw_text:   The original input text (for debugging / dry-run preview).
    """

    blocks: list[RawBlock]
    raw_text: str


@dataclass
class ExtractResult:
    """
    Holds the full output of the extractor stage.

    Attributes:
        files:          All resolved FileObjects ready to be built.
        skipped_blocks: Block indices that could not be mapped to a file.
    """

    files: list[FileObject]
    skipped_blocks: list[int] = field(default_factory=list)


@dataclass
class BuildResult:
    """
    Summary of what the builder stage actually did.

    Attributes:
        created:    Paths that were successfully written.
        skipped:    Paths that were skipped (e.g. already exist, no --force).
        errors:     Paths where an error occurred, with message.
        dry_run:    True if no files were actually written.
    """

    created: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    errors: list[tuple[str, str]] = field(default_factory=list)
    dry_run: bool = False
