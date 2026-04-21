#!/usr/bin/env python3
"""CLI for working with mdownreview markdown review sidecar files (.review.yaml).

Reads both .review.yaml (preferred) and .review.json (legacy) sidecar files.
All writes use MRSF v1.0 envelope and YAML output.

Subcommands:
  open     — find, install, and launch the mdownreview desktop app
  read     — show review comments from sidecar files
  cleanup  — delete fully-resolved sidecar files
"""

import argparse
import datetime
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import yaml


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def find_review_files(root: str) -> list[str]:
    """Recursively find all *.review.yaml and *.review.json files under *root*.

    YAML takes priority: if both extensions exist for the same source file,
    only the .review.yaml path is returned.
    """
    yaml_set: set[str] = set()
    results: list[str] = []
    # First pass: collect YAML files
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.endswith(".review.yaml"):
                full = os.path.join(dirpath, fn)
                results.append(full)
                yaml_set.add(os.path.join(dirpath, fn[:-len(".review.yaml")]))
    # Second pass: collect JSON files only if no YAML counterpart
    for dirpath, _dirnames, filenames in os.walk(root):
        for fn in sorted(filenames):
            if fn.endswith(".review.json"):
                base_key = os.path.join(dirpath, fn[:-len(".review.json")])
                if base_key not in yaml_set:
                    results.append(os.path.join(dirpath, fn))
    results.sort()
    return results


def load_review(path: str) -> dict:
    """Load and return parsed data from a review sidecar file (YAML or JSON)."""
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith(".review.yaml"):
            return yaml.safe_load(f) or {}
        return json.load(f)


def save_review(path: str, data: dict) -> None:
    """Atomically write *data* as YAML to *path*.

    If *path* ends with ``.review.json``, it is rewritten to
    ``.review.yaml`` so all output uses MRSF v1.0 YAML format.
    Uses a temporary file in the same directory followed by ``os.replace``
    so the write is atomic on both Windows and POSIX.
    """
    if path.endswith(".review.json"):
        path = path[:-len(".review.json")] + ".review.yaml"
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def source_file_for(review_path: str) -> str:
    """Derive the source filename by stripping the review suffix."""
    base = os.path.basename(review_path)
    for suffix in (".review.yaml", ".review.json"):
        if base.endswith(suffix):
            return base[:-len(suffix)]
    return base


def iso_now() -> str:
    """Return the current UTC time as an ISO-8601 string with ``Z`` suffix."""
    return datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%dT%H:%M:%S.%f"
    )[:-3] + "Z"


# ---------------------------------------------------------------------------
# read
# ---------------------------------------------------------------------------

def cmd_read(args: argparse.Namespace) -> int:
    root = args.path or os.getcwd()
    show_all = args.all
    fmt = args.format

    files = find_review_files(root)
    output_entries: list[dict] = []

    for fpath in files:
        try:
            data = load_review(fpath)
        except (json.JSONDecodeError, yaml.YAMLError, OSError) as exc:
            print(f"warning: skipping {fpath}: {exc}", file=sys.stderr)
            continue

        comments = data.get("comments", [])
        if not show_all:
            comments = [c for c in comments if not c.get("resolved", False)]
        if not comments:
            continue

        rel = os.path.relpath(fpath, root)
        source = source_file_for(fpath)
        output_entries.append({
            "reviewFile": rel,
            "sourceFile": source,
            "comments": comments,
        })

    if fmt == "json":
        json.dump(output_entries, sys.stdout, indent=2, ensure_ascii=False)
        sys.stdout.write("\n")
    else:
        for entry in output_entries:
            n = len(entry["comments"])
            label = "comments" if show_all else "unresolved comments"
            print(f"\u2500\u2500 {entry['sourceFile']} ({n} {label}) \u2500\u2500")
            for c in entry["comments"]:
                line = c.get("line", "?")
                prefix = ""
                if c.get("type"):
                    prefix += f"[{c['type']}] "
                if c.get("severity"):
                    prefix += f"({c['severity']}) "
                print(f"  [{c['id']}] line {line}: {prefix}{c['text']}")

    return 0


# ---------------------------------------------------------------------------
# cleanup
# ---------------------------------------------------------------------------

def cmd_cleanup(args: argparse.Namespace) -> int:
    root = args.path or os.getcwd()
    dry_run = args.dry_run

    files = find_review_files(root)
    removed = 0

    for fpath in files:
        try:
            data = load_review(fpath)
        except (json.JSONDecodeError, yaml.YAMLError, OSError) as exc:
            print(f"warning: skipping {fpath}: {exc}", file=sys.stderr)
            continue

        comments = data.get("comments", [])
        if not comments:
            continue
        if all(c.get("resolved", False) for c in comments):
            rel = os.path.relpath(fpath, root)
            if dry_run:
                print(f"would delete: {rel}")
            else:
                os.remove(fpath)
                print(f"deleted: {rel}")
            removed += 1

    action = "would delete" if dry_run else "deleted"
    print(f"{removed} file(s) {action}")
    return 0


