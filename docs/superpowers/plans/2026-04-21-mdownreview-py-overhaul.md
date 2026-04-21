# mdownreview.py Overhaul Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rewrite `mdownreview.py` to remove the PyYAML dependency, enforce strict MRSF v1.0 compliance, fix Windows app discovery, and replace the auto-installer with a download URL.

**Architecture:** All changes are confined to `skills/mdownreview.py` and `skills/test_mdownreview.py`. A pure-Python YAML reader/writer (`_yaml_loads`/`_yaml_dumps`) replaces `import yaml`. MRSF validation is added to `load_review`; envelope injection is added to `save_review`. Windows known paths gain the Tauri default install location. `install_app` is deleted; `cmd_open` points to the download page on failure.

**Tech Stack:** Python 3.11+, stdlib only (`re`, `json`, `os`, `sys`, `tempfile`, `subprocess`, `shutil`, `platform`, `datetime`, `argparse`). Tests: `unittest`, `unittest.mock`.

---

## File Map

| File | Change |
|------|--------|
| `skills/mdownreview.py` | Remove `import yaml`; add `import re`; add YAML module section; update `load_review`, `save_review`, `_KNOWN_PATHS_WINDOWS`, `cmd_open`; delete `install_app` |
| `skills/test_mdownreview.py` | Update `make_review`/`make_comment` helpers to MRSF format; update `write_review` to support YAML; add YAML unit tests; update `open` tests to remove `install_app` references |

---

## Task 1: Pure-Python YAML module

**Files:**
- Modify: `skills/mdownreview.py` — add `_yaml_loads` and `_yaml_dumps`, remove `import yaml`, add `import re`
- Modify: `skills/test_mdownreview.py` — add `TestYAML` class

- [ ] **Step 1.1: Write failing YAML tests**

Add this class to `skills/test_mdownreview.py` after the imports, before `TempDirMixin`:

