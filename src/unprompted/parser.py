"""
Stage 1 — Parser.

Reads the raw input text and extracts all triple-backtick code blocks,
along with surrounding context lines used to detect filenames later.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

from unprompted.models import ParseResult, RawBlock
from unprompted.utils import _SPECIAL_FILENAMES, is_valid_filepath

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Regex patterns
# ---------------------------------------------------------------------------

# ✅ NEW — supports both ``` and ```` fences (3 or 4 backticks)
# This handles README.md blocks that use 4-backtick fences
_FENCE_OPEN: re.Pattern[str] = re.compile(
    r"^[ \t]*(?P<fence>`{3,4})[ \t]*(?P<lang>[a-zA-Z0-9_+\-.]*)[ \t]*$"
)

# Separate close patterns for each fence width
# Closing fence must match same width as opening fence
_FENCE_3_CLOSE: re.Pattern[str] = re.compile(r"^[ \t]*```[ \t]*$")
_FENCE_4_CLOSE: re.Pattern[str] = re.compile(r"^[ \t]*````[ \t]*$")

# Increased from 10 to 15 — captures more context lines before each block
# This ensures headings that appear further above the fence are still captured
_CONTEXT_LINES: int = 15

# ---------------------------------------------------------------------------
# Security limits
# ---------------------------------------------------------------------------

# Maximum input file size (50MB)
_MAX_FILE_SIZE_MB: int = 50
_MAX_FILE_SIZE_BYTES: int = _MAX_FILE_SIZE_MB * 1024 * 1024

# Maximum size per individual code block (10MB)
_MAX_BLOCK_SIZE_BYTES: int = 10 * 1024 * 1024

# ---------------------------------------------------------------------------
# Block classification helpers
# ---------------------------------------------------------------------------

_TREE_CHARS_RE: re.Pattern[str] = re.compile(r"[├└─│┬┼╠╚╔╗╝]")

# ✅ EXPANDED — now covers git, uv, curl, brew, wget and more
# Previous version missed: git clone, cd oss-analyzer, uv sync etc.
_SHELL_COMMAND_RE: re.Pattern[str] = re.compile(
    r"^\s*(?:"
    # Package managers
    r"pip|pip3|pipx|uv|uvx|npm|node|yarn|pnpm|brew|apt|apt-get|"
    r"yum|dnf|pacman|choco|scoop|winget|"
    # Python / app runners
    r"python|python3|flask|uvicorn|gunicorn|django|"
    # Build tools
    r"cargo|go|rustc|make|gradle|mvn|maven|"
    # Container / cloud
    r"docker|kubectl|helm|terraform|ansible|"
    # Version control
    r"git|gh|svn|"
    # Shell builtins and common commands
    r"cd |ls |mkdir |cp |mv |rm |cat |echo |export |source |"
    r"curl |wget |chmod |chown |sudo |ssh |scp |rsync |"
    r"touch |find |grep |sed |awk |sort |head |tail |"
    # Common CLI patterns
    r"set |unset |eval |exec |"
    # Comments and shebangs — lines starting with # are shell comments
    r"#"
    r")",
    re.IGNORECASE,
)

# ✅ NEW — detects terminal output display blocks
# These are blocks that show WHAT a tool outputs — not real files
# Identified by: emoji indicators, box drawing chars, status lines
# _OUTPUT_DISPLAY_RE: re.Pattern[str] = re.compile(
#     r"(?:"
#     # Common output emojis used in CLI tools
#     r"[🔍🟢🟡🟠🔴⭐✅❌⚠️📊🛠️🎯🚀📅👥🍴🔀📖⚖️🤝🗄️💻📝⚙️🐳🔨]|"
#     # Separator lines (═══ or ─── fills)
#     r"^\s*[─═]{3,}\s*$|"
#     # Box drawing characters
#     r"[┌┐└┘├┤┬┴┼║╔╗╚╝╠╣╦╩╬]|"
#     # Progress bar characters
#     r"[█░▓▒▤▥]|"
#     # Score/stat patterns like "78/100" or "1,200"
#     r"\d+/\d+|"
#     # Common output label patterns
#     r"Health Score:|Stars|Forks|Last Commit|PR Merge Rate|"
#     r"Contributors|Open Issues|CONTRIBUTING|Archived"
#     r")",
#     re.IGNORECASE,
# )
# ✅ UPDATED — added arrow patterns and roadmap indicators
_OUTPUT_DISPLAY_RE: re.Pattern[str] = re.compile(
    r"(?:"
    # Common output emojis used in CLI tools
    r"[🔍🟢🟡🟠🔴⭐✅❌⚠️📊🛠️🎯🚀📅👥🍴🔀📖⚖️🤝🗄️💻📝⚙️🐳🔨]|"
    # Separator lines (═══ or ─── fills)
    r"^\s*[─═]{3,}\s*$|"
    # Box drawing characters
    r"[┌┐└┘├┤┬┴┼║╔╗╚╝╠╣╦╩╬]|"
    # Progress bar characters
    r"[█░▓▒▤▥]|"
    # Score/stat patterns like "78/100" or "1,200"
    r"\d+/\d+|"
    # Common output label patterns
    r"Health Score:|Stars|Forks|Last Commit|PR Merge Rate|"
    r"Contributors|Open Issues|CONTRIBUTING|Archived|"
    # ✅ NEW — roadmap/changelog arrow patterns
    # e.g.  v0.2  → Profile matcher
    #        Step 1 → do something
    r"→|"
    # ✅ NEW — version indicators at start of line
    # e.g.  v0.2  /  v1.0.0
    r"^\s*v\d+\.\d+"
    r")",
    re.IGNORECASE,
)


def parse_file(input_path: Path) -> ParseResult:
    """
    Read input_path and extract all code blocks.

    Args:
        input_path: Path to the raw LLM output text file.

    Returns:
        A ParseResult with all found RawBlocks.

    Raises:
        FileNotFoundError: If input_path does not exist.
        PermissionError:   If the file cannot be read.
        ValueError:        If the file is empty or too large.
    """
    logger.debug("Reading input file: %s", input_path)

    try:
        # Check file size before reading into memory
        file_size = input_path.stat().st_size
        if file_size > _MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"Input file is too large: "
                f"{file_size / 1024 / 1024:.1f}MB "
                f"(max {_MAX_FILE_SIZE_MB}MB). "
                f"Split it into smaller files."
            )

        raw_text = input_path.read_text(encoding="utf-8", errors="replace")

    except FileNotFoundError:
        raise FileNotFoundError(
            f"Input file not found: {input_path}"
        ) from None
    except PermissionError:
        raise PermissionError(
            f"Cannot read input file (permission denied): {input_path}"
        ) from None

    if not raw_text.strip():
        raise ValueError(f"Input file is empty: {input_path}")

    logger.debug("File size: %d bytes", len(raw_text))

    blocks = _extract_blocks(raw_text)
    logger.info("Parser found %d code block(s)", len(blocks))

    return ParseResult(blocks=blocks, raw_text=raw_text)


def parse_text(raw_text: str) -> ParseResult:
    """
    Parse LLM output from a string instead of a file.

    Args:
        raw_text: The full LLM output as a string.

    Returns:
        A ParseResult with all found RawBlocks.
    """
    if not raw_text.strip():
        raise ValueError("Input text is empty.")

    blocks = _extract_blocks(raw_text)
    logger.info("Parser found %d code block(s)", len(blocks))
    return ParseResult(blocks=blocks, raw_text=raw_text)


def _extract_blocks(text: str) -> list[RawBlock]:
    """
    Core state-machine parser.

    Supports both triple (```) and quad (````) backtick fences.
    The closing fence must match the same width as the opening fence.
    This correctly handles README blocks that wrap inner ``` fences
    inside ```` fences.

    Automatically discards:
    - Empty blocks
    - Oversized blocks (> 10MB)
    - Pure directory tree blocks
    - Pure shell-command example blocks
    - Terminal output display blocks

    Args:
        text: The full raw input string.

    Returns:
        Ordered list of RawBlock instances.
    """
    lines = text.splitlines()
    blocks: list[RawBlock] = []
    block_index = 0

    inside_block = False
    current_lang: str | None = None
    current_lines: list[str] = []
    block_start_line = 0
    context_window: list[str] = []

    # ✅ NEW — track which fence width opened the current block
    # So ``` only closes ``` and ```` only closes ````
    current_fence: str = "```"

    for line_num, line in enumerate(lines):
        if not inside_block:
            open_match = _FENCE_OPEN.match(line)

            if open_match:
                lang_raw = open_match.group("lang").strip()
                current_lang = lang_raw if lang_raw else None
                current_lines = []
                block_start_line = line_num
                inside_block = True
                # ✅ Remember the fence width that opened this block
                current_fence = open_match.group("fence")

                logger.debug(
                    "Block #%d opened at line %d (lang=%r, fence=%r)",
                    block_index,
                    line_num + 1,
                    current_lang,
                    current_fence,
                )
            else:
                context_window.append(line)
                if len(context_window) > _CONTEXT_LINES:
                    context_window.pop(0)
        else:
            # ✅ NEW — use the matching close pattern for the fence width
            close_pattern = (
                _FENCE_4_CLOSE
                if current_fence == "````"
                else _FENCE_3_CLOSE
            )
            close_match = close_pattern.match(line)

            if close_match and line_num != block_start_line:
                content = "\n".join(current_lines)

                # Block size limit — skip oversized blocks
                block_bytes = len(content.encode("utf-8"))
                if block_bytes > _MAX_BLOCK_SIZE_BYTES:
                    logger.warning(
                        "Block #%d exceeds size limit "
                        "(%.1fMB) — skipping",
                        block_index,
                        block_bytes / 1024 / 1024,
                    )
                    block_index += 1
                    inside_block = False
                    current_lang = None
                    current_lines = []
                    context_window = []
                    current_fence = "```"
                    continue

                if _should_discard_block(
                    content=content,
                    language=current_lang,
                    context=context_window,
                    block_index=block_index,
                ):
                    logger.debug(
                        "Block #%d discarded "
                        "(tree/command/empty/output)",
                        block_index,
                    )
                    block_index += 1
                    inside_block = False
                    current_lang = None
                    current_lines = []
                    context_window = []
                    current_fence = "```"
                    continue

                block = RawBlock(
                    content=content,
                    language=current_lang,
                    context_before=list(context_window),
                    block_index=block_index,
                )
                blocks.append(block)
                logger.debug(
                    "Block #%d closed at line %d (%d content lines)",
                    block_index,
                    line_num + 1,
                    len(current_lines),
                )
                block_index += 1
                inside_block = False
                current_lang = None
                current_lines = []
                context_window = []
                current_fence = "```"
            else:
                current_lines.append(line)

    # Handle unclosed fence
    if inside_block and current_lines:
        content = "\n".join(current_lines)
        if not _should_discard_block(
            content=content,
            language=current_lang,
            context=context_window,
            block_index=block_index,
        ):
            logger.warning(
                "Unclosed code fence at end of document — "
                "saving block #%d anyway",
                block_index,
            )
            blocks.append(
                RawBlock(
                    content=content,
                    language=current_lang,
                    context_before=list(context_window),
                    block_index=block_index,
                )
            )

    return blocks


def _should_discard_block(
    content: str,
    language: str | None,
    context: list[str],
    block_index: int,
) -> bool:
    """
    Decide whether a code block should be discarded entirely.

    A block is discarded when it is clearly not a project file:
    1. Empty — no content at all.
    2. Directory tree — lines contain tree-drawing characters.
    3. Shell command example — all lines are commands,
       no filename in context.
    4. Terminal output display — emoji-heavy output examples.

    Args:
        content:     Raw block content (inside the fences).
        language:    Language hint from the opening fence.
        context:     Context lines before the block.
        block_index: Block number (for logging).

    Returns:
        True if the block should be thrown away.
    """
    stripped = content.strip()

    # 1. Empty block
    if not stripped:
        logger.debug("Block #%d: empty → discard", block_index)
        return True

    content_lines = [
        line for line in stripped.splitlines() if line.strip()
    ]

    # 2. Directory tree block
    if _is_directory_tree(content_lines):
        logger.debug("Block #%d: directory tree → discard", block_index)
        return True

    # 3. Shell command example block
    if _is_shell_example(content_lines, language, context):
        logger.debug("Block #%d: shell example → discard", block_index)
        return True

    # 4. ✅ NEW — terminal output display block
    if _is_output_display(content_lines, language):
        logger.debug(
            "Block #%d: terminal output display → discard",
            block_index,
        )
        return True

    return False


def _is_directory_tree(lines: list[str]) -> bool:
    """
    Return True if the block looks like a directory tree diagram.

    Criteria: more than 50% of non-empty lines contain tree-drawing
    characters (├ └ │ ─ etc).

    Args:
        lines: Non-empty content lines.

    Returns:
        True if this is a directory tree.
    """
    if not lines:
        return False

    tree_line_count = sum(
        1 for line in lines
        if _TREE_CHARS_RE.search(line)
    )

    ratio = tree_line_count / len(lines)
    return ratio > 0.5


def _is_shell_example(
    lines: list[str],
    language: str | None,
    context: list[str],
) -> bool:
    """
    Return True if this block is a shell command example.

    Criteria:
    - Language is bash/sh/shell/console or empty
    - ALL lines look like shell commands or comments
    - No filename label found in nearby context

    Args:
        lines:    Non-empty content lines.
        language: Language hint from the fence.
        context:  Context lines before the block.

    Returns:
        True if this looks like a run-it-like-this example.
    """
    shell_langs = {
        None, "", "bash", "sh", "shell",
        "console", "terminal", "cmd", "powershell", "ps1",
    }
    if language not in shell_langs:
        return False

    if not lines:
        return False

    all_commands = all(
        _SHELL_COMMAND_RE.match(line) for line in lines
    )
    if not all_commands:
        return False

    # If there is a nearby filename in context, keep the block
    for ctx_line in reversed(context[-8:]):
        ctx_stripped = ctx_line.strip()
        if (
            is_valid_filepath(ctx_stripped)
            or ctx_stripped.lower() in _SPECIAL_FILENAMES
        ):
            logger.debug(
                "Shell block has nearby filename %r — keeping",
                ctx_stripped,
            )
            return False

    return True


# def _is_output_display(
#     lines: list[str],
#     language: str | None,
# ) -> bool:
#     """
#     Return True if this block looks like terminal output being
#     displayed as an example rather than actual source code.

#     These are blocks that show WHAT THE TOOL OUTPUTS — things like
#     health scores, stat tables, emoji dashboards — not files to write.

#     Criteria:
#     - No language hint OR plain text language
#     - More than 40% of lines match output display patterns
#       (emojis, box drawing chars, score indicators, stat labels)

#     Args:
#         lines:    Non-empty content lines.
#         language: Language hint from the fence.

#     Returns:
#         True if this looks like a display output example.
#     """
#     # Only apply to unlabelled or plain text blocks
#     # Never discard python/js/bash/etc labelled blocks
#     display_langs = {None, "", "text", "txt", "plaintext", "plain"}
#     if language not in display_langs:
#         return False

#     if not lines:
#         return False

#     display_count = sum(
#         1 for line in lines
#         if _OUTPUT_DISPLAY_RE.search(line)
#     )

#     ratio = display_count / len(lines)
#     return ratio > 0.4
def _is_output_display(
    lines: list[str],
    language: str | None,
) -> bool:
    """
    Return True if this block looks like terminal output being
    displayed as an example rather than actual source code.

    These are blocks that show WHAT THE TOOL OUTPUTS — things like
    health scores, stat tables, emoji dashboards, roadmaps —
    not files to write to disk.

    Criteria:
    - No language hint OR plain text language
    - More than 30% of lines match output display patterns
      (emojis, box drawing chars, score indicators, stat labels,
       arrow roadmap lines, version indicators)

    Args:
        lines:    Non-empty content lines.
        language: Language hint from the fence.

    Returns:
        True if this looks like a display output example.
    """
    # Only apply to unlabelled or plain text blocks
    # Never discard python/js/bash/etc labelled blocks
    display_langs = {None, "", "text", "txt", "plaintext", "plain"}
    if language not in display_langs:
        return False

    if not lines:
        return False

    display_count = sum(
        1 for line in lines
        if _OUTPUT_DISPLAY_RE.search(line)
    )

    ratio = display_count / len(lines)

    # ✅ LOWERED from 0.4 to 0.3
    # The roadmap block has 4 lines all containing →
    # so ratio will be 1.0 — well above 0.3
    return ratio > 0.3
