"""
Stage 3 — Builder.

Takes a list of FileObjects and writes them to disk (or simulates
doing so in dry-run mode). Also handles zip output.

Security hardened against:
- Path traversal attacks (../../etc/passwd)
- Absolute path writes (/etc/passwd)
- Zip slip attacks
- Symlink following
"""

from __future__ import annotations

import logging
import tempfile
import zipfile
from pathlib import Path

from rich.console import Console
from rich.tree import Tree

from unprompted.models import BuildResult, FileObject

logger = logging.getLogger(__name__)
console = Console()


def _is_safe_path(base: Path, target: Path) -> bool:
    """
    Verify that target resolves inside base directory.

    Prevents path traversal attacks where a malicious input
    file contains paths like ../../etc/passwd.

    Args:
        base:   The intended root output directory.
        target: The resolved target path to write to.

    Returns:
        True only if target is strictly inside base.
    """
    try:
        resolved_base = base.resolve()
        resolved_target = target.resolve()
        resolved_target.relative_to(resolved_base)
        return True
    except ValueError:
        return False


def _sanitize_zip_path(path: str) -> str | None:
    """
    Sanitize a file path before adding it to a zip archive.

    Blocks:
    - Absolute paths (/etc/passwd)
    - Path traversal sequences (..)
    - Empty paths

    Args:
        path: The raw file path from FileObject.

    Returns:
        Sanitized path string, or None if it should be blocked.
    """
    normalized = path.replace("\\", "/")

    # Block absolute paths
    if normalized.startswith("/"):
        logger.error("Blocked absolute path in zip: %r", path)
        return None

    # Block traversal sequences
    parts = normalized.split("/")
    clean_parts = []
    for part in parts:
        if part in (".", ".."):
            logger.error(
                "Blocked path traversal in zip: %r", path
            )
            return None
        if part:
            clean_parts.append(part)

    if not clean_parts:
        return None

    return "/".join(clean_parts)


def build_project(
    files: list[FileObject],
    output_dir: Path,
    *,
    dry_run: bool = False,
    force: bool = False,
    verbose: bool = False,
    as_zip: bool = False,
) -> BuildResult:
    """
    Write all FileObjects to output_dir or produce a zip archive.

    Args:
        files:      Resolved FileObjects from the extractor stage.
        output_dir: Root directory for output.
        dry_run:    If True, print actions without touching filesystem.
        force:      If True, overwrite existing files.
        verbose:    If True, print per-file success messages.
        as_zip:     If True, create a project.zip instead of a folder.

    Returns:
        A BuildResult summarising what was created/skipped/errored.
    """
    result = BuildResult(dry_run=dry_run)

    if not files:
        logger.warning("No files to build.")
        return result

    if as_zip:
        return _build_zip(
            files,
            output_dir,
            dry_run=dry_run,
            force=force,
            verbose=verbose,
        )

    _print_tree_preview(files, output_dir)

    if dry_run:
        console.print(
            "\n[bold yellow]Dry run — no files were written.[/bold yellow]"
        )
        result.created = [f.path for f in files]
        return result

    for file_obj in files:
        _write_file(file_obj, output_dir, force=force, result=result)

    _print_summary(result)
    return result


def _write_file(
    file_obj: FileObject,
    base: Path,
    *,
    force: bool,
    result: BuildResult,
) -> None:
    """
    Write a single FileObject to disk safely.

    Security checks (in order):
    1. Path traversal — target must be inside base
    2. Symlink — refuse to write through symlinks
    3. Conflict — skip if exists and not --force

    Args:
        file_obj: The file to write.
        base:     The root output directory.
        force:    Whether to overwrite existing files.
        result:   BuildResult to update in place.
    """
    target = file_obj.resolved_path(base)

    # ✅ 1. PATH TRAVERSAL CHECK
    if not _is_safe_path(base, target):
        msg = (
            f"Blocked: '{file_obj.path}' resolves outside "
            f"output directory — possible path traversal attack"
        )
        logger.error(msg)
        console.print(
            f"  [red]BLOCKED[/red] {file_obj.path} "
            f"— outside output dir"
        )
        result.errors.append((file_obj.path, msg))
        return

    # ✅ 2. SYMLINK CHECK
    if target.exists() and target.is_symlink():
        msg = (
            f"Blocked: '{file_obj.path}' is a symlink — "
            f"refusing to write to avoid symlink attack"
        )
        logger.error(msg)
        console.print(
            f"  [red]BLOCKED[/red] {file_obj.path} "
            f"— symlink detected"
        )
        result.errors.append((file_obj.path, msg))
        return

    # ✅ 3. CONFLICT CHECK
    if target.exists() and not force:
        msg = (
            f"File already exists "
            f"(use --force to overwrite): {file_obj.path}"
        )
        logger.warning(msg)
        console.print(f"  [yellow]SKIP[/yellow]  {file_obj.path}")
        result.skipped.append(file_obj.path)
        return

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(file_obj.content, encoding="utf-8")
        logger.debug("Created: %s", target)
        console.print(f"  [green]CREATE[/green] {file_obj.path}")
        result.created.append(file_obj.path)

    except PermissionError as exc:
        msg = f"Permission denied: {target}"
        logger.error(msg)
        console.print(
            f"  [red]ERROR[/red]  {file_obj.path} — {exc}"
        )
        result.errors.append((file_obj.path, str(exc)))

    except OSError as exc:
        msg = f"OS error writing {target}: {exc}"
        logger.error(msg)
        console.print(
            f"  [red]ERROR[/red]  {file_obj.path} — {exc}"
        )
        result.errors.append((file_obj.path, str(exc)))