```python
class TestYAML(unittest.TestCase):

    def test_load_minimal_mapping(self):
        src = "mrsf_version: '1.0'\ndocument: foo.md\ncomments: []\n"
        data = mdownreview._yaml_loads(src)
        self.assertEqual(data["mrsf_version"], "1.0")
        self.assertEqual(data["document"], "foo.md")
        self.assertEqual(data["comments"], [])

    def test_load_sequence_of_mappings(self):
        src = (
            "mrsf_version: '1.0'\n"
            "document: foo.md\n"
            "comments:\n"
            "  - id: abc\n"
            "    author: Alice (alice)\n"
            "    timestamp: '2026-01-01T00:00:00Z'\n"
            "    text: Fix this.\n"
            "    resolved: false\n"
            "    line: 5\n"
        )
        data = mdownreview._yaml_loads(src)
        c = data["comments"][0]
        self.assertEqual(c["id"], "abc")
        self.assertEqual(c["author"], "Alice (alice)")
        self.assertIs(c["resolved"], False)
        self.assertEqual(c["line"], 5)

    def test_load_scalar_types(self):
        src = (
            "a: true\n"
            "b: false\n"
            "c: null\n"
            "d: 42\n"
            "e: plain string\n"
            "f: 'single quoted'\n"
            'g: "double quoted"\n'
        )
        d = mdownreview._yaml_loads(src)
        self.assertIs(d["a"], True)
        self.assertIs(d["b"], False)
        self.assertIsNone(d["c"])
        self.assertEqual(d["d"], 42)
        self.assertEqual(d["e"], "plain string")
        self.assertEqual(d["f"], "single quoted")
        self.assertEqual(d["g"], "double quoted")

    def test_load_double_quoted_escapes(self):
        src = 'text: "line1\\nline2\\ttab"\n'
        d = mdownreview._yaml_loads(src)
        self.assertEqual(d["text"], "line1\nline2\ttab")

    def test_load_single_quoted_escape(self):
        src = "text: 'it''s a quote'\n"
        d = mdownreview._yaml_loads(src)
        self.assertEqual(d["text"], "it's a quote")

    def test_load_block_literal(self):
        src = "text: |\n  line one\n  line two\n"
        d = mdownreview._yaml_loads(src)
        self.assertEqual(d["text"], "line one\nline two\n")

    def test_load_block_literal_strip(self):
        src = "text: |-\n  hello\n"
        d = mdownreview._yaml_loads(src)
        self.assertEqual(d["text"], "hello")

    def test_load_ignores_comments(self):
        src = "# top comment\nkey: value # inline\n"
        d = mdownreview._yaml_loads(src)
        self.assertEqual(d["key"], "value # inline")

    def test_load_reply_to_field(self):
        src = (
            "mrsf_version: '1.0'\n"
            "document: foo.md\n"
            "comments:\n"
            "  - id: aaa\n"
            "    author: A (a)\n"
            "    timestamp: '2026-01-01T00:00:00Z'\n"
            "    text: parent\n"
            "    resolved: false\n"
            "  - id: bbb\n"
            "    author: B (b)\n"
            "    timestamp: '2026-01-01T00:01:00Z'\n"
            "    text: reply\n"
            "    resolved: false\n"
            "    reply_to: aaa\n"
        )
        d = mdownreview._yaml_loads(src)
        self.assertEqual(d["comments"][1]["reply_to"], "aaa")

    def test_roundtrip(self):
        original = {
            "mrsf_version": "1.0",
            "document": "docs/arch.md",
            "comments": [
                {
                    "id": "c1",
                    "author": "Tester (test)",
                    "timestamp": "2026-01-01T00:00:00.000Z",
                    "text": "Fix this.",
                    "resolved": False,
                    "line": 10,
                    "type": "issue",
                    "severity": "high",
                }
            ],
        }
        dumped = mdownreview._yaml_dumps(original)
        reloaded = mdownreview._yaml_loads(dumped)
        self.assertEqual(reloaded["mrsf_version"], "1.0")
        self.assertEqual(reloaded["document"], "docs/arch.md")
        c = reloaded["comments"][0]
        self.assertEqual(c["id"], "c1")
        self.assertIs(c["resolved"], False)
        self.assertEqual(c["line"], 10)

    def test_dump_quotes_bool_like_strings(self):
        dumped = mdownreview._yaml_dumps({"key": "true"})
        self.assertIn("'true'", dumped)

    def test_dump_quotes_int_like_strings(self):
        dumped = mdownreview._yaml_dumps({"key": "123"})
        self.assertIn("'123'", dumped)

    def test_dump_quotes_version_float(self):
        dumped = mdownreview._yaml_dumps({"mrsf_version": "1.0"})
        self.assertIn("'1.0'", dumped)

    def test_dump_empty_comments(self):
        dumped = mdownreview._yaml_dumps({"mrsf_version": "1.0", "document": "f.md", "comments": []})
        self.assertIn("comments: []", dumped)
```

- [ ] **Step 1.2: Run tests to confirm failure**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py::TestYAML -v
```

Expected: multiple failures — `AttributeError: module 'mdownreview' has no attribute '_yaml_loads'`

- [ ] **Step 1.3: Implement the YAML module in `skills/mdownreview.py`**

Replace the `import yaml` line with `import re`, then replace the entire `# Helpers` section's top (up to and including `find_review_files`) with the following YAML module block. Insert it between the stdlib imports and the `find_review_files` function:

**Change import block** — replace:
```python
import yaml
```
with:
```python
import re
```

**Add YAML module** — insert after the imports, before `find_review_files`:

