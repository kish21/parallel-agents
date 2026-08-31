"""Regression tests for changed-file detection.

`get_changed_files` called `line.strip()` before slicing `line[3:]` out of
`git status --porcelain`. The porcelain format is `XY<space>PATH`, where the two status
columns are position-significant and X is a space when a change is not staged — so an
unstaged edit reads `" M path"`. Stripping first removed that leading space and the slice
then took the first character of the path with it: `secrets/prod.pem` was reported as
`ecrets/prod.pem`.

No lane or capability pattern matched the corrupted path, so **editing** a protected file
passed validation while **creating** one was correctly blocked. Newly created files are
reported as `"?? path"` — no leading space — which is why the whole existing suite, which
only ever created files, passed over this.
"""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from parallel_agents.config import LaneConfig
from parallel_agents.lanes import LaneEngine
from parallel_agents.worktree import WorktreeManager


class ChangedFilesTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._git("init", "-q", "-b", "main", ".")
        self._git("config", "user.email", "t@t.c")
        self._git("config", "user.name", "t")
        for rel in ["secrets/prod.pem", "src/api.py", "src/café.py", "weird dir/a b.py"]:
            f = self.tmp / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("original\n", encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", "init")
        self.wt = WorktreeManager(self.tmp)

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.tmp, check=True, capture_output=True)

    def _changed(self):
        return self.wt.get_changed_files(self.tmp)


class TestPathsAreNotTruncated(ChangedFilesTestCase):
    def test_modified_file_keeps_its_first_character(self):
        """The defect itself."""
        (self.tmp / "secrets" / "prod.pem").write_text("changed\n", encoding="utf-8")
        changed = self._changed()
        self.assertIn("secrets/prod.pem", changed)
        self.assertNotIn("ecrets/prod.pem", changed)

    def test_staged_and_unstaged_modifications_both_parse(self):
        (self.tmp / "src" / "api.py").write_text("unstaged\n", encoding="utf-8")
        (self.tmp / "secrets" / "prod.pem").write_text("staged\n", encoding="utf-8")
        self._git("add", "secrets/prod.pem")
        changed = self._changed()
        self.assertIn("src/api.py", changed)
        self.assertIn("secrets/prod.pem", changed)

    def test_untracked_file_still_parses(self):
        (self.tmp / "src" / "brand_new.py").write_text("new\n", encoding="utf-8")
        self.assertIn("src/brand_new.py", self._changed())

    def test_deleted_file_is_reported_intact(self):
        (self.tmp / "src" / "api.py").unlink()
        self.assertIn("src/api.py", self._changed())

    def test_renamed_file_reports_the_destination(self):
        self._git("mv", "src/api.py", "src/renamed.py")
        changed = self._changed()
        self.assertIn("src/renamed.py", changed)
        # The source path must not be mistaken for a separate changed file entry.
        self.assertNotIn("rc/api.py", changed)

    def test_paths_with_spaces_survive(self):
        (self.tmp / "weird dir" / "a b.py").write_text("edited\n", encoding="utf-8")
        self.assertIn("weird dir/a b.py", self._changed())

    def test_non_ascii_paths_are_not_escaped(self):
        """Git quotes non-ASCII paths in line mode; -z output must not."""
        (self.tmp / "src" / "café.py").write_text("edited\n", encoding="utf-8")
        changed = self._changed()
        self.assertIn("src/café.py", changed)
        self.assertFalse(any(c.startswith('"') for c in changed), changed)


class TestProtectedPathsCannotBeEditedPastTheGate(ChangedFilesTestCase):
    """The security consequence: a deny rule that caught creation but not modification."""

    LANE = LaneConfig(name="platform", allow=["**"], deny=["secrets/**"])

    def test_creating_a_protected_file_is_blocked(self):
        (self.tmp / "secrets" / "new.pem").write_text("k\n", encoding="utf-8")
        result = LaneEngine.validate_files(self._changed(), self.LANE)
        self.assertFalse(result.is_valid)

    def test_modifying_a_protected_file_is_also_blocked(self):
        (self.tmp / "secrets" / "prod.pem").write_text("exfiltrated\n", encoding="utf-8")
        result = LaneEngine.validate_files(self._changed(), self.LANE)
        self.assertFalse(result.is_valid, "editing a denied file must be blocked, not only creating it")
        self.assertIn("secrets/prod.pem", {v.filepath for v in result.violations})

    def test_deleting_a_protected_file_is_blocked(self):
        (self.tmp / "secrets" / "prod.pem").unlink()
        result = LaneEngine.validate_files(self._changed(), self.LANE)
        self.assertFalse(result.is_valid)


class TestPorcelainParser(unittest.TestCase):
    """Unit-level checks on the parser, independent of a real repository."""

    parse = staticmethod(WorktreeManager._parse_porcelain_z)

    def test_unstaged_modification_leading_space(self):
        self.assertEqual(self.parse(" M secrets/prod.pem\0"), ["secrets/prod.pem"])

    def test_staged_modification(self):
        self.assertEqual(self.parse("M  src/api.py\0"), ["src/api.py"])

    def test_untracked(self):
        self.assertEqual(self.parse("?? src/new.py\0"), ["src/new.py"])

    def test_rename_skips_the_source_path(self):
        self.assertEqual(self.parse("R  src/new.py\0src/old.py\0"), ["src/new.py"])

    def test_mixed_entries(self):
        raw = " M a.py\0?? b.py\0R  d.py\0c.py\0 D e.py\0"
        self.assertEqual(self.parse(raw), ["a.py", "b.py", "d.py", "e.py"])

    def test_empty_and_short_entries_are_ignored(self):
        self.assertEqual(self.parse(""), [])
        self.assertEqual(self.parse("\0\0"), [])
        self.assertEqual(self.parse("M \0"), [])


if __name__ == "__main__":
    unittest.main()
