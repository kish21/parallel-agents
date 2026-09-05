"""Running lanekeeper against a repository that is not the current directory — #28.

Every command derives everything from `Path.cwd()`, so `--repo` is one chdir done
once in `main()`. These tests are about the two things that can go wrong with that:
the flag being ignored in the position people type it in, and a path that is not a
repository root being accepted quietly.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.capabilities import default_cards, save_card
from lanekeeper.config import generate_default_config, save_config

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=str(root), check=True,
                          capture_output=True, text=True, encoding="utf-8")


class TestRepoFlag(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.tmp), ignore_errors=True)
        self.elsewhere = self.tmp / "elsewhere"
        self.elsewhere.mkdir()
        self.project = self.tmp / "project"
        self.project.mkdir()
        _git(self.project, "init", "-q", "-b", "main", ".")
        _git(self.project, "config", "user.email", "t@t.c")
        _git(self.project, "config", "user.name", "t")
        (self.project / "README.md").write_text("# p\n", encoding="utf-8")
        _git(self.project, "add", "-A")
        _git(self.project, "commit", "-qm", "init")

        config = generate_default_config("Elsewhere-App")
        save_config(config, self.project)
        for card in default_cards(sorted(config.lanes)):
            save_card(card, self.project)

    def test_status_runs_against_another_repository(self):
        res = run_cli(["--repo", str(self.project), "status"], cwd=self.elsewhere)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("ELSEWHERE-APP", res.stdout.upper(), output_of(res))

    def test_the_flag_works_after_the_subcommand_too(self):
        res = run_cli(["status", "--repo", str(self.project)], cwd=self.elsewhere)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("ELSEWHERE-APP", res.stdout.upper(), output_of(res))

    def test_short_form_matches_git(self):
        res = run_cli(["-C", str(self.project), "status"], cwd=self.elsewhere)
        self.assertEqual(res.returncode, 0, output_of(res))

    def test_a_missing_directory_is_named(self):
        missing = self.tmp / "no-such-place"
        res = run_cli(["--repo", str(missing), "status"], cwd=self.elsewhere)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("no such directory", (res.stdout + res.stderr).lower())

    def test_a_directory_that_is_not_a_repository_is_refused(self):
        res = run_cli(["--repo", str(self.elsewhere), "status"], cwd=self.project)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("not inside a Git repository", res.stdout + res.stderr)

    def test_a_subdirectory_is_refused_and_the_root_is_named(self):
        sub = self.project / "src"
        sub.mkdir()
        res = run_cli(["--repo", str(sub), "status"], cwd=self.elsewhere)
        self.assertEqual(res.returncode, 1, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn("not its root", out, output_of(res))
        self.assertIn(self.project.as_posix(), out.replace("\\", "/"), output_of(res))

    def test_board_keeps_its_own_repo_option(self):
        # `board --repo OWNER/NAME` predates the global flag and means a GitHub
        # repository, not a directory. It must not be read as a path to enter.
        res = run_cli(["board", "--repo", "owner/name", "--show"], cwd=self.project)
        self.assertNotIn("no such directory", (res.stdout + res.stderr).lower(),
                         output_of(res))


if __name__ == "__main__":
    unittest.main()