```python
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
    'e': '\x1b', 'N': '\x85', '_': '\xa0', 'L': ' ', 'P': ' ',
}


def _yaml_unescape_dq(s: str) -> str:
    out, i = [], 0
    while i < len(s):
        if s[i] == '\\' and i + 1 < len(s):
            c = s[i + 1]
            if c in _YAML_DQ_ESC:
                out.append(_YAML_DQ_ESC[c]); i += 2
            elif c == 'x' and i + 3 < len(s):
                out.append(chr(int(s[i+2:i+4], 16))); i += 4
            elif c == 'u' and i + 5 < len(s):
                out.append(chr(int(s[i+2:i+6], 16))); i += 6
            elif c == 'U' and i + 9 < len(s):
                out.append(chr(int(s[i+2:i+10], 16))); i += 10
            else:
                out.append(s[i]); i += 1
        else:
            out.append(s[i]); i += 1
    return ''.join(out)


def _yaml_loads(text: str) -> object:
    """Parse YAML into Python objects. Handles the full MRSF v1.0 subset."""
    lines = text.splitlines()
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
                if pos[0] < len(lines) and indent_of(lines[pos[0]]) > map_ind:
                    nind = indent_of(lines[pos[0]])
                    ns = lines[pos[0]].lstrip()
                    result[key] = (
                        parse_sequence(nind) if (ns.startswith('- ') or ns == '-')
                        else parse_mapping(nind)
                    )
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
        if "'" not in s and '\n' not in s:
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
    return str(v)


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
```

- [ ] **Step 1.4: Run YAML tests to confirm they pass**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py::TestYAML -v
```

Expected: all 14 tests PASS.

- [ ] **Step 1.5: Run the full test suite to confirm no regressions**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py -v
```

Expected: all existing tests still PASS (they use `json.load`/`json.dump` directly via `write_review`, unaffected by YAML addition). The new `TestYAML` tests pass.

- [ ] **Step 1.6: Commit**

```bash
git add skills/mdownreview.py skills/test_mdownreview.py
git commit -m "feat: replace PyYAML with pure-Python YAML subset for MRSF"
```

---

## Task 2: MRSF v1.0 compliance in `load_review` and `save_review`

**Files:**
- Modify: `skills/mdownreview.py` — `load_review` validates envelope; `save_review` uses `_yaml_dumps`, injects envelope
- Modify: `skills/test_mdownreview.py` — update `make_review`, `make_comment`, `write_review`; update all test cases to use MRSF format; add `TestMRSFCompliance`

- [ ] **Step 2.1: Update test helpers to MRSF format**

In `skills/test_mdownreview.py`, replace `make_review`, `make_comment`, `TempDirMixin.write_review`, and `TempDirMixin.read_review`:

```python
def make_review(comments, document="test.md"):
    return {
        "mrsf_version": "1.0",
        "document": document,
        "comments": comments,
    }


def make_comment(id_, text="Fix this", line=10, resolved=False, reply_to=None):
    c = {
        "id": id_,
        "author": "Test User (test)",
        "timestamp": "2026-01-01T00:00:00.000Z",
        "text": text,
        "resolved": resolved,
        "line": line,
    }
    if reply_to is not None:
        c["reply_to"] = reply_to
    return c
```

In `TempDirMixin`, replace `write_review` and `read_review`:

```python
def write_review(self, relpath, data):
    full = os.path.join(self.tmpdir, relpath)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "w", encoding="utf-8") as f:
        if relpath.endswith(".yaml"):
            f.write(mdownreview._yaml_dumps(data))
        else:
            json.dump(data, f)
    return full

def read_review(self, path):
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith(".yaml"):
            return mdownreview._yaml_loads(f.read()) or {}
        return json.load(f)
```

- [ ] **Step 2.2: Update all existing test cases to use `.review.yaml` paths**

In every call to `self.write_review(...)` throughout `TestReadText`, `TestReadJson`, and `TestCleanup`, change all `.review.json` file paths to `.review.yaml`. For example:

```python
# Before
self.write_review("app.tsx.review.json", make_review([...]))
# After
self.write_review("app.tsx.review.yaml", make_review([...]))
```

