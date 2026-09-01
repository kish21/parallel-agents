"""Confirming a division changes who may touch what — for real, not in a file nothing reads.

`lanes.yaml` is the human record. `config.yaml`'s `lanes` section is what `spawn`,
`validate` and `check` enforce. Until `--confirm` wrote both, the confirmation message
said "this is what I read from now on" and it was not. And the project's own worked
example could not be confirmed at all, because two wildcard segments were assumed to
collide.
"""

import argparse
import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper import cli, paths
from lanekeeper.config import Config, load_config, save_config
from lanekeeper.divide import draft as draft_mod
from lanekeeper.config import DivideConfig

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import FakeTracker  # noqa: E402
from test_divide_worked_example import EXAMPLE, tree_from  # noqa: E402


@contextlib.contextmanager
def in_dir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class ConfirmTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        subprocess.run(["git", "init", "-q"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.c"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.root, check=True)

    def commit(self, files):
        for name in files:
            p = self.root / name
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("x\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "files"], cwd=self.root, check=True,
                       capture_output=True)

    def write_draft(self, text):
        path = self.root / paths.home_dirname() / "start" / "lanes.draft.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def confirm(self, force=False):
        args = argparse.Namespace(take_as_is=True, fresh=True, confirm=True, force=force,
                                  redraft=False)
        original = cli.get_tracker
        cli.get_tracker = lambda settings, root, runner=None: FakeTracker([])
        out = io.StringIO()
        try:
            with in_dir(self.root), contextlib.redirect_stdout(out):
                code = cli.cmd_divide(args)
        finally:
            cli.get_tracker = original
        return code, out.getvalue()


class TestConfirmWritesThePolicy(ConfirmTestCase):
    DRAFT = ("version: 1\nlanes:\n  catalog:\n    tickets: ['1']\n    allow:\n"
             "      - backend/app/domains/catalog/**\n    deny:\n      - backend/app/domains/catalog/legacy/**\n"
             "  search:\n    allow:\n      - backend/app/domains/search/**\n")

    def test_a_project_with_no_policy_gets_one_with_these_lanes(self):
        self.commit(["backend/app/domains/catalog/a.py", "backend/app/domains/search/b.py"])
        self.write_draft(self.DRAFT)
        code, out = self.confirm()
        self.assertEqual(code, 0, out)
        cfg = load_config(self.root)
        self.assertEqual(sorted(cfg.lanes), ["catalog", "search"])
        self.assertEqual(cfg.lanes["catalog"].allow, ["backend/app/domains/catalog/**"])
        self.assertEqual(cfg.lanes["catalog"].deny, ["backend/app/domains/catalog/legacy/**"])
        self.assertIn("config.yaml", out)
        self.assertTrue((self.root / "lanes.yaml").exists())

    def test_an_existing_policy_keeps_everything_but_its_lanes(self):
        self.commit(["backend/app/domains/catalog/a.py", "backend/app/domains/search/b.py"])
        cfg = Config.default("kept")
        cfg.max_agents = 9
        save_config(cfg, self.root)
        self.write_draft(self.DRAFT)
        code, out = self.confirm()
        self.assertEqual(code, 0, out)
        after = load_config(self.root)
        self.assertEqual(after.max_agents, 9)
        self.assertEqual(after.project_name, "kept")
        self.assertNotIn("backend", after.lanes)
        self.assertEqual(sorted(after.lanes), ["catalog", "search"])

    def test_a_refused_confirm_changes_no_policy(self):
        self.commit(["backend/app/domains/catalog/a.py"])
        cfg = Config.default("kept")
        save_config(cfg, self.root)
        before = (self.root / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8")
        self.write_draft("version: 1\nlanes:\n  empty:\n    allow: []\n")
        code, out = self.confirm()
        self.assertEqual(code, 1, out)
        self.assertEqual((self.root / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8"),
                         before)


class TestTheWorkedExampleConfirms(unittest.TestCase):
    def test_the_example_lane_file_has_no_collisions_against_its_own_tree(self):
        document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        settings = DivideConfig()
        draft_path = tmp / paths.home_dirname() / "start" / "lanes.draft.yaml"
        draft_path.parent.mkdir(parents=True)
        draft_path.write_text(yaml.safe_dump(document), encoding="utf-8")
        lanes, doc, problem = draft_mod.load(tmp, settings)
        self.assertIsNone(problem)
        report = draft_mod.validate(lanes, tree_from(document), settings, document=doc)
        self.assertEqual([p.detail for p in report.problems], [])
        self.assertEqual(
            [(o.left, o.right, o.kind) for o in report.overlaps], [],
            "the project's own example must confirm cleanly")
        self.assertTrue(report.ok)


if __name__ == "__main__":
    unittest.main()
