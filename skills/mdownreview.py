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
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


# ---------------------------------------------------------------------------
# Pure-Python YAML subset for MRSF v1.0 sidecar files
# ---------------------------------------------------------------------------

_YAML_KEY_RE = re.compile(r'^([A-Za-z_][A-Za-z0-9_]*):\s*(.*)')
_YAML_NEEDS_QUOTE = re.compile(
    r"^['\"{}\[\]#&*!|>%@`,]"   # special first char
    r"|^-[^ \t\n]"               # dash not followed by space/newline
    r"|: "                       # colon-space (mapping separator)
    r"| #"                       # space-hash (comment)
    r"|\s$"                      # trailing whitespace
    r"|[\x00-\x1f]"              # control chars (includes \n, \t, \r)
)
_YAML_BOOL_NULL_INT = re.compile(r'^(true|false|null|~|-?\d+)$', re.I)
_YAML_FLOAT_LIKE = re.compile(r'^-?\d*\.\d+([eE][+-]?\d+)?$')

_YAML_DQ_ESC: dict[str, str] = {
    'n': '\n', 't': '\t', 'r': '\r', '"': '"', '\\': '\\',
    'b': '\b', 'f': '\f', '0': '\0', 'a': '\a', 'v': '\v',
    'e': '\x1b', 'N': '\x85', '_': '\xa0', 'L': ' ', 'P': ' ',
}