Full list of changes (apply to all occurrences):
- `"app.tsx.review.json"` → `"app.tsx.review.yaml"`
- `"b.md.review.json"` → `"b.md.review.yaml"`
- `"a.md.review.json"` → `"a.md.review.yaml"`
- `"c.md.review.json"` → `"c.md.review.yaml"`
- `os.path.join("sub", "deep", "x.md.review.json")` → `os.path.join("sub", "deep", "x.md.review.yaml")`
- `os.path.join("sub", "x.md.review.json")` → `os.path.join("sub", "x.md.review.yaml")`

Also update the assertion in `test_review_file_relative_path` that checks `data[0]["sourceFile"]` — it should still pass since `source_file_for` strips `.review.yaml` just like `.review.json`.

- [ ] **Step 2.3: Write failing MRSF compliance tests**

Add this class to `skills/test_mdownreview.py` after `TestYAML`:

```python
class TestMRSFCompliance(TempDirMixin, unittest.TestCase):

    def test_load_review_warns_on_missing_version(self):
        path = self.write_review("a.md.review.yaml", {"document": "a.md", "comments": []})
        with self.assertWarns(None):  # no exception
            pass
        old_stderr = sys.stderr
        sys.stderr = buf = StringIO()
        data = mdownreview.load_review(path)
        sys.stderr = old_stderr
        self.assertIn("mrsf_version", buf.getvalue())

    def test_load_review_warns_on_unsupported_version(self):
        path = self.write_review(
            "a.md.review.yaml",
            {"mrsf_version": "2.0", "document": "a.md", "comments": []},
        )
        old_stderr = sys.stderr
        sys.stderr = buf = StringIO()
        mdownreview.load_review(path)
        sys.stderr = old_stderr
        self.assertIn("unsupported", buf.getvalue())

    def test_load_review_no_warning_on_valid_version(self):
        path = self.write_review(
            "a.md.review.yaml",
            {"mrsf_version": "1.0", "document": "a.md", "comments": []},
        )
        old_stderr = sys.stderr
        sys.stderr = buf = StringIO()
        mdownreview.load_review(path)
        sys.stderr = old_stderr
        self.assertEqual(buf.getvalue(), "")

    def test_save_review_injects_mrsf_version(self):
        path = os.path.join(self.tmpdir, "a.md.review.yaml")
        mdownreview.save_review(path, {"document": "a.md", "comments": []})
        data = self.read_review(path)
        self.assertEqual(data.get("mrsf_version"), "1.0")

    def test_save_review_injects_document_from_path(self):
        path = os.path.join(self.tmpdir, "myfile.md.review.yaml")
        mdownreview.save_review(path, {"mrsf_version": "1.0", "comments": []})
        data = self.read_review(path)
        self.assertEqual(data.get("document"), "myfile.md")

    def test_save_review_preserves_existing_document(self):
        path = os.path.join(self.tmpdir, "a.md.review.yaml")
        mdownreview.save_review(path, {"mrsf_version": "1.0", "document": "docs/a.md", "comments": []})
        data = self.read_review(path)
        self.assertEqual(data["document"], "docs/a.md")

    def test_save_review_rewrites_json_path_to_yaml(self):
        json_path = os.path.join(self.tmpdir, "a.md.review.json")
        yaml_path = os.path.join(self.tmpdir, "a.md.review.yaml")
        mdownreview.save_review(json_path, {"mrsf_version": "1.0", "document": "a.md", "comments": []})
        self.assertTrue(os.path.exists(yaml_path))
        self.assertFalse(os.path.exists(json_path))

    def test_save_review_output_is_valid_yaml(self):
        path = os.path.join(self.tmpdir, "a.md.review.yaml")
        mdownreview.save_review(path, {
            "mrsf_version": "1.0",
            "document": "a.md",
            "comments": [make_comment("c1")],
        })
        data = self.read_review(path)
        self.assertEqual(len(data["comments"]), 1)
        self.assertEqual(data["comments"][0]["id"], "c1")
```

