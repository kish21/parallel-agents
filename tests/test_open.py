"""`lanekeeper open` and `spawn --open`: the worktree lands in an editor.

The editor under test is a small Python script that records what it was asked to open.
The real one is whatever `editor.command` names; nothing here depends on it existing.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

from lanekeeper.config import Config, EditorConfig, load_config, save_config
from lanekeeper.desk import EditorNotFoundError, editor_command, open_worktree

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402

FAKE_EDITOR = '''\
import sys, pathlib
pathlib.Path(sys.argv[1]).write_text(" ".join(sys.argv[2:]), encoding="utf-8")
'''


class FakeEditorTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.record = self.tmp / "opened.txt"
        self.script = self.tmp / "fake_editor.py"
        self.script.write_text(FAKE_EDITOR, encoding="utf-8")
        self.editor = EditorConfig(command=sys.executable,
                                   args=[str(self.script), str(self.record)])

    def wait_for_record(self, timeout=10.0) -> str:
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.record.exists() and self.record.read_text(encoding="utf-8"):
                return self.record.read_text(encoding="utf-8")
            time.sleep(0.05)
        self.fail("the editor was never started")


class TestOpenWorktree(FakeEditorTestCase):
    def test_the_editor_receives_the_worktree_path_last(self):
        wt = self.tmp / "wt"
        wt.mkdir()
        argv = open_worktree(self.editor, wt)
        self.assertEqual(argv[-1], str(wt))
        self.assertEqual(self.wait_for_record(), str(wt))

    def test_a_missing_editor_is_named(self):
        with self.assertRaises(EditorNotFoundError) as ctx:
            editor_command(EditorConfig(command="no-such-editor-xyz"), self.tmp)
        self.assertIn("no-such-editor-xyz", str(ctx.exception))
        self.assertIn("editor.command", str(ctx.exception))


class TestOpenCommand(FakeEditorTestCase):
    def setUp(self):
        super().setUp()
        self.repo = self.tmp / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.c"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.repo, check=True)
        (self.repo / "backend").mkdir()
        (self.repo / "backend" / "app.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.repo, check=True)
        cfg = Config.default("proj")
        cfg.capability_gates = {}
        cfg.editor = self.editor
        save_config(cfg, self.repo)

    def test_editor_setting_round_trips_through_the_config_file(self):
        loaded = load_config(self.repo)
        self.assertEqual(loaded.editor.command, sys.executable)
        self.assertEqual(loaded.editor.args, [str(self.script), str(self.record)])

    def test_a_config_without_an_editor_section_defaults_to_code(self):
        cfg_file = self.repo / ".lanekeeper" / "config.yaml"
        cfg_file.write_text("project:\n  name: p\nlanes:\n  backend:\n    allow: ['backend/**']\n",
                            encoding="utf-8")
        self.assertEqual(load_config(self.repo).editor.command, "code")

    def test_spawn_open_opens_the_new_worktree(self):
        res = run_cli(["spawn", "--lane", "backend", "--task", "t", "--open"], cwd=self.repo)
        self.assertEqual(res.returncode, 0, output_of(res))
        opened = Path(self.wait_for_record())
        self.assertTrue(opened.exists())
        self.assertEqual(opened.name, "agent-001")
        self.assertIn("Opened agent-001", res.stdout)

    def test_open_command_opens_an_existing_agent(self):
        res = run_cli(["spawn", "--lane", "backend", "--task", "t"], cwd=self.repo)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("lanekeeper open agent-001", res.stdout)
        res = run_cli(["open", "agent-001"], cwd=self.repo)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertEqual(Path(self.wait_for_record()).name, "agent-001")

    def test_open_of_an_unknown_agent_fails(self):
        res = run_cli(["open", "agent-009"], cwd=self.repo)
        self.assertEqual(res.returncode, 1, output_of(res))

    def test_a_missing_editor_does_not_undo_the_spawn(self):
        cfg = load_config(self.repo)
        cfg.editor = EditorConfig(command="no-such-editor-xyz")
        save_config(cfg, self.repo)
        res = run_cli(["spawn", "--lane", "backend", "--task", "t", "--open"], cwd=self.repo)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("successfully spawned", res.stdout)
        self.assertIn("no-such-editor-xyz", res.stderr)
        status = run_cli(["status", "--json"], cwd=self.repo)
        self.assertIn("agent-001", status.stdout)

    def test_the_lane_file_carries_the_boundary(self):
        run_cli(["spawn", "--lane", "backend", "--task", "add auth"], cwd=self.repo)
        lane_file = self.repo / ".lanekeeper" / "worktrees" / "agent-001" / ".lane"
        text = lane_file.read_text(encoding="utf-8")
        self.assertIn("ALLOW=", text)
        self.assertIn("backend/**", text)
        self.assertIn("DENY=", text)
        self.assertIn("TASK='add auth'", text)


if __name__ == "__main__":
    unittest.main()