def _yaml_unescape_dq(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            c = s[i + 1]
            if c in _YAML_DQ_ESC:
                out.append(_YAML_DQ_ESC[c])
                i += 2
            elif c == 'x' and i + 3 < len(s):
                out.append(chr(int(s[i+2:i+4], 16)))
                i += 4
            elif c == 'u' and i + 5 < len(s):
                out.append(chr(int(s[i+2:i+6], 16)))
                i += 6
            elif c == 'U' and i + 9 < len(s):
                out.append(chr(int(s[i+2:i+10], 16)))
                i += 10
            else:
                out.append(s[i])
                i += 1
        else:
            out.append(s[i])
            i += 1
    return ''.join(out)


def _yaml_loads(text: str) -> object:
    """Parse YAML into Python objects. Handles the full MRSF v1.0 subset."""
    # Use split('\n') rather than splitlines() so that a literal \r inside a
    # YAML scalar value does not split the line and corrupt the parse.
    lines = text.split('\n')
    pos = [0]

    def skip_empty() -> None:
        while pos[0] < len(lines):
            s = lines[pos[0]].lstrip()
            if s and not s.startswith('#'):
                return
            pos[0] += 1

    def indent_of(line: str) -> int:
        return len(line) - len(line.lstrip(' '))

    def parse_scalar(s: str) -> object:
        s = s.strip()
        if not s or s in ('null', '~'):
            return None
        if s == 'true':
            return True
        if s == 'false':
            return False
        if s == '[]':
            return []
        if s == '{}':
            return {}
        try:
            return int(s)
        except ValueError:
            pass
        if len(s) >= 2 and s[0] == "'" and s[-1] == "'":
            return s[1:-1].replace("''", "'")
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            return _yaml_unescape_dq(s[1:-1])
        return s

    def parse_block_scalar(header: str, base_ind: int) -> str:
        style = '|' if '|' in header else '>'
        rest = header.strip().lstrip('|>').strip()
        chomp = 'clip'
        if rest.startswith('+'):
            chomp = 'keep'
        elif rest.startswith('-'):
            chomp = 'strip'

        block_lines: list[str] = []
        block_ind: int | None = None
        while pos[0] < len(lines):
            raw = lines[pos[0]].rstrip()
            if raw.strip() == '':
                block_lines.append('')
                pos[0] += 1
                continue
            ind = indent_of(raw)
            if block_ind is None:
                if ind <= base_ind:
                    break
                block_ind = ind
            if ind < block_ind:
                break
            block_lines.append(raw[block_ind:])
            pos[0] += 1

        if not block_lines:
            return '' if chomp == 'strip' else '\n'

        if style == '|':
            content = '\n'.join(block_lines)
        else:
            parts: list[str] = []
            for bl in block_lines:
                if bl == '':
                    parts.append('\n\n')
                elif parts and not parts[-1].endswith('\n'):
                    parts[-1] += ' ' + bl
                else:
                    parts.append(bl)
            content = ''.join(parts)

        if chomp == 'strip':
            return content.rstrip('\n')
        if chomp == 'keep':
            return content + '\n'
        return content.rstrip('\n') + '\n'

    def parse_mapping(map_ind: int) -> dict:
        result: dict = {}
        while True:
            skip_empty()
            if pos[0] >= len(lines):
                break
            line = lines[pos[0]]
            if indent_of(line) != map_ind:
                break
            m = _YAML_KEY_RE.match(line.lstrip())
            if not m:
                break
            key, val_s = m.group(1), m.group(2).rstrip()
            pos[0] += 1

            if val_s == '':
                skip_empty()
                if pos[0] < len(lines):
                    nind = indent_of(lines[pos[0]])
                    ns = lines[pos[0]].lstrip()
                    is_seq = ns.startswith('- ') or ns == '-'
                    # Block sequences may sit at the same indent as the mapping key
                    # (valid YAML). Nested mappings must be strictly deeper.
                    if nind > map_ind or (nind == map_ind and is_seq):
                        result[key] = (
                            parse_sequence(nind) if is_seq
                            else parse_mapping(nind)
                        )
                    else:
                        result[key] = None
                else:
                    result[key] = None
            elif val_s[0] in ('|', '>'):
                result[key] = parse_block_scalar(val_s, map_ind)
            else:
                result[key] = parse_scalar(val_s)
        return result

    def next_block_value(item_ind: int) -> object:
        skip_empty()
        if pos[0] >= len(lines) or indent_of(lines[pos[0]]) < item_ind:
            return None
        nind = indent_of(lines[pos[0]])
        ns = lines[pos[0]].lstrip()
        return (parse_sequence(nind) if (ns.startswith('- ') or ns == '-')
                else parse_mapping(nind))

    def parse_sequence(seq_ind: int) -> list:
        result: list = []
        while True:
            skip_empty()
            if pos[0] >= len(lines):
                break
            line = lines[pos[0]]
            if indent_of(line) != seq_ind:
                break
            s = line.lstrip()
            if not (s.startswith('- ') or s == '-'):
                break
            pos[0] += 1
            item_ind = seq_ind + 2
            rest = (s[2:] if s.startswith('- ') else '').rstrip()

            if rest == '':
                result.append(next_block_value(item_ind))
            elif rest[0] in ('|', '>'):
                result.append(parse_block_scalar(rest, item_ind))
            else:
                mm = _YAML_KEY_RE.match(rest)
                if mm:
                    fk, fv_s = mm.group(1), mm.group(2).rstrip()
                    if fv_s == '':
                        fv = next_block_value(item_ind)
                    elif fv_s[0] in ('|', '>'):
                        fv = parse_block_scalar(fv_s, item_ind)
                    else:
                        fv = parse_scalar(fv_s)
                    item: dict = {fk: fv}
                    item.update(parse_mapping(item_ind))
                    result.append(item)
                else:
                    result.append(parse_scalar(rest))
        return result

    skip_empty()
    if pos[0] >= len(lines):
        return None
    s = lines[pos[0]].lstrip()
    ind = indent_of(lines[pos[0]])
    return parse_sequence(ind) if (s.startswith('- ') or s == '-') else parse_mapping(ind)


def _yaml_quote_str(s: str) -> str:
    """Return the YAML scalar representation of string s."""
    if not s:
        return "''"
    if _YAML_BOOL_NULL_INT.match(s) or _YAML_FLOAT_LIKE.match(s) or _YAML_NEEDS_QUOTE.search(s):
        if "'" not in s and '\n' not in s and '\r' not in s:
            return f"'{s}'"
        escaped = (s.replace('\\', '\\\\').replace('"', '\\"')
                   .replace('\n', '\\n').replace('\r', '\\r').replace('\t', '\\t'))
        return f'"{escaped}"'
    return s


def _yaml_scalar_repr(v: object) -> str:
    if v is None:
        return 'null'
    if isinstance(v, bool):
        return 'true' if v else 'false'
    if isinstance(v, int):
        return str(v)
    if isinstance(v, str):
        return _yaml_quote_str(v)
    if isinstance(v, list) and not v:
        return '[]'
    if isinstance(v, dict) and not v:
        return '{}'
    raise TypeError(f"unsupported YAML scalar type: {type(v).__name__!r}")


def _yaml_emit_lines(obj: object, indent: int) -> list[str]:
    pad = '  ' * indent
    if isinstance(obj, dict):
        lines: list[str] = []
        for k, v in obj.items():
            if isinstance(v, dict) and v:
                lines.append(f'{pad}{k}:')
                lines.extend(_yaml_emit_lines(v, indent + 1))
            elif isinstance(v, list) and v:
                lines.append(f'{pad}{k}:')
                lines.extend(_yaml_emit_lines(v, indent + 1))
            else:
                lines.append(f'{pad}{k}: {_yaml_scalar_repr(v)}')
        return lines
    if isinstance(obj, list):
        lines = []
        for item in obj:
            if isinstance(item, dict) and item:
                keys = list(item.keys())
                fk, fv = keys[0], item[keys[0]]
                if isinstance(fv, (dict, list)) and fv:
                    lines.append(f'{pad}- {fk}:')
                    lines.extend(_yaml_emit_lines(fv, indent + 2))
                else:
                    lines.append(f'{pad}- {fk}: {_yaml_scalar_repr(fv)}')
                subpad = '  ' * (indent + 1)
                for k in keys[1:]:
                    v = item[k]
                    if isinstance(v, (dict, list)) and v:
                        lines.append(f'{subpad}{k}:')
                        lines.extend(_yaml_emit_lines(v, indent + 2))
                    else:
                        lines.append(f'{subpad}{k}: {_yaml_scalar_repr(v)}')
            else:
                lines.append(f'{pad}- {_yaml_scalar_repr(item)}')
        return lines
    return [f'{pad}{_yaml_scalar_repr(obj)}']


def _yaml_dumps(obj: object) -> str:
    """Serialize Python objects to a YAML string."""
    return '\n'.join(_yaml_emit_lines(obj, 0)) + '\n'


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
    with open(path, "r", encoding="utf-8", newline='') as f:
        if path.endswith(".review.yaml"):
            # Use newline='' to suppress universal-newlines translation so that a
            # lone \r inside a YAML scalar (e.g. selected_text: '## Skills\r')
            # is preserved rather than being silently converted to \n, which
            # would split a single-quoted value across two lines and corrupt parsing.
            data = _yaml_loads(f.read().replace('\r\n', '\n')) or {}
        else:
            data = json.load(f)
    version = data.get("mrsf_version")
    if version is None:
        print(f"warning: {path}: missing mrsf_version (expected '1.0')", file=sys.stderr)
    elif not str(version).startswith("1."):
        print(f"warning: {path}: unsupported mrsf_version {version!r}", file=sys.stderr)
    return data


def save_review(path: str, data: dict) -> None:
    """Atomically write *data* as YAML to *path*, injecting MRSF envelope fields if absent.

    Rewrites .review.json paths to .review.yaml.
    """
    if path.endswith(".review.json"):
        path = path[:-len(".review.json")] + ".review.yaml"
    if "mrsf_version" not in data:
        data = {"mrsf_version": "1.0", **data}
    if "document" not in data:
        base = os.path.basename(path)
        if base.endswith(".review.yaml"):
            data = {**data, "document": base[:-len(".review.yaml")]}
    directory = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(_yaml_dumps(data))
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
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            print(f"warning: skipping {fpath}: {exc}", file=sys.stderr)
            continue

        comments = list(data.get("comments") or [])
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
            print(f"-- {entry['sourceFile']} ({n} {label}) --")
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
        except (json.JSONDecodeError, ValueError, OSError) as exc:
            print(f"warning: skipping {fpath}: {exc}", file=sys.stderr)
            continue

        comments = list(data.get("comments") or [])
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
# resolve / respond
# ---------------------------------------------------------------------------

def _add_response(data: dict, comment_id: str, response_text: str | None,
                  resolve: bool) -> bool:
    """Mutate *data* in place. Returns True if the comment was found."""
    for c in data.get("comments", []):
        if str(c.get("id")) == comment_id:
            if resolve:
                c["resolved"] = True
            if response_text:
                responses = list(c.get("responses") or [])
                responses.append({
                    "author": "agent",
                    "text": response_text,
                    "timestamp": iso_now(),
                })
                c["responses"] = responses
            return True
    return False


def cmd_resolve(args: argparse.Namespace) -> int:
    review_path = args.review_file
    comment_id = str(args.comment_id)

    try:
        data = load_review(review_path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"error: cannot read {review_path}: {exc}", file=sys.stderr)
        return 1

    if not _add_response(data, comment_id, args.response, resolve=True):
        print(f"error: comment {comment_id!r} not found in {review_path}", file=sys.stderr)
        return 1

    save_review(review_path, data)
    print(f"Resolved comment {comment_id} in {os.path.basename(review_path)}")
    return 0


def cmd_respond(args: argparse.Namespace) -> int:
    review_path = args.review_file
    comment_id = str(args.comment_id)

    try:
        data = load_review(review_path)
    except (json.JSONDecodeError, ValueError, OSError) as exc:
        print(f"error: cannot read {review_path}: {exc}", file=sys.stderr)
        return 1

    if not _add_response(data, comment_id, args.response, resolve=False):
        print(f"error: comment {comment_id!r} not found in {review_path}", file=sys.stderr)
        return 1

    save_review(review_path, data)
    print(f"Added response to comment {comment_id} in {os.path.basename(review_path)}")
    return 0


# ---------------------------------------------------------------------------
# open
# ---------------------------------------------------------------------------

# Well-known install locations per platform
_KNOWN_PATHS_WINDOWS = [
    os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "mdownreview", "mdownreview.exe",
    ),
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


def cmd_open(args: argparse.Namespace) -> int:
    folder = os.path.abspath(args.folder or os.getcwd())
    file_path = args.file
    binary = find_app_binary()

    if binary is None:
        print(
            f"mdownreview not found — download and install from: {_INSTALL_URL_BASE}/",
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

    # resolve
    p_resolve = sub.add_parser("resolve", help="Mark a comment as resolved")
    p_resolve.add_argument("review_file", help="Path to the .review.yaml file")
    p_resolve.add_argument("comment_id", help="Comment ID to resolve")
    p_resolve.add_argument("--response", default=None, help="Response message to record")
    p_resolve.set_defaults(func=cmd_resolve)

    # respond
    p_respond = sub.add_parser("respond", help="Add a response to a comment without resolving")
    p_respond.add_argument("review_file", help="Path to the .review.yaml file")
    p_respond.add_argument("comment_id", help="Comment ID to respond to")
    p_respond.add_argument("--response", required=True, help="Response message to record")
    p_respond.set_defaults(func=cmd_respond)

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
