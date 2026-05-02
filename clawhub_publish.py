#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Wrapper around the official ``clawhub`` CLI that auto-bumps the version.

Purpose
-------
The official CLI already handles packaging, ignore rules (``.clawhubignore``
and ``.gitignore``) and the upload itself. This wrapper only adds two things
we want automated:

1. **Auto version bump** - writes the new version into ``SKILL.md``
   frontmatter and ``juejin_skill/__init__.py``.
2. **Forward** the rest to the real ``clawhub publish`` so the actual upload
   path stays official.

The publishing script itself (``clawhub_publish.py``) and ``.clawhubignore``
are already listed in ``.clawhubignore`` so the official CLI will skip them
when building the artifact.

Usage
-----
    python clawhub_publish.py publish <skill_dir> --version=1.0.1 --slug=juejin-skills

Any extra flags (``--name``, ``--tags``, ``--changelog``, ``--fork-of``,
``--dry-run``) are forwarded to ``clawhub publish`` unchanged. Use
``--bump-only`` to update the version files without invoking the CLI.
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

VERSION_RE = re.compile(r"^\d+\.\d+\.\d+([.-][0-9A-Za-z]+)*$")


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _eprint(*args, **kwargs) -> None:
    print(*args, file=sys.stderr, **kwargs)


def _validate_version(version: str) -> None:
    if not VERSION_RE.match(version):
        raise ValueError(
            f"Invalid --version '{version}'. Expected semver like 1.0.1 or 1.2.3-beta."
        )


def _version_tuple(version: str) -> Tuple[int, ...]:
    nums: List[int] = []
    for part in re.split(r"[.-]", version):
        if part.isdigit():
            nums.append(int(part))
        else:
            break
    return tuple(nums)


# ---------------------------------------------------------------------------
# Version bumping
# ---------------------------------------------------------------------------


@dataclass
class BumpResult:
    file: Path
    old_version: Optional[str]
    new_version: str
    changed: bool


def _bump_skill_md(skill_dir: Path, new_version: str, dry_run: bool) -> BumpResult:
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        raise FileNotFoundError(f"SKILL.md not found under {skill_dir}")

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError("SKILL.md must start with a YAML frontmatter block ('---').")

    end = text.find("\n---", 3)
    if end == -1:
        raise ValueError("SKILL.md frontmatter is not terminated by '---'.")

    frontmatter = text[3:end]
    body = text[end:]

    version_line_re = re.compile(r"^version:\s*(.+)$", re.MULTILINE)
    match = version_line_re.search(frontmatter)
    old_version: Optional[str] = None
    if match:
        old_version = match.group(1).strip().strip('"').strip("'")
        new_frontmatter = version_line_re.sub(
            f"version: {new_version}", frontmatter, count=1
        )
    else:
        # Insert after the first line (typically `name:`) to keep it near the top.
        lines = frontmatter.splitlines()
        insert_at = 1 if lines else 0
        lines.insert(insert_at, f"version: {new_version}")
        new_frontmatter = "\n".join(lines)
        if not new_frontmatter.endswith("\n"):
            new_frontmatter += "\n"

    if old_version == new_version:
        return BumpResult(path, old_version, new_version, changed=False)

    new_text = f"---{new_frontmatter}{body}"
    if not dry_run:
        path.write_text(new_text, encoding="utf-8")
    return BumpResult(path, old_version, new_version, changed=True)


def _bump_python_init(
    skill_dir: Path, new_version: str, dry_run: bool
) -> Optional[BumpResult]:
    """Best-effort bump of ``__version__`` in a sibling Python package."""
    candidates: List[Path] = [skill_dir / "juejin_skill" / "__init__.py"]
    for sub in skill_dir.iterdir():
        if sub.is_dir() and (sub / "__init__.py").is_file():
            candidates.append(sub / "__init__.py")

    version_assign_re = re.compile(
        r"^(__version__\s*=\s*)([\"'])([^\"']+)\2\s*$", re.MULTILINE
    )

    seen: set = set()
    for path in candidates:
        if path in seen or not path.is_file():
            continue
        seen.add(path)
        text = path.read_text(encoding="utf-8")
        m = version_assign_re.search(text)
        if not m:
            continue
        old_version = m.group(3)
        if old_version == new_version:
            return BumpResult(path, old_version, new_version, changed=False)
        new_text = version_assign_re.sub(
            lambda mm: f"{mm.group(1)}{mm.group(2)}{new_version}{mm.group(2)}",
            text,
            count=1,
        )
        if not dry_run:
            path.write_text(new_text, encoding="utf-8")
        return BumpResult(path, old_version, new_version, changed=True)
    return None


# ---------------------------------------------------------------------------
# SKILL.md readers (for slug + current version)
# ---------------------------------------------------------------------------


