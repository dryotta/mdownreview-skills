#!/usr/bin/env python3
"""Tests for mdownreview.py CLI."""

import json
import os
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path
from io import StringIO

# Ensure the scripts directory is importable
sys.path.insert(0, os.path.dirname(__file__))

import mdownreview


def make_review(comments, version=3):
    """Build a review sidecar dict."""
    return {"version": version, "comments": comments}


def make_comment(id_, text="Fix this", line=10, resolved=False, responses=None):
    """Build a single comment dict."""
    c = {
        "id": id_,
        "anchorType": "line",
        "lineHash": "abcd1234",
        "lineNumber": line,
        "text": text,
        "createdAt": "2026-01-01T00:00:00.000Z",
        "resolved": resolved,
    }
    if responses is not None:
        c["responses"] = responses
    return c


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
            json.dump(data, f)
        return full

    def read_review(self, path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)


# ===== read =====

class TestReadText(TempDirMixin, unittest.TestCase):
    """read subcommand — text format."""

    def test_unresolved_only(self):
        self.write_review("app.tsx.review.json", make_review([
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
        self.write_review("app.tsx.review.json", make_review([
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
        self.write_review(os.path.join("sub", "deep", "x.md.review.json"), make_review([
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
        self.write_review("app.tsx.review.json", make_review([
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
        self.write_review("app.tsx.review.json", make_review([
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
        self.write_review(os.path.join("sub", "x.md.review.json"), make_review([
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
        fpath = self.write_review("a.md.review.json", make_review([
            make_comment("c1", "Fix", resolved=True),
            make_comment("c2", "Also", resolved=True),
        ]))
        # Keep one with unresolved
        keep = self.write_review("b.md.review.json", make_review([
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
        fpath = self.write_review("a.md.review.json", make_review([
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
        self.write_review("a.md.review.json", make_review([
            make_comment("c1", resolved=True),
        ]))
        self.write_review("b.md.review.json", make_review([
            make_comment("c2", resolved=True),
        ]))
        self.write_review("c.md.review.json", make_review([
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

    def test_open_not_found_install_fails(self):
        """cmd_open exits 1 when binary not found and install fails."""
        with unittest.mock.patch.object(mdownreview, "find_app_binary", return_value=None):
            with unittest.mock.patch.object(mdownreview, "install_app", return_value=None):
                old_stdout, old_stderr = sys.stdout, sys.stderr
                sys.stdout = StringIO()
                sys.stderr = buf_err = StringIO()
                rc = mdownreview.main(["open"])
                sys.stdout, sys.stderr = old_stdout, old_stderr
        self.assertEqual(rc, 1)
        self.assertIn("could not be installed", buf_err.getvalue())

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

    def test_open_auto_installs_when_not_found(self):
        """cmd_open tries install_app when find_app_binary returns None."""
        call_count = [0]

        def find_side_effect():
            call_count[0] += 1
            if call_count[0] == 1:
                return None  # first call: not found
            return "/installed/app"  # after install

        with unittest.mock.patch.object(mdownreview, "find_app_binary", side_effect=find_side_effect):
            with unittest.mock.patch.object(mdownreview, "install_app", return_value="/installed/app"):
                with unittest.mock.patch("subprocess.Popen"):
                    old_stdout, old_stderr = sys.stdout, sys.stderr
                    sys.stdout = StringIO()
                    sys.stderr = StringIO()
                    rc = mdownreview.main(["open"])
                    sys.stdout, sys.stderr = old_stdout, old_stderr
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