- [ ] **Step 2.4: Run failing tests**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py::TestMRSFCompliance -v
```

Expected: failures — `load_review` has no version check, `save_review` still uses `yaml.dump`.

- [ ] **Step 2.5: Implement MRSF compliance in `load_review` and `save_review`**

In `skills/mdownreview.py`, replace the existing `load_review` function:

```python
def load_review(path: str) -> dict:
    """Load and return parsed data from a review sidecar file (YAML or JSON)."""
    with open(path, "r", encoding="utf-8") as f:
        if path.endswith(".review.yaml"):
            data = _yaml_loads(f.read()) or {}
        else:
            data = json.load(f)
    version = data.get("mrsf_version")
    if version is None:
        print(f"warning: {path}: missing mrsf_version (expected '1.0')", file=sys.stderr)
    elif not str(version).startswith("1."):
        print(f"warning: {path}: unsupported mrsf_version {version!r}", file=sys.stderr)
    return data
```

Replace the existing `save_review` function:

```python
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
```

- [ ] **Step 2.6: Run compliance tests**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py::TestMRSFCompliance -v
```

Expected: all 8 tests PASS.

- [ ] **Step 2.7: Run full test suite**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py -v
```

Expected: all tests PASS. The `TestRead*` and `TestCleanup` tests now exercise `.review.yaml` paths with MRSF-format data.

- [ ] **Step 2.8: Commit**

```bash
git add skills/mdownreview.py skills/test_mdownreview.py
git commit -m "feat: enforce MRSF v1.0 compliance in load_review and save_review"
```

---

## Task 3: Fix Windows app discovery paths

**Files:**
- Modify: `skills/mdownreview.py` — `_KNOWN_PATHS_WINDOWS`
- Modify: `skills/test_mdownreview.py` — add Windows path tests to `TestOpen`

- [ ] **Step 3.1: Write failing Windows path tests**

Add these three test methods inside `TestOpen` in `skills/test_mdownreview.py`:

```python
def test_known_paths_windows_contains_tauri_default(self):
    """_KNOWN_PATHS_WINDOWS must include the Tauri currentUser default path."""
    localappdata = os.environ.get("LOCALAPPDATA", "")
    expected = os.path.join(localappdata, "mdownreview", "mdownreview.exe")
    self.assertIn(expected, mdownreview._KNOWN_PATHS_WINDOWS)

def test_find_app_binary_windows_tauri_default(self):
    """find_app_binary returns Tauri default path when it exists (first in list)."""
    tauri = "C:\\FakeLocal\\mdownreview\\mdownreview.exe"
    programs = "C:\\FakeLocal\\Programs\\mdownreview\\mdownreview.exe"
    with unittest.mock.patch.object(mdownreview, "_KNOWN_PATHS_WINDOWS", [tauri, programs]):
        with unittest.mock.patch("platform.system", return_value="Windows"):
            with unittest.mock.patch("os.path.isfile", return_value=True):
                with unittest.mock.patch("shutil.which", return_value=None):
                    result = mdownreview.find_app_binary()
    self.assertEqual(result, tauri)

def test_find_app_binary_windows_programs_fallback(self):
    """find_app_binary falls back to Programs path when Tauri default missing."""
    tauri = "C:\\FakeLocal\\mdownreview\\mdownreview.exe"
    programs = "C:\\FakeLocal\\Programs\\mdownreview\\mdownreview.exe"
    with unittest.mock.patch.object(mdownreview, "_KNOWN_PATHS_WINDOWS", [tauri, programs]):
        with unittest.mock.patch("platform.system", return_value="Windows"):
            with unittest.mock.patch("os.path.isfile", side_effect=lambda p: p == programs):
                with unittest.mock.patch("shutil.which", return_value=None):
                    result = mdownreview.find_app_binary()
    self.assertEqual(result, programs)
```

- [ ] **Step 3.2: Run failing tests**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py::TestOpen::test_known_paths_windows_contains_tauri_default test_mdownreview.py::TestOpen::test_find_app_binary_windows_tauri_default test_mdownreview.py::TestOpen::test_find_app_binary_windows_programs_fallback -v
```

