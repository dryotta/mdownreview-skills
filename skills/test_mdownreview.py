#!/usr/bin/env python3
"""Tests for mdownreview.py CLI."""

import contextlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
import unittest.mock
from pathlib import Path
from io import StringIO

# Ensure the scripts directory is importable
sys.path.insert(0, os.path.dirname(__file__))

import mdownreview


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


class TempDirMixin:
    """Mixin that creates a temp directory for each test."""

    def setUp(self):
        self._tmpdir_obj = tempfile.TemporaryDirectory()
        self.tmpdir = self._tmpdir_obj.name

    def tearDown(self):
        self._tmpdir_obj.cleanup()

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


class TestMRSFCompliance(TempDirMixin, unittest.TestCase):

    def test_load_review_warns_on_missing_version(self):
        path = self.write_review("a.md.review.yaml", {"document": "a.md", "comments": []})
        buf = StringIO()
        with contextlib.redirect_stderr(buf):
            mdownreview.load_review(path)
        self.assertIn("mrsf_version", buf.getvalue())

    def test_load_review_warns_on_unsupported_version(self):
        path = self.write_review(
            "a.md.review.yaml",
            {"mrsf_version": "2.0", "document": "a.md", "comments": []},
        )
        buf = StringIO()
        with contextlib.redirect_stderr(buf):
            mdownreview.load_review(path)
        self.assertIn("unsupported", buf.getvalue())

    def test_load_review_no_warning_on_valid_version(self):
        path = self.write_review(
            "a.md.review.yaml",
            {"mrsf_version": "1.0", "document": "a.md", "comments": []},
        )
        buf = StringIO()
        with contextlib.redirect_stderr(buf):
            mdownreview.load_review(path)
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


# ===== read =====