# ---------------------------------------------------------------------------
# open
# ---------------------------------------------------------------------------

# Well-known install locations per platform
_KNOWN_PATHS_WINDOWS = [
    os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "mdownreview", "mdownreview.exe",
    ),
]

_KNOWN_PATHS_MACOS = [
    "/Applications/mdownreview.app/Contents/MacOS/mdownreview",
    os.path.expanduser(
        "~/Applications/mdownreview.app/Contents/MacOS/mdownreview"
    ),
]

_PATH_NAMES = ["mdownreview", "mdown-review"]

_INSTALL_URL_BASE = "https://dryotta.github.io/mdownreview"


def find_app_binary() -> str | None:
    """Locate the mdownreview binary.

    Search order: well-known install paths, then PATH.
    Returns the absolute path or ``None``.
    """
    system = platform.system()

    known: list[str] = []
    if system == "Windows":
        known = _KNOWN_PATHS_WINDOWS
    elif system == "Darwin":
        known = _KNOWN_PATHS_MACOS

    for p in known:
        if p and os.path.isfile(p):
            return p

    for name in _PATH_NAMES:
        found = shutil.which(name)
        if found:
            return found

    return None


def install_app() -> str | None:
    """Download and install mdownreview using the official install scripts.

    Returns the binary path on success, or ``None`` on failure.
    """
    system = platform.system()
    try:
        if system == "Darwin":
            print("Installing mdownreview (macOS)…")
            subprocess.run(
                ["sh", "-c", f"curl -LsSf {_INSTALL_URL_BASE}/install.sh | sh"],
                check=True,
            )
        elif system == "Windows":
            print("Installing mdownreview (Windows)…")
            subprocess.run(
                [
                    "powershell", "-ExecutionPolicy", "ByPass", "-c",
                    f"irm {_INSTALL_URL_BASE}/install.ps1 | iex",
                ],
                check=True,
            )
        else:
            print(f"error: automatic install not supported on {system}", file=sys.stderr)
            return None
    except subprocess.CalledProcessError as exc:
        print(f"error: install failed: {exc}", file=sys.stderr)
        return None

    return find_app_binary()


def cmd_open(args: argparse.Namespace) -> int:
    folder = os.path.abspath(args.folder or os.getcwd())
    file_path = args.file
    binary = find_app_binary()

    if binary is None:
        print("mdownreview not found — attempting install…", file=sys.stderr)
        binary = install_app()

    if binary is None:
        print("error: mdownreview could not be installed", file=sys.stderr)
        print(
            f"Install manually:\n"
            f"  macOS:   curl -LsSf {_INSTALL_URL_BASE}/install.sh | sh\n"
            f"  Windows: powershell -ExecutionPolicy ByPass -c "
            f"\"irm {_INSTALL_URL_BASE}/install.ps1 | iex\"",
            file=sys.stderr,
        )
        return 1

    cmd = [binary, "--folder", folder]
    if file_path:
        cmd.extend(["--file", file_path])

    try:
        if platform.system() == "Windows":
            subprocess.Popen(
                cmd,
                creationflags=subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                | subprocess.CREATE_NEW_PROCESS_GROUP,  # type: ignore[attr-defined]
                close_fds=True,
            )
        else:
            subprocess.Popen(
                cmd,
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        print(f"error: failed to launch: {exc}", file=sys.stderr)
        return 1

    print(f"Launched mdownreview: {binary}")
    parts = [f"--folder {folder}"]
    if file_path:
        parts.append(f"--file {file_path}")
    print(f"Opening: {' '.join(parts)}")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdownreview",
        description="Work with mdownreview markdown review sidecar files (.review.yaml).",
    )
    sub = parser.add_subparsers(dest="command")

    # open
    p_open = sub.add_parser("open", help="Launch mdownreview desktop app")
    p_open.add_argument("--folder", default=None, help="Project folder to open (default: cwd)")
    p_open.add_argument("--file", default=None, help="Specific file to open")
    p_open.set_defaults(func=cmd_open)

    # read
    p_read = sub.add_parser("read", help="Show review comments")
    p_read.add_argument("path", nargs="?", default=None, help="Root directory (default: cwd)")
    p_read.add_argument("--format", choices=["json", "text"], default="text")
    p_read.add_argument("--all", action="store_true", help="Include resolved comments")
    p_read.set_defaults(func=cmd_read)

    # cleanup
    p_clean = sub.add_parser("cleanup", help="Delete fully-resolved sidecar files")
    p_clean.add_argument("path", nargs="?", default=None, help="Root directory (default: cwd)")
    p_clean.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    p_clean.set_defaults(func=cmd_cleanup)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