Expected: `test_known_paths_windows_contains_tauri_default` FAILS (path not in list yet); the other two PASS (they patch the list directly so they're structure tests).

- [ ] **Step 3.3: Update `_KNOWN_PATHS_WINDOWS`**

In `skills/mdownreview.py`, replace:

```python
_KNOWN_PATHS_WINDOWS = [
    os.path.join(
        os.environ.get("LOCALAPPDATA", ""),
        "Programs", "mdownreview", "mdownreview.exe",
    ),
]
```

with:

```python
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
```

- [ ] **Step 3.4: Run Windows path tests**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py::TestOpen -v
```

Expected: all `TestOpen` tests PASS.

- [ ] **Step 3.5: Commit**

```bash
git add skills/mdownreview.py skills/test_mdownreview.py
git commit -m "fix: add Tauri default install path to Windows app discovery"
```

---

## Task 4: Replace auto-installer with download link

**Files:**
- Modify: `skills/mdownreview.py` — delete `install_app`, update `cmd_open`
- Modify: `skills/test_mdownreview.py` — replace two `open` tests that reference `install_app`

- [ ] **Step 4.1: Update open tests to remove `install_app` references**

In `skills/test_mdownreview.py`, replace `test_open_not_found_install_fails`:

```python
def test_open_not_found_prints_url(self):
    """cmd_open exits 1 and prints download URL when binary not found."""
    with unittest.mock.patch.object(mdownreview, "find_app_binary", return_value=None):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = StringIO()
        sys.stderr = buf_err = StringIO()
        rc = mdownreview.main(["open"])
        sys.stdout, sys.stderr = old_stdout, old_stderr
    self.assertEqual(rc, 1)
    self.assertIn("https://dryotta.github.io/mdownreview/", buf_err.getvalue())
```

Replace `test_open_auto_installs_when_not_found` with:

```python
def test_open_not_found_no_install_attempt(self):
    """cmd_open never tries to install — just prints URL and exits 1."""
    with unittest.mock.patch.object(mdownreview, "find_app_binary", return_value=None):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = StringIO()
        sys.stderr = buf_err = StringIO()
        rc = mdownreview.main(["open"])
        sys.stdout, sys.stderr = old_stdout, old_stderr
    self.assertEqual(rc, 1)
    # URL is printed, no subprocess calls were made
    self.assertIn("dryotta.github.io", buf_err.getvalue())
```

- [ ] **Step 4.2: Run failing tests**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py::TestOpen::test_open_not_found_prints_url test_mdownreview.py::TestOpen::test_open_not_found_no_install_attempt -v
```

Expected: FAIL — `test_open_not_found_prints_url` fails because current code calls `install_app` and prints `"could not be installed"` not the URL.

- [ ] **Step 4.3: Delete `install_app` and update `cmd_open`**

In `skills/mdownreview.py`, delete the entire `install_app` function (from its `def install_app() -> str | None:` through the closing `return find_app_binary()`).

Replace the beginning of `cmd_open` (the binary discovery and missing-binary block) with:

```python
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
```

- [ ] **Step 4.4: Run full test suite**

```
cd Q:/src2/mdownreview-skills/skills && python -m pytest test_mdownreview.py -v
```

Expected: all tests PASS. Confirm `install_app` is gone with:

```
cd Q:/src2/mdownreview-skills/skills && python -c "import mdownreview; print(hasattr(mdownreview, 'install_app'))"
```

Expected output: `False`

- [ ] **Step 4.5: Verify `import yaml` is gone**

```
cd Q:/src2/mdownreview-skills/skills && python -c "import mdownreview; print('ok')"
```

Expected: `ok` — no `ModuleNotFoundError` even without PyYAML installed. Also verify:

```
grep "import yaml" Q:/src2/mdownreview-skills/skills/mdownreview.py
```

Expected: no output.

- [ ] **Step 4.6: Commit**

```bash
git add skills/mdownreview.py skills/test_mdownreview.py
git commit -m "fix: remove auto-installer, point to download page when app not found"
```
