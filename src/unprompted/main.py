"""
CLI entry point for unprompted.

Wires together parser → extractor → builder and exposes
the command-line interface via Click.
"""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from unprompted import __version__
from unprompted.builder import build_project
from unprompted.extractor import extract_files
from unprompted.parser import parse_file
from unprompted.utils import configure_logging

console = Console()
error_console = Console(stderr=True, style="bold red")


def _version_callback(ctx: click.Context, _param: click.Parameter, value: bool) -> None:
    """Print version and exit."""
    if value:
        console.print(f"unprompted v{__version__}")
        ctx.exit()


@click.command(
    name="unprompted",
    help=(
        "Convert raw LLM output into a fully structured project on disk.\n\n"
        "Parses INPUT_FILE for code blocks, detects filenames, and writes "
        "them to OUTPUT_DIR (or a zip archive with --zip)."
    ),
    context_settings={"help_option_names": ["-h", "--help"]},
)
@click.argument(
    "input_file",
    type=click.Path(exists=False, dir_okay=False, path_type=Path),
    metavar="INPUT_FILE",
)
@click.argument(
    "output_dir",
    type=click.Path(file_okay=False, path_type=Path),
    metavar="OUTPUT_DIR",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Preview the project structure without writing any files.",
)
@click.option(
    "--verbose", "-v",
    is_flag=True,
    default=False,
    help="Enable detailed debug logging.",
)
@click.option(
    "--force", "-f",
    is_flag=True,
    default=False,
    help="Overwrite existing files without prompting.",
)
@click.option(
    "--zip", "-z",
    "as_zip",
    is_flag=True,
    default=False,
    help="Package the output as project.zip instead of a folder.",
)
@click.option(
    "--version", "-V",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=_version_callback,
    help="Show version and exit.",
)
def cli(
    input_file: Path,
    output_dir: Path,
    dry_run: bool,
    verbose: bool,
    force: bool,
    as_zip: bool,
) -> None:
    """
    Main CLI command.

    Orchestrates the three-stage pipeline:
        1. parse_file    → RawBlocks
        2. extract_files → FileObjects
        3. build_project → Files on disk / zip
    """
    configure_logging(verbose)

    # -----------------------------------------------------------------------
    # Banner
    # -----------------------------------------------------------------------
    console.print(
        Panel.fit(
            f"[bold cyan]unprompted[/bold cyan] [dim]v{__version__}[/dim]\n"
            "LLM output → structured project",
            border_style="cyan",
        )
    )

    # -----------------------------------------------------------------------
    # Validate input file exists
    # -----------------------------------------------------------------------
    if not input_file.exists():
        error_console.print(f"Input file not found: {input_file}")
        sys.exit(1)

    console.print(f"[dim]Input:[/dim]  {input_file}")
    console.print(f"[dim]Output:[/dim] {output_dir}")
    if dry_run:
        console.print("[bold yellow]Mode: DRY RUN[/bold yellow]")
    if as_zip:
        console.print("[bold cyan]Output format: ZIP[/bold cyan]")
    console.print()

    # -----------------------------------------------------------------------
    # Stage 1 — Parse
    # -----------------------------------------------------------------------
    try:
        with console.status("[cyan]Parsing input file...[/cyan]"):
            parse_result = parse_file(input_file)
    except (FileNotFoundError, PermissionError, ValueError) as exc:
        error_console.print(f"Parse error: {exc}")
        sys.exit(1)

    if not parse_result.blocks:
        console.print(
            "[bold yellow]⚠  No code blocks found in input file.[/bold yellow]\n"
            "Make sure code is wrapped in triple backticks (```)."
        )
        sys.exit(0)

    console.print(
        f"[green]✓[/green] Found [bold]{len(parse_result.blocks)}[/bold] "
        f"code block(s)"
    )

    # -----------------------------------------------------------------------
    # Stage 2 — Extract
    # -----------------------------------------------------------------------
    with console.status("[cyan]Extracting files...[/cyan]"):
        extract_result = extract_files(parse_result.blocks)

    if not extract_result.files:
        console.print(
            "[bold yellow]⚠  No files could be extracted.[/bold yellow]"
        )
        sys.exit(0)

    console.print(
        f"[green]✓[/green] Resolved [bold]{len(extract_result.files)}[/bold] "
        f"file(s)"
    )
    if extract_result.skipped_blocks:
        console.print(
            f"[yellow]  {len(extract_result.skipped_blocks)} empty block(s) "
            f"skipped[/yellow]"
        )

    # -----------------------------------------------------------------------
    # Stage 3 — Build
    # -----------------------------------------------------------------------
    build_result = build_project(
        extract_result.files,
        output_dir,
        dry_run=dry_run,
        force=force,
        verbose=verbose,
        as_zip=as_zip,
    )

    # -----------------------------------------------------------------------
    # Exit with error code if anything went wrong
    # -----------------------------------------------------------------------
    if build_result.errors:
        sys.exit(1)