def _build_zip(
    files: list[FileObject],
    output_dir: Path,
    *,
    dry_run: bool,
    force: bool,
    verbose: bool,
) -> BuildResult:
    """
    Build the project inside a temp directory then zip it safely.

    Security: all paths are sanitized before adding to the archive
    to prevent zip slip attacks.

    Args:
        files:      Files to package.
        output_dir: Where to place project.zip.
        dry_run:    If True, simulate only.
        force:      If True, overwrite existing zip.
        verbose:    Verbose flag (passed through).

    Returns:
        BuildResult describing what happened.
    """
    result = BuildResult(dry_run=dry_run)
    zip_path = output_dir / "project.zip"

    if zip_path.exists() and not force:
        console.print(
            "[yellow]project.zip already exists "
            "— use --force to overwrite[/yellow]"
        )
        result.skipped.append("project.zip")
        return result

    _print_tree_preview(files, output_dir, label="project.zip")

    if dry_run:
        console.print(
            "\n[bold yellow]Dry run — "
            "project.zip was not written.[/bold yellow]"
        )
        result.created = [f.path for f in files]
        return result

    try:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)

            for file_obj in files:
                # ✅ SANITIZE path before writing into temp dir
                safe_path = _sanitize_zip_path(file_obj.path)
                if safe_path is None:
                    msg = (
                        f"Blocked unsafe zip path: {file_obj.path}"
                    )
                    logger.error(msg)
                    result.errors.append((file_obj.path, msg))
                    continue

                safe_file = FileObject(
                    path=safe_path,
                    content=file_obj.content,
                    language=file_obj.language,
                    source_block_index=file_obj.source_block_index,
                )
                _write_file(
                    safe_file, tmp_path, force=True, result=result
                )

            output_dir.mkdir(parents=True, exist_ok=True)
            with zipfile.ZipFile(
                zip_path, "w", zipfile.ZIP_DEFLATED
            ) as zf:
                for file_obj in files:
                    safe_path = _sanitize_zip_path(file_obj.path)
                    if safe_path is None:
                        continue
                    disk_path = tmp_path / safe_path
                    if disk_path.exists():
                        # ✅ arcname uses sanitized path only
                        zf.write(disk_path, arcname=safe_path)

        console.print(
            f"\n[bold green]✓ Created archive:[/bold green] "
            f"{zip_path}"
        )

    except OSError as exc:
        msg = f"Failed to create zip: {exc}"
        logger.error(msg)
        console.print(f"[red]ERROR[/red] {msg}")
        result.errors.append(("project.zip", str(exc)))

    _print_summary(result)
    return result


def _print_tree_preview(
    files: list[FileObject],
    output_dir: Path,
    label: str | None = None,
) -> None:
    """
    Print a Rich tree showing the files that will be created.

    Args:
        files:      Files to show in the tree.
        output_dir: Root directory (used as tree root label).
        label:      Override the root label.
    """
    root_label = label or str(output_dir)
    tree = Tree(
        f"[bold cyan]{root_label}[/bold cyan]",
        guide_style="dim",
    )

    dir_nodes: dict[str, Tree] = {}

    for file_obj in sorted(files, key=lambda f: f.path):
        parts = Path(file_obj.path).parts

        if len(parts) == 1:
            tree.add(f"[green]{parts[0]}[/green]")
        else:
            current_tree = tree
            for i, part in enumerate(parts[:-1]):
                key = "/".join(parts[: i + 1])
                if key not in dir_nodes:
                    node = current_tree.add(
                        f"[bold blue]{part}/[/bold blue]"
                    )
                    dir_nodes[key] = node
                current_tree = dir_nodes[key]
            current_tree.add(f"[green]{parts[-1]}[/green]")

    console.print("\n[bold]Project structure preview:[/bold]")
    console.print(tree)
    console.print()


def _print_summary(result: BuildResult) -> None:
    """
    Print a final summary of what was written, skipped, or errored.

    Args:
        result: The completed BuildResult.
    """
    console.print()
    console.print(
        f"[bold green]✓ Created:[/bold green]  "
        f"{len(result.created)} file(s)"
    )
    if result.skipped:
        console.print(
            f"[bold yellow]⚠ Skipped:[/bold yellow]  "
            f"{len(result.skipped)} file(s)"
        )
    if result.errors:
        console.print(
            f"[bold red]✗ Errors:[/bold red]   "
            f"{len(result.errors)} file(s)"
        )
        for path, msg in result.errors:
            console.print(f"    [red]{path}[/red]: {msg}")
