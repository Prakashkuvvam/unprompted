"""
Utility helpers for unprompted.

Small, pure functions shared across parser, extractor, and builder.
No side effects, no I/O — easy to unit-test in isolation.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Language → file extension mapping
# ---------------------------------------------------------------------------

LANG_TO_EXT: dict[str, str] = {
    # Web
    "html": ".html",
    "htm": ".html",
    "css": ".css",
    "scss": ".scss",
    "sass": ".sass",
    "less": ".less",
    "javascript": ".js",
    "js": ".js",
    "jsx": ".jsx",
    "typescript": ".ts",
    "ts": ".ts",
    "tsx": ".tsx",
    "vue": ".vue",
    "svelte": ".svelte",
    # Backend
    "python": ".py",
    "py": ".py",
    "ruby": ".rb",
    "rb": ".rb",
    "php": ".php",
    "java": ".java",
    "kotlin": ".kt",
    "scala": ".scala",
    "go": ".go",
    "rust": ".rs",
    "c": ".c",
    "cpp": ".cpp",
    "c++": ".cpp",
    "csharp": ".cs",
    "c#": ".cs",
    "swift": ".swift",
    "dart": ".dart",
    # Data / Config
    "json": ".json",
    "yaml": ".yaml",
    "yml": ".yaml",
    "toml": ".toml",
    "ini": ".ini",
    "env": ".env",
    "xml": ".xml",
    "csv": ".csv",
    "sql": ".sql",
    # Shell / Scripts
    "bash": ".sh",
    "sh": ".sh",
    "zsh": ".sh",
    "fish": ".fish",
    "powershell": ".ps1",
    "ps1": ".ps1",
    "batch": ".bat",
    "bat": ".bat",
    # Docs / Markup
    "markdown": ".md",
    "md": ".md",
    "rst": ".rst",
    "txt": ".txt",
    "text": ".txt",
    # Docker / Infra
    "dockerfile": ".dockerfile",
    "docker": ".dockerfile",
    "nginx": ".conf",
    "terraform": ".tf",
    "tf": ".tf",
    "hcl": ".hcl",
}

# ---------------------------------------------------------------------------
# Known special filenames with no extension
# ---------------------------------------------------------------------------

_SPECIAL_FILENAMES: frozenset[str] = frozenset({
    "dockerfile",
    "makefile",
    "gemfile",
    "rakefile",
    "procfile",
    "vagrantfile",
    "jenkinsfile",
    "caddyfile",
    "brewfile",
    "fastfile",
    "podfile",
})

# ---------------------------------------------------------------------------
# Hard reject patterns
# ---------------------------------------------------------------------------

_TABLE_ROW_RE: re.Pattern[str] = re.compile(r"\|")
_LIST_ITEM_RE: re.Pattern[str] = re.compile(r"^[-*+]\s+\S")
_TREE_LINE_RE: re.Pattern[str] = re.compile(r"[├└─│]")

_PROSE_STARTERS: tuple[str, ...] = (
    "the ", "a ", "an ", "this ", "that ", "it ",
    "we ", "you ", "note", "now ", "here", "next ",
    "then ", "also ", "and ", "or ", "if ", "for ",
    "so ", "but ", "with ", "by ", "from ", "to ",
    "let", "run ", "use ", "add ", "check ", "make ",
    "install", "create", "first", "now,", "that's",
    "i'll", "i've", "we'll", "here's", "let's",
)

_VALID_PATH_CHARS_RE: re.Pattern[str] = re.compile(
    r"^[a-zA-Z0-9_\-./\\]+$"
)


def language_to_extension(language: str | None) -> str | None:
    """
    Convert a language hint string to a file extension.

    Args:
        language: Raw language string from a code fence (e.g. 'python', 'JS').

    Returns:
        A dotted extension like '.py', or None if not recognised.
    """
    if not language:
        return None
    normalised = language.strip().lower()
    return LANG_TO_EXT.get(normalised)


def is_valid_filepath(text: str) -> bool:
    """
    Strict heuristic: does this line look like a file path or filename?

    Runs a series of REJECT checks first (fast path), then
    ACCEPT checks. Designed to have very low false-positive rate.

    The backtick character is intentionally NOT in invalid_chars because
    backtick-wrapped paths like `app.py` are valid LLM output patterns.
    The extractor strips backticks before calling this function.

    Args:
        text: A single stripped line of text.

    Returns:
        True only if the line strongly resembles a filename or path.
    """
    stripped = text.strip()

    if not stripped:
        return False

    # ----------------------------------------------------------------
    # HARD REJECTS
    # ----------------------------------------------------------------

    if len(stripped) > 200:
        return False

    # Spaces are almost never valid in file paths
    if " " in stripped:
        return False

    # Markdown table rows
    if _TABLE_ROW_RE.search(stripped):
        return False

    # Tree drawing characters
    if _TREE_LINE_RE.search(stripped):
        return False

    # Markdown list items
    if _LIST_ITEM_RE.match(stripped):
        return False

    # Prose starters
    lower = stripped.lower()
    if any(lower.startswith(p) for p in _PROSE_STARTERS):
        return False

    # Trailing punctuation that prose uses but paths do not
    if stripped.endswith((".", ",", ":", "!", "?", ";")):
        return False

    # Characters that are invalid in file paths
    # NOTE: backtick (`) intentionally removed from this set —
    # backtick-wrapped paths are stripped before reaching here
    invalid_chars = set('<>:"*?()[]{}=+@#$%^&~!;,')
    if any(c in stripped for c in invalid_chars):
        return False

    # ----------------------------------------------------------------
    # ACCEPT CHECKS
    # ----------------------------------------------------------------

    # Known special filenames like Dockerfile, Makefile
    if stripped.lower() in _SPECIAL_FILENAMES:
        logger.debug("Identified as special filename: %r", stripped)
        return True

    # Must only contain valid path characters
    if not _VALID_PATH_CHARS_RE.match(stripped):
        return False

    # Must have a dot (extension) or slash (path separator)
    has_extension = (
        "." in stripped
        and not stripped.startswith(".")
        and not stripped.endswith(".")
    )
    has_separator = "/" in stripped or "\\" in stripped

    # Allow dotfiles like .env, .gitignore, .env.example
    is_dotfile = (
        stripped.startswith(".")
        and len(stripped) > 1
        and "." in stripped[1:]
        or stripped.startswith(".")
        and " " not in stripped
        and len(stripped) > 1
    )

    if not (has_extension or has_separator or is_dotfile):
        return False

    # Extension sanity check — must be short (1-13 chars)
    p = Path(stripped.split("/")[-1].split("\\")[-1])
    if p.suffix and len(p.suffix) > 13:
        return False

    logger.debug("Identified as filepath: %r", stripped)
    return True


def normalise_path(raw: str) -> str:
    """
    Clean and normalise a raw path string.

    Security hardened:
    - Blocks null bytes
    - Strips absolute Unix paths (/etc/passwd)
    - Strips Windows absolute paths (C:/Windows/)
    - Removes path traversal sequences (..)
    - Converts backslashes to forward slashes
    - Removes leading ./
    - Collapses double slashes

    Args:
        raw: The raw path string as scraped from the document.

    Returns:
        A clean, safe, normalised relative path string.

    Raises:
        ValueError: If the path contains a null byte.
    """
    path = raw.strip().strip("`").strip("'").strip('"')

    # Block null bytes
    if "\x00" in path:
        raise ValueError(f"Path contains null byte: {raw!r}")

    path = path.replace("\\", "/")

    # Block absolute Unix paths
    if path.startswith("/"):
        logger.warning("Stripped absolute path prefix from: %r", path)
        path = path.lstrip("/")

    # Block Windows absolute paths (C:/, D:/)
    if len(path) > 2 and path[1] == ":" and path[2] == "/":
        logger.warning("Stripped Windows drive prefix from: %r", path)
        path = path[3:]

    # Remove leading ./
    while path.startswith("./"):
        path = path[2:]

    # Remove path traversal sequences
    parts = path.split("/")
    safe_parts = [p for p in parts if p not in (".", "..") and p]
    path = "/".join(safe_parts)

    # Collapse double slashes
    while "//" in path:
        path = path.replace("//", "/")

    return path


def deduplicate_path(path: str, existing: set[str]) -> str:
    """
    If path already exists in existing, append _1, _2, ... until unique.

    Args:
        path:     The desired file path.
        existing: Set of already-claimed paths.

    Returns:
        A unique path string.
    """
    if path not in existing:
        return path

    base = Path(path)
    stem = base.stem
    suffix = base.suffix
    parent = str(base.parent)

    counter = 1
    while True:
        candidate_name = f"{stem}_{counter}{suffix}"
        candidate = (
            f"{parent}/{candidate_name}"
            if parent != "."
            else candidate_name
        )
        if candidate not in existing:
            logger.debug(
                "Deduplicated %r → %r (counter=%d)",
                path,
                candidate,
                counter,
            )
            return candidate
        counter += 1


def auto_filename(index: int, language: str | None) -> str:
    """
    Generate a fallback filename when none can be detected.

    Args:
        index:    The 1-based file counter.
        language: Optional language hint for choosing extension.

    Returns:
        A filename like 'file_1.py' or 'file_2.txt'.
    """
    ext = language_to_extension(language) or ".txt"
    return f"file_{index}{ext}"


def configure_logging(verbose: bool) -> None:
    """
    Set up the root logger based on CLI verbosity.

    Args:
        verbose: If True, enable DEBUG level; otherwise INFO.
    """
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="%(levelname)s | %(name)s | %(message)s",
        level=level,
    )