def _read_skill_field(skill_dir: Path, field: str) -> Optional[str]:
    path = skill_dir / "SKILL.md"
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = re.search(rf"^{re.escape(field)}:\s*(.+)$", text, re.MULTILINE)
    return m.group(1).strip().strip('"').strip("'") if m else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_args(argv: List[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="clawhub_publish",
        description=(
            "Bump the skill version and run the official `clawhub publish` command."
        ),
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser(
        "publish",
        help="Bump version files and invoke `clawhub publish` on <skill_dir>.",
    )
    p.add_argument("skill_dir", type=Path, help="Path to the skill project root.")
    p.add_argument(
        "--version", required=True, help="New semantic version, e.g. 1.0.1"
    )
    p.add_argument(
        "--slug",
        default=None,
        help="Skill slug (defaults to the `name` field from SKILL.md).",
    )
    # Optional pass-through arguments understood by the official CLI.
    p.add_argument("--name", default=None, help="Display name (forwarded).")
    p.add_argument("--tags", default=None, help="Comma-separated tags (forwarded).")
    p.add_argument(
        "--changelog", default=None, help="Changelog text (forwarded)."
    )
    p.add_argument(
        "--fork-of", default=None, help="Mark as a fork of an existing skill."
    )

    # Wrapper-specific switches.
    p.add_argument(
        "--force",
        action="store_true",
        help="Allow re-using the same version or downgrading.",
    )
    p.add_argument(
        "--bump-only",
        action="store_true",
        help="Only update version files; do not invoke `clawhub publish`.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview version changes without writing files or calling the CLI.",
    )
    p.add_argument(
        "--clawhub-bin",
        default=os.environ.get("CLAWHUB_BIN", "clawhub"),
        help="Path to the clawhub executable (default: `clawhub` from PATH).",
    )
    return parser.parse_args(argv)


def cmd_publish(args: argparse.Namespace) -> int:
    skill_dir: Path = args.skill_dir.expanduser().resolve()
    if not skill_dir.is_dir():
        _eprint(f"[clawhub] skill_dir does not exist: {skill_dir}")
        return 2

    _validate_version(args.version)

    slug = args.slug or _read_skill_field(skill_dir, "name")
    if not slug:
        _eprint(
            "[clawhub] --slug was not provided and SKILL.md has no `name:` field."
        )
        return 2

    current = _read_skill_field(skill_dir, "version")
    if current and not args.force:
        if _version_tuple(args.version) <= _version_tuple(current):
            _eprint(
                f"[clawhub] New version {args.version} is not greater than current "
                f"{current}. Pass --force to override."
            )
            return 2

    # 1) Bump versions
    results: List[BumpResult] = [
        _bump_skill_md(skill_dir, args.version, args.dry_run)
    ]
    init_result = _bump_python_init(skill_dir, args.version, args.dry_run)
    if init_result is not None:
        results.append(init_result)

    print("[clawhub] Version bump:")
    for r in results:
        status = (
            "DRY-RUN" if args.dry_run else ("updated" if r.changed else "unchanged")
        )
        old = r.old_version or "<none>"
        print(
            f"  - {r.file.relative_to(skill_dir)}: {old} -> {r.new_version} [{status}]"
        )

    if args.bump_only:
        print("[clawhub] --bump-only set; skipping `clawhub publish`.")
        return 0

    # 2) Invoke the official CLI (it handles .clawhubignore / .gitignore itself)
    clawhub_bin = args.clawhub_bin
    if shutil.which(clawhub_bin) is None and not Path(clawhub_bin).is_file():
        _eprint(
            f"[clawhub] '{clawhub_bin}' not found on PATH. Install via "
            "`npm i -g clawhub` or set --clawhub-bin / $CLAWHUB_BIN."
        )
        return 127

    cmd: List[str] = [clawhub_bin, "publish", str(skill_dir),
                      "--slug", slug,
                      "--version", args.version]
    if args.name:
        cmd += ["--name", args.name]
    if args.tags:
        cmd += ["--tags", args.tags]
    if args.changelog:
        cmd += ["--changelog", args.changelog]
    if args.fork_of:
        cmd += ["--fork-of", args.fork_of]

    pretty = " ".join(cmd)
    if args.dry_run:
        print(f"[clawhub] DRY-RUN would execute: {pretty}")
        return 0

    print(f"[clawhub] Running: {pretty}")
    try:
        completed = subprocess.run(cmd, check=False)
    except FileNotFoundError:
        _eprint(f"[clawhub] Failed to execute '{clawhub_bin}'.")
        return 127
    return completed.returncode


def main(argv: Optional[List[str]] = None) -> int:
    args = _parse_args(argv if argv is not None else sys.argv[1:])
    if args.command == "publish":
        return cmd_publish(args)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
