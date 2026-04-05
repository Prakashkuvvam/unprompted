# Contributing to unprompted

First off — thank you for taking the time to contribute. 🎉

unprompted is a focused, single-purpose CLI tool and contributions that keep it sharp, reliable, and simple are especially valued. This document will walk you through everything you need to know.

---

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Ways to Contribute](#ways-to-contribute)
- [Getting Started](#getting-started)
- [Project Structure](#project-structure)
- [Development Workflow](#development-workflow)
- [Running Tests](#running-tests)
- [Code Style](#code-style)
- [Submitting a Pull Request](#submitting-a-pull-request)
- [Reporting Bugs](#reporting-bugs)
- [Suggesting Features](#suggesting-features)
- [Commit Message Convention](#commit-message-convention)
- [What Gets Accepted](#what-gets-accepted)

---

## Code of Conduct

Be respectful. This is a small open-source project maintained in spare time. Keep discussions technical and constructive. Issues or PRs that are rude or dismissive will be closed.

---

## Ways to Contribute

You don't have to write code to contribute meaningfully:

| Type | What it looks like |
|------|--------------------|
| 🐛 Bug report | Input file that produces wrong output |
| 💡 Feature suggestion | New filename pattern, flag idea, workflow improvement |
| 🔧 Bug fix | Fork, fix, test, PR |
| 🧪 Tests | New edge cases, better coverage for existing modules |
| 📖 Documentation | Fix typos, add examples, clarify confusing sections |
| 🔍 Code review | Review open PRs and leave thoughtful feedback |

---

## Getting Started

### Prerequisites

- Python 3.10 or higher
- [`uv`](https://github.com/astral-sh/uv) — strongly recommended for development

### Fork and clone

```bash
# 1. Fork on GitHub (top-right button on the repo page)

# 2. Clone your fork
git clone https://github.com/YOUR_USERNAME/unprompted
cd unprompted
```

### Install dependencies

```bash
# Install all dev dependencies
uv sync --group dev

# Verify the CLI works
uv run unprompted --help
```

### Run against the sample input

```bash
uv run unprompted sample_input.txt output/ --dry-run
```

If you see a file tree preview with no errors — you're set up correctly.

---

## Project Structure

Understanding where things live before you make changes:

```
unprompted/
├── src/
│   └── unprompted/
│       ├── __init__.py        # Package version
│       ├── main.py            # CLI entry point — Click commands and flags
│       ├── models.py          # Data structures: RawBlock, FileObject
│       ├── parser.py          # Stage 1: extract code blocks from raw text
│       ├── extractor.py       # Stage 2: map blocks to file paths
│       ├── builder.py         # Stage 3: write files to disk or zip
│       └── utils.py           # Pure helper functions (no side effects)
├── tests/
│   ├── test_utils.py          # Tests for utils.py
│   ├── test_parser.py         # Tests for parser.py
│   ├── test_extractor.py      # Tests for extractor.py
│   └── test_builder.py        # Tests for builder.py
├── sample_input.txt           # Realistic LLM output for manual testing
└── pyproject.toml
```

### The pipeline

```
input.txt → parser.py → extractor.py → builder.py → output/
             RawBlock    FileObject      files on disk
```

If you're fixing a filename detection bug → `extractor.py` + `test_extractor.py`.  
If you're fixing a code block parsing bug → `parser.py` + `test_parser.py`.  
If you're adding a new CLI flag → `main.py` + `builder.py`.

---

## Development Workflow

### Create a branch

```bash
# For a bug fix
git checkout -b fix/path-traversal-guard

# For a new feature
git checkout -b feat/stdin-support

# For documentation
git checkout -b docs/improve-readme-examples
```

Use short, lowercase, hyphenated names. Prefix with `fix/`, `feat/`, `docs/`, `test/`, or `chore/`.

### Make your changes

Keep changes focused. One PR = one concern. If you notice an unrelated bug while working on something else, open a separate PR for it.

### Check your work

```bash
# Run the full check suite before committing
uv run ruff check src/ --fix   # lint and auto-fix
uv run mypy src/               # type check
uv run pytest                  # run all 113 tests
```

All three must pass before opening a PR.

---

## Running Tests

```bash
# Run all tests
uv run pytest

# Verbose output
uv run pytest --verbose

# Run a single test file
uv run pytest tests/test_extractor.py -v

# Run a single test by name
uv run pytest tests/test_parser.py::test_handles_unclosed_fence -v

# With coverage report
uv run pytest --cov=src/unprompted --cov-report=term-missing
```

### Writing new tests

- Tests live in `tests/` and follow the pattern `test_<module>.py`
- Each test should be small and test exactly one behavior
- Use descriptive names: `test_detects_filename_from_bold_pattern`, not `test_bold`
- Tests should not touch the real filesystem — use `tmp_path` (pytest fixture) for any file I/O
- Every bug fix should come with a regression test

```python
# Good test structure
def test_detects_filename_from_markdown_heading(tmp_path):
    """Filename on a ### heading line is correctly resolved."""
    input_text = "### app.py\n```python\nprint('hello')\n```"
    blocks = parse(input_text)
    files = extract(blocks)
    assert files[0].path == "app.py"
    assert files[0].content == "print('hello')\n"
```

---

## Code Style

unprompted uses [Ruff](https://github.com/astral-sh/ruff) for linting and formatting, and [mypy](https://mypy-lang.org/) for type checking.

```bash
# Check for issues
uv run ruff check src/

# Auto-fix what can be auto-fixed
uv run ruff check src/ --fix

# Type check
uv run mypy src/
```

### Style principles

- **Type annotations are required** on all public functions
- **Docstrings** on all public functions — one-line is fine for simple helpers
- **No magic numbers** — use named constants
- **Pure functions in `utils.py`** — no side effects, no I/O
- **Keep functions small** — if a function is doing two things, split it
- **No `print()` in library code** — use `rich.console.Console` for CLI output

---

## Submitting a Pull Request

### Before opening the PR

- [ ] Tests pass (`uv run pytest`)
- [ ] Lint passes (`uv run ruff check src/`)
- [ ] Type check passes (`uv run mypy src/`)
- [ ] New functionality has tests
- [ ] Bug fixes include a regression test
- [ ] The branch is up to date with `main`

### PR title format

```
fix: guard against path traversal in extractor
feat: add stdin support via --clip flag
docs: add more examples for nested path detection
test: add edge cases for unclosed code fence handling
chore: update ruff to 0.5.0
```

### PR description template

```markdown
## What this PR does
<!-- One paragraph summary -->

## Why
<!-- The problem this solves, or the use case it enables -->

## How
<!-- Key implementation decisions -->

## Testing
<!-- How you verified the change works -->

## Related issues
<!-- Closes #123 -->
```

### Review process

- PRs are reviewed as time allows — usually within a few days
- Feedback will be specific and actionable
- Requests for changes are not rejections — they're part of the process
- Once approved, PRs are squash-merged to keep the history clean

---

## Reporting Bugs

Open a [GitHub Issue](https://github.com/prakashkuvvam/unprompted/issues/new) and include:

**Required**

- The exact command you ran
- A minimal input file (or snippet) that reproduces the bug
- The actual output vs the expected output
- Your OS and Python version (`python --version`)
- Your unprompted version (`unprompted --version`)

**Good bug report example**

```
**Command**
unprompted input.txt output/ --dry-run

**Input snippet**
### src/utils.py
```python
def helper():
    pass
```

**Expected**
File: src/utils.py resolved correctly

**Actual**
File name not detected — auto-named file_1.py instead

**Environment**
- OS: macOS 14.4
- Python: 3.11.6
- unprompted: 0.1.0
```

---

## Suggesting Features

Open a [GitHub Issue](https://github.com/prakashkuvvam/unprompted/issues/new) with the label `enhancement` and describe:

- **The problem** — what workflow pain does this solve?
- **The proposed solution** — what should unprompted do differently?
- **Alternatives considered** — what else did you think about?
- **Real-world example** — a concrete case where this would help

Features that fit unprompted's philosophy — local-first, no-agent, single-purpose, offline — are most likely to be accepted.

---

## Commit Message Convention

unprompted uses [Conventional Commits](https://www.conventionalcommits.org/):

```
<type>: <short imperative description>

[optional body]

[optional footer — e.g. Closes #42]
```

| Type | When to use |
|------|-------------|
| `feat` | New feature or behavior |
| `fix` | Bug fix |
| `docs` | Documentation only |
| `test` | Adding or updating tests |
| `refactor` | Code change that's neither a fix nor a feature |
| `chore` | Tooling, deps, CI, config |
| `perf` | Performance improvement |

**Good commit messages**

```
fix: guard against path traversal in extractor output paths
feat: add --clip flag to read from clipboard
test: add regression test for unclosed code fence
docs: add stdin piping example to README
```

**Bad commit messages**

```
fix stuff
update
wip
```

---

## What Gets Accepted

To set expectations clearly — PRs are most likely to be accepted when they:

✅ Fix a real, reproducible bug  
✅ Add a filename detection pattern seen in real LLM output  
✅ Improve test coverage for an edge case  
✅ Fix a typo or improve documentation clarity  
✅ Improve an error message  

PRs are less likely to be accepted if they:

⚠️ Add a large dependency  
⚠️ Significantly increase complexity for a niche use case  
⚠️ Change the public CLI interface without prior discussion  
⚠️ Add network features or cloud integrations — this tool is intentionally offline  

When in doubt — **open an issue first** and discuss before writing the code. It saves everyone time.

---

## Questions?

Open a [GitHub Discussion](https://github.com/prakashkuvvam/unprompted/discussions) or reach out via the email in the README.

---

<div align="center">
<sub>unprompted · MIT License · © 2025 Kuvam Sai Prakash</sub>
</div>