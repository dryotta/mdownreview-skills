#!/usr/bin/env python3
"""CLI for working with mDown reView sidecar files (MRSF v1.0, YAML format).

Reads both .review.yaml (preferred) and .review.json (legacy) sidecar files.
All writes use MRSF v1.0 envelope and YAML output.

Subcommands:
  read     — show review comments from sidecar files
  respond  — add a reply to a comment (flat reply_to threading)
  resolve  — mark comments as resolved
  cleanup  — delete fully-resolved sidecar files
  open     — find and launch the mDown reView desktop app
"""

import argparse
import datetime
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import uuid
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
# respond
# ---------------------------------------------------------------------------

def cmd_respond(args: argparse.Namespace) -> int:
    fpath = args.file
    comment_id = args.comment_id
    text = args.text

    if not os.path.isfile(fpath):
        print(f"error: file not found: {fpath}", file=sys.stderr)
        return 1

    data = load_review(fpath)
    comments = data.get("comments", [])

    # Verify parent comment exists
    if not any(c["id"] for c in comments if c.get("id") == comment_id):
        print(f"error: comment '{comment_id}' not found in {fpath}", file=sys.stderr)
        return 1

    # Create a new reply comment with reply_to
    reply = {
        "id": str(uuid.uuid4()),
        "author": "Agent (agent)",
        "timestamp": iso_now(),
        "text": text,
        "resolved": False,
        "reply_to": comment_id,
    }
    comments.append(reply)

    # Ensure MRSF envelope
    data["mrsf_version"] = "1.0"
    if "document" not in data:
        data["document"] = source_file_for(fpath)
    data["comments"] = comments

    save_review(fpath, data)
    print(f"Replied to {comment_id} (new comment {reply['id']})")
    return 0


# ---------------------------------------------------------------------------
# resolve
# ---------------------------------------------------------------------------

def cmd_resolve(args: argparse.Namespace) -> int:
    fpath = args.file
    resolve_all = args.all
    comment_ids: list[str] = args.comment_ids or []

    if not resolve_all and not comment_ids:
        print("error: provide comment IDs or --all", file=sys.stderr)
        return 1

    if not os.path.isfile(fpath):
        print(f"error: file not found: {fpath}", file=sys.stderr)
        return 1

    data = load_review(fpath)
    comments = data.get("comments", [])

    if resolve_all:
        count = 0
        for c in comments:
            if not c.get("resolved", False):
                c["resolved"] = True
                count += 1
        data["mrsf_version"] = "1.0"
        if "document" not in data:
            data["document"] = source_file_for(fpath)
        save_review(fpath, data)
        print(f"Resolved {count} comment(s)")
        return 0

    # Resolve specific IDs
    ids_found: set[str] = set()
    for c in comments:
        if c["id"] in comment_ids:
            c["resolved"] = True
            ids_found.add(c["id"])

    missing = set(comment_ids) - ids_found
    if missing:
        print(
            f"error: comment(s) not found: {', '.join(sorted(missing))}",
            file=sys.stderr,
        )
        return 1

    data["mrsf_version"] = "1.0"
    if "document" not in data:
        data["document"] = source_file_for(fpath)
    save_review(fpath, data)
    print(f"Resolved {len(ids_found)} comment(s)")
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
        "Programs", "mDown reView", "mDown reView.exe",
    ),
]

_KNOWN_PATHS_MACOS = [
    "/Applications/mDown reView.app/Contents/MacOS/mDown reView",
    os.path.expanduser(
        "~/Applications/mDown reView.app/Contents/MacOS/mDown reView"
    ),
]

_PATH_NAMES = ["mDown reView", "mdown-review"]


def find_app_binary() -> str | None:
    """Locate the mDown reView binary.

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


def cmd_open(args: argparse.Namespace) -> int:
    target = os.path.abspath(args.path or os.getcwd())
    binary = find_app_binary()

    if binary is None:
        searched = []
        system = platform.system()
        if system == "Windows":
            searched.extend(_KNOWN_PATHS_WINDOWS)
        elif system == "Darwin":
            searched.extend(_KNOWN_PATHS_MACOS)
        searched.extend(f"(PATH) {n}" for n in _PATH_NAMES)
        print("error: mDown reView not found", file=sys.stderr)
        print("Searched:", file=sys.stderr)
        for loc in searched:
            print(f"  - {loc}", file=sys.stderr)
        return 1

    try:
        if platform.system() == "Windows":
            # DETACHED_PROCESS so the app doesn't block the terminal
            subprocess.Popen(
                [binary, target],
                creationflags=subprocess.DETACHED_PROCESS  # type: ignore[attr-defined]
                | subprocess.CREATE_NEW_PROCESS_GROUP,  # type: ignore[attr-defined]
                close_fds=True,
            )
        else:
            subprocess.Popen(
                [binary, target],
                start_new_session=True,
                close_fds=True,
            )
    except OSError as exc:
        print(f"error: failed to launch: {exc}", file=sys.stderr)
        return 1

    print(f"Launched mDown reView: {binary}")
    print(f"Opening: {target}")
    return 0


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdownreview",
        description="Work with mDown reView sidecar files (MRSF v1.0, YAML format).",
    )
    sub = parser.add_subparsers(dest="command")

    # read
    p_read = sub.add_parser("read", help="Show review comments")
    p_read.add_argument("path", nargs="?", default=None, help="Root directory (default: cwd)")
    p_read.add_argument("--format", choices=["json", "text"], default="text")
    p_read.add_argument("--all", action="store_true", help="Include resolved comments")
    p_read.set_defaults(func=cmd_read)

    # respond
    p_resp = sub.add_parser("respond", help="Add a response to a comment")
    p_resp.add_argument("file", help="Path to .review.yaml or .review.json file")
    p_resp.add_argument("comment_id", help="Comment ID")
    p_resp.add_argument("text", help="Response text")
    p_resp.set_defaults(func=cmd_respond)

    # resolve
    p_res = sub.add_parser("resolve", help="Mark comments as resolved")
    p_res.add_argument("file", help="Path to .review.yaml or .review.json file")
    p_res.add_argument("comment_ids", nargs="*", help="Comment IDs to resolve")
    p_res.add_argument("--all", action="store_true", help="Resolve all comments")
    p_res.set_defaults(func=cmd_resolve)

    # cleanup
    p_clean = sub.add_parser("cleanup", help="Delete fully-resolved sidecar files")
    p_clean.add_argument("path", nargs="?", default=None, help="Root directory (default: cwd)")
    p_clean.add_argument("--dry-run", action="store_true", help="Preview without deleting")
    p_clean.set_defaults(func=cmd_cleanup)

    # open
    p_open = sub.add_parser("open", help="Launch mDown reView desktop app")
    p_open.add_argument("path", nargs="?", default=None, help="Folder to open (default: cwd)")
    p_open.set_defaults(func=cmd_open)

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