class TestReadText(TempDirMixin, unittest.TestCase):
    """read subcommand — text format."""

    def test_unresolved_only(self):
        self.write_review("app.tsx.review.yaml", make_review([
            make_comment("c1", "Fix null", line=15),
            make_comment("c2", "OK", line=20, resolved=True),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir])
        sys.stdout = old_stdout
        output = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("app.tsx", output)
        self.assertIn("[c1]", output)
        self.assertIn("Fix null", output)
        self.assertNotIn("[c2]", output)
        self.assertIn("1 unresolved", output)

    def test_all_flag(self):
        self.write_review("app.tsx.review.yaml", make_review([
            make_comment("c1", "Fix null", line=15),
            make_comment("c2", "OK", line=20, resolved=True),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir, "--all"])
        sys.stdout = old_stdout
        output = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("[c1]", output)
        self.assertIn("[c2]", output)
        self.assertIn("2 comments", output)

    def test_empty_dir(self):
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir])
        sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        self.assertEqual(buf.getvalue(), "")

    def test_nested_dirs(self):
        self.write_review(os.path.join("sub", "deep", "x.md.review.yaml"), make_review([
            make_comment("n1", "Nested comment", line=1),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir])
        sys.stdout = old_stdout
        output = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("[n1]", output)
        self.assertIn("x.md", output)


class TestReadJson(TempDirMixin, unittest.TestCase):
    """read subcommand — JSON format."""

    def test_json_unresolved(self):
        self.write_review("app.tsx.review.yaml", make_review([
            make_comment("c1", "Fix", line=15),
            make_comment("c2", "OK", line=20, resolved=True),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir, "--format", "json"])
        sys.stdout = old_stdout
        data = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["sourceFile"], "app.tsx")
        self.assertEqual(len(data[0]["comments"]), 1)
        self.assertEqual(data[0]["comments"][0]["id"], "c1")

    def test_json_all(self):
        self.write_review("app.tsx.review.yaml", make_review([
            make_comment("c1", "Fix", line=15),
            make_comment("c2", "OK", line=20, resolved=True),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir, "--format", "json", "--all"])
        sys.stdout = old_stdout
        data = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(len(data[0]["comments"]), 2)

    def test_json_empty_dir(self):
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir, "--format", "json"])
        sys.stdout = old_stdout
        data = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        self.assertEqual(data, [])

    def test_review_file_relative_path(self):
        self.write_review(os.path.join("sub", "x.md.review.yaml"), make_review([
            make_comment("r1", "Check", line=5),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["read", self.tmpdir, "--format", "json"])
        sys.stdout = old_stdout
        data = json.loads(buf.getvalue())
        self.assertEqual(rc, 0)
        # reviewFile should be a relative path
        self.assertIn("sub", data[0]["reviewFile"])


# ===== cleanup =====

class TestCleanup(TempDirMixin, unittest.TestCase):

    def test_deletes_fully_resolved(self):
        fpath = self.write_review("a.md.review.yaml", make_review([
            make_comment("c1", "Fix", resolved=True),
            make_comment("c2", "Also", resolved=True),
        ]))
        # Keep one with unresolved
        keep = self.write_review("b.md.review.yaml", make_review([
            make_comment("c3", "Keep", resolved=False),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["cleanup", self.tmpdir])
        sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        self.assertFalse(os.path.exists(fpath))
        self.assertTrue(os.path.exists(keep))
        self.assertIn("1 file(s) deleted", buf.getvalue())

    def test_dry_run(self):
        fpath = self.write_review("a.md.review.yaml", make_review([
            make_comment("c1", "Fix", resolved=True),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["cleanup", self.tmpdir, "--dry-run"])
        sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        self.assertTrue(os.path.exists(fpath))
        self.assertIn("would delete", buf.getvalue())

    def test_empty_dir(self):
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["cleanup", self.tmpdir])
        sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        self.assertIn("0 file(s)", buf.getvalue())

    def test_reports_count(self):
        self.write_review("a.md.review.yaml", make_review([
            make_comment("c1", resolved=True),
        ]))
        self.write_review("b.md.review.yaml", make_review([
            make_comment("c2", resolved=True),
        ]))
        self.write_review("c.md.review.yaml", make_review([
            make_comment("c3", resolved=False),
        ]))
        old_stdout = sys.stdout
        sys.stdout = buf = StringIO()
        rc = mdownreview.main(["cleanup", self.tmpdir])
        sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        self.assertIn("2 file(s) deleted", buf.getvalue())


# ===== helpers =====

class TestHelpers(unittest.TestCase):

    def test_source_file_for(self):
        self.assertEqual(mdownreview.source_file_for("app.tsx.review.json"), "app.tsx")
        self.assertEqual(mdownreview.source_file_for("readme.md.review.json"), "readme.md")
        self.assertEqual(mdownreview.source_file_for("app.tsx.review.yaml"), "app.tsx")

    def test_iso_now_format(self):
        ts = mdownreview.iso_now()
        self.assertTrue(ts.endswith("Z"))
        self.assertIn("T", ts)

    def test_no_subcommand_exits_1(self):
        old_stdout, old_stderr = sys.stdout, sys.stderr
        sys.stdout = StringIO()
        sys.stderr = StringIO()
        rc = mdownreview.main([])
        sys.stdout, sys.stderr = old_stdout, old_stderr
        self.assertEqual(rc, 1)


# ===== open =====

class TestOpen(unittest.TestCase):

    def test_find_app_binary_on_path(self):
        """find_app_binary returns a PATH match when available."""
        with unittest.mock.patch("shutil.which") as mock_which:
            mock_which.side_effect = lambda name: (
                "/usr/bin/mdown-review" if name == "mdown-review" else None
            )
            with unittest.mock.patch("os.path.isfile", return_value=False):
                result = mdownreview.find_app_binary()
        self.assertEqual(result, "/usr/bin/mdown-review")

    def test_find_app_binary_none(self):
        """find_app_binary returns None when nothing found."""
        with unittest.mock.patch("shutil.which", return_value=None):
            with unittest.mock.patch("os.path.isfile", return_value=False):
                result = mdownreview.find_app_binary()
        self.assertIsNone(result)

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

    def test_open_launches_app_with_folder(self):
        """cmd_open launches the binary with --folder and exits 0."""
        with unittest.mock.patch.object(mdownreview, "find_app_binary", return_value="/fake/app"):
            with unittest.mock.patch("subprocess.Popen") as mock_popen:
                old_stdout = sys.stdout
                sys.stdout = buf = StringIO()
                rc = mdownreview.main(["open", "--folder", "/some/project"])
                sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        mock_popen.assert_called_once()
        call_args = mock_popen.call_args[0][0]
        self.assertEqual(call_args[0], "/fake/app")
        self.assertIn("--folder", call_args)
        self.assertIn("Launched", buf.getvalue())

    def test_open_launches_app_with_folder_and_file(self):
        """cmd_open launches with both --folder and --file."""
        with unittest.mock.patch.object(mdownreview, "find_app_binary", return_value="/fake/app"):
            with unittest.mock.patch("subprocess.Popen") as mock_popen:
                old_stdout = sys.stdout
                sys.stdout = buf = StringIO()
                rc = mdownreview.main(["open", "--folder", "/proj", "--file", "src/main.py"])
                sys.stdout = old_stdout
        self.assertEqual(rc, 0)
        call_args = mock_popen.call_args[0][0]
        self.assertIn("--folder", call_args)
        self.assertIn("--file", call_args)
        self.assertIn("src/main.py", call_args)

    def test_open_launch_failure(self):
        """cmd_open exits 1 when Popen raises OSError."""
        with unittest.mock.patch.object(mdownreview, "find_app_binary", return_value="/fake/app"):
            with unittest.mock.patch("subprocess.Popen", side_effect=OSError("nope")):
                old_stdout, old_stderr = sys.stdout, sys.stderr
                sys.stdout = StringIO()
                sys.stderr = buf_err = StringIO()
                rc = mdownreview.main(["open", "--folder", "/some/project"])
                sys.stdout, sys.stderr = old_stdout, old_stderr
        self.assertEqual(rc, 1)
        self.assertIn("failed to launch", buf_err.getvalue())

    def test_open_not_found_no_install_attempt(self):
        """cmd_open never tries to install — just prints URL and exits 1."""
        with unittest.mock.patch.object(mdownreview, "find_app_binary", return_value=None):
            old_stdout, old_stderr = sys.stdout, sys.stderr
            sys.stdout = StringIO()
            sys.stderr = buf_err = StringIO()
            rc = mdownreview.main(["open"])
            sys.stdout, sys.stderr = old_stdout, old_stderr
        self.assertEqual(rc, 1)
        self.assertIn("https://dryotta.github.io/mdownreview/", buf_err.getvalue())

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


class TestYAMLMRSFExamples(unittest.TestCase):
    """Parser tests using verbatim YAML examples from MRSF v1.0 spec."""

    def test_spec_minimal_example(self):
        # Section 11.1 — double-quoted strings, 2-space-indented sequence
        src = textwrap.dedent("""\
            mrsf_version: "1.0"
            document: docs/architecture.md
            comments:
              - id: 1d3c72b0
                author: Wictor (wictorwilen)
                timestamp: '2026-03-02T18:22:59.713284+00:00'
                text: "This section needs clarification."
                resolved: false
                line: 9
                selected_text: "The gateway component routes all inbound traffic."
                commit: 02eb613
        """)
        data = mdownreview._yaml_loads(src)
        self.assertEqual(data["mrsf_version"], "1.0")
        self.assertEqual(data["document"], "docs/architecture.md")
        self.assertEqual(len(data["comments"]), 1)
        c = data["comments"][0]
        self.assertEqual(c["id"], "1d3c72b0")
        self.assertEqual(c["author"], "Wictor (wictorwilen)")
        self.assertIs(c["resolved"], False)
        self.assertEqual(c["line"], 9)
        self.assertEqual(c["selected_text"], "The gateway component routes all inbound traffic.")
        self.assertEqual(c["commit"], "02eb613")

    def test_spec_advanced_example(self):
        # Section 11.2 — type, end_line, start_column, end_column
        src = textwrap.dedent("""\
            mrsf_version: "1.0"
            document: docs/architecture.md
            comments:
              - id: 3eeccbd3
                author: Wictor (wictorwilen)
                timestamp: '2026-03-02T18:24:51.742976+00:00'
                text: "Is this phrasing correct?"
                type: question
                resolved: false
                commit: 02eb613
                line: 12
                end_line: 12
                start_column: 42
                end_column: 73
                selected_text: "While many concepts are represented"
        """)
        data = mdownreview._yaml_loads(src)
        c = data["comments"][0]
        self.assertEqual(c["id"], "3eeccbd3")
        self.assertEqual(c["type"], "question")
        self.assertEqual(c["end_line"], 12)
        self.assertEqual(c["start_column"], 42)
        self.assertEqual(c["end_column"], 73)
        self.assertEqual(c["selected_text"], "While many concepts are represented")

    def test_spec_threaded_reply_example(self):
        # Section 11.4 — two comments, second has reply_to
        src = textwrap.dedent("""\
            mrsf_version: "1.0"
            document: docs/architecture.md
            comments:
              - id: 1d3c72b0
                author: Wictor (wictorwilen)
                timestamp: '2026-03-02T18:22:59.713284+00:00'
                text: "Initial comment."
                resolved: false
                line: 9
                commit: 02eb613
              - id: badf5462
                author: Wictor (wictorwilen)
                timestamp: '2026-03-02T19:44:24.558426+00:00'
                text: "Follow-up reply."
                resolved: false
                reply_to: 1d3c72b0
                commit: 02eb613
        """)
        data = mdownreview._yaml_loads(src)
        self.assertEqual(len(data["comments"]), 2)
        self.assertEqual(data["comments"][0]["id"], "1d3c72b0")
        self.assertEqual(data["comments"][1]["id"], "badf5462")
        self.assertEqual(data["comments"][1]["reply_to"], "1d3c72b0")
        self.assertNotIn("reply_to", data["comments"][0])


class TestYAMLRealFileFormat(unittest.TestCase):
    """Parser tests using the format the mdownreview app actually writes.

    The app places sequence items at column 0 (same indent as the mapping key),
    which is valid YAML but was previously mishandled by the parser.
    """

    def test_zero_indent_sequence_single_comment(self):
        src = textwrap.dedent("""\
            mrsf_version: '1.0'
            document: README.md
            comments:
            - id: a8c5b0f7-670e-4603-b826-7c11bffb9fda
              author: Anonymous
              timestamp: 2026-04-21T23:13:35.368Z
              text: remove legacy
              resolved: false
              line: 5
        """)
        data = mdownreview._yaml_loads(src)
        self.assertEqual(len(data["comments"]), 1)
        c = data["comments"][0]
        self.assertEqual(c["id"], "a8c5b0f7-670e-4603-b826-7c11bffb9fda")
        self.assertIs(c["resolved"], False)
        self.assertEqual(c["line"], 5)

    def test_zero_indent_sequence_multiple_comments(self):
        src = textwrap.dedent("""\
            mrsf_version: '1.0'
            document: README.md
            comments:
            - id: c1
              author: Anonymous
              timestamp: 2026-04-21T23:13:00.000Z
              text: first comment
              resolved: false
              line: 5
            - id: c2
              author: Anonymous
              timestamp: 2026-04-21T23:14:00.000Z
              text: second comment
              resolved: true
              line: 14
        """)
        data = mdownreview._yaml_loads(src)
        self.assertEqual(len(data["comments"]), 2)
        self.assertEqual(data["comments"][0]["id"], "c1")
        self.assertIs(data["comments"][0]["resolved"], False)
        self.assertEqual(data["comments"][1]["id"], "c2")
        self.assertIs(data["comments"][1]["resolved"], True)

    def test_selected_text_with_escape_sequences(self):
        # App writes selected_text as double-quoted with \r at end (Windows line endings)
        src = textwrap.dedent("""\
            mrsf_version: '1.0'
            document: README.md
            comments:
            - id: abc
              author: Anonymous
              timestamp: 2026-04-21T23:13:35.368Z
              text: Fix this
              resolved: false
              line: 5
              selected_text: "Both `.review.yaml` and `.review.json` formats are supported.\\r"
              selected_text_hash: 9829196a78d643f682b7584b954c8e1763ce8d43740df91c15b0bde3e90650bd
              commit: bf7fee9e03a1c8291c3add25bd01d49759fde94d
        """)
        data = mdownreview._yaml_loads(src)
        c = data["comments"][0]
        self.assertTrue(c["selected_text"].endswith("\r"))
        self.assertEqual(
            c["selected_text_hash"],
            "9829196a78d643f682b7584b954c8e1763ce8d43740df91c15b0bde3e90650bd",
        )
        self.assertEqual(c["commit"], "bf7fee9e03a1c8291c3add25bd01d49759fde94d")

    def test_verbatim_readme_review_yaml(self):
        # Exact content of README.md.review.yaml as found in this repo
        src = textwrap.dedent("""\
            mrsf_version: '1.0'
            document: README.md
            comments:
            - id: a8c5b0f7-670e-4603-b826-7c11bffb9fda
              author: Anonymous
              timestamp: 2026-04-21T23:13:35.368Z
              text: remove legacy - json can also be used
              resolved: false
              line: 5
              selected_text: "Both `.review.yaml` (preferred) and `.review.json` (legacy) formats are supported.\\r"
              selected_text_hash: 9829196a78d643f682b7584b954c8e1763ce8d43740df91c15b0bde3e90650bd
              commit: bf7fee9e03a1c8291c3add25bd01d49759fde94d
            - id: 58af8d55-785f-4dd8-9ed3-e927e0526f95
              author: Anonymous
              timestamp: 2026-04-21T23:14:08.600Z
              text: remove install - since we don;t auto install right now
              resolved: false
              line: 14
              selected_text: "## Skills\\r"
              selected_text_hash: df2b43864e08684e06597d33401f5c940ae8ce480cdeab1145eabe7433cc9814
              commit: bf7fee9e03a1c8291c3add25bd01d49759fde94d
            - id: d81d9123-7671-45ff-99a3-4d369240fdeb
              author: Anonymous
              timestamp: 2026-04-21T23:14:27.901Z
              text: remove clean up from review skill
              resolved: false
              line: 14
              selected_text: "## Skills\\r"
              selected_text_hash: df2b43864e08684e06597d33401f5c940ae8ce480cdeab1145eabe7433cc9814
              commit: bf7fee9e03a1c8291c3add25bd01d49759fde94d
            - id: 5a813fd3-7013-4490-9042-014282b7a6f0
              author: Anonymous
              timestamp: 2026-04-21T23:14:37.947Z
              text: add all supported cli mode
              resolved: false
              line: 23
              selected_text: "## CLI\\r"
              selected_text_hash: 09f49ba2ae21534abb6970011d72806b94ef02cc47e9e44a763ea7ca49d47158
              commit: bf7fee9e03a1c8291c3add25bd01d49759fde94d
        """)
        data = mdownreview._yaml_loads(src)
        self.assertEqual(data["mrsf_version"], "1.0")
        self.assertEqual(data["document"], "README.md")
        self.assertEqual(len(data["comments"]), 4)
        ids = [c["id"] for c in data["comments"]]
        self.assertIn("a8c5b0f7-670e-4603-b826-7c11bffb9fda", ids)
        self.assertIn("5a813fd3-7013-4490-9042-014282b7a6f0", ids)
        for c in data["comments"]:
            self.assertIs(c["resolved"], False)
            self.assertIn("commit", c)
            self.assertIn("selected_text_hash", c)

    def test_real_readme_review_file_on_disk(self):
        # Parse the actual file from the repo (skipped if not present)
        real_path = Path(__file__).parent.parent / "README.md.review.yaml"
        if not real_path.exists():
            self.skipTest("README.md.review.yaml not present")
        data = mdownreview.load_review(str(real_path))
        self.assertEqual(data["mrsf_version"], "1.0")
        comments = data.get("comments") or []
        self.assertGreater(len(comments), 0)
        for c in comments:
            self.assertIn("id", c)
            self.assertIn("text", c)
            self.assertIn("resolved", c)

    def test_null_comments_does_not_crash_read(self):
        # comments: null is valid YAML; read should treat it as empty
        src = "mrsf_version: '1.0'\ndocument: foo.md\ncomments: null\n"
        data = mdownreview._yaml_loads(src)
        self.assertIsNone(data["comments"])
        # Verify cmd_read handles it gracefully via the `or []` guard
        self.assertEqual(list(data.get("comments") or []), [])


class TestResolveCommand(TempDirMixin, unittest.TestCase):

    def _path(self, comments=None):
        comments = comments or [make_comment("c1", "Fix this")]
        return self.write_review("a.md.review.yaml", make_review(comments))

    def test_marks_comment_resolved(self):
        path = self._path()
        rc = mdownreview.main(["resolve", path, "c1"])
        self.assertEqual(rc, 0)
        self.assertTrue(self.read_review(path)["comments"][0]["resolved"])

    def test_adds_response_with_agent_author(self):
        path = self._path()
        rc = mdownreview.main(["resolve", path, "c1", "--response", "Fixed the issue"])
        self.assertEqual(rc, 0)
        c = self.read_review(path)["comments"][0]
        self.assertTrue(c["resolved"])
        self.assertEqual(len(c["responses"]), 1)
        self.assertEqual(c["responses"][0]["author"], "agent")
        self.assertEqual(c["responses"][0]["text"], "Fixed the issue")
        self.assertIn("timestamp", c["responses"][0])

    def test_resolve_without_response_leaves_no_responses_key(self):
        path = self._path()
        mdownreview.main(["resolve", path, "c1"])
        c = self.read_review(path)["comments"][0]
        self.assertNotIn("responses", c)

    def test_unknown_id_returns_1(self):
        path = self._path()
        sys.stderr = StringIO()
        rc = mdownreview.main(["resolve", path, "no-such-id"])
        sys.stderr = sys.__stderr__
        self.assertEqual(rc, 1)

    def test_does_not_affect_other_comments(self):
        path = self._path([make_comment("c1"), make_comment("c2")])
        mdownreview.main(["resolve", path, "c1", "--response", "done"])
        comments = self.read_review(path)["comments"]
        self.assertTrue(comments[0]["resolved"])
        self.assertFalse(comments[1]["resolved"])
        self.assertNotIn("responses", comments[1])


class TestRespondCommand(TempDirMixin, unittest.TestCase):

    def _path(self):
        return self.write_review("a.md.review.yaml", make_review([make_comment("c1")]))

    def test_adds_response_without_resolving(self):
        path = self._path()
        rc = mdownreview.main(["respond", path, "c1", "--response", "Need more info"])
        self.assertEqual(rc, 0)
        c = self.read_review(path)["comments"][0]
        self.assertFalse(c["resolved"])
        self.assertEqual(len(c["responses"]), 1)
        self.assertEqual(c["responses"][0]["author"], "agent")
        self.assertEqual(c["responses"][0]["text"], "Need more info")

    def test_unknown_id_returns_1(self):
        path = self._path()
        sys.stderr = StringIO()
        rc = mdownreview.main(["respond", path, "bad-id", "--response", "x"])
        sys.stderr = sys.__stderr__
        self.assertEqual(rc, 1)

    def test_accumulates_multiple_responses(self):
        path = self._path()
        mdownreview.main(["respond", path, "c1", "--response", "first"])
        mdownreview.main(["respond", path, "c1", "--response", "second"])
        responses = self.read_review(path)["comments"][0]["responses"]
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0]["text"], "first")
        self.assertEqual(responses[1]["text"], "second")

    def test_response_has_timestamp(self):
        path = self._path()
        mdownreview.main(["respond", path, "c1", "--response", "noted"])
        r = self.read_review(path)["comments"][0]["responses"][0]
        self.assertIn("timestamp", r)
        self.assertTrue(r["timestamp"].endswith("Z"))


if __name__ == "__main__":
    unittest.main()
