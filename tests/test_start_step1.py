"""`lanekeeper start` end to end, against #37's definition of done.

The tracker is injected at the command's own seam (`cli.get_tracker`), so these run the
real command — configuration loading, the gate, the printing, the exit code — without a
network, a GitHub account, or `gh` being installed.
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

from lanekeeper import cli, paths
from lanekeeper.config import Config, save_config

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402
from _intake_fakes import FakeTracker, issue  # noqa: E402

PRODUCT_MD = "# App\n\n## Scope\n- Checkout\n- Search\n"

GOOD_ISSUES = [
    issue(1, "Checkout coupon fix", body="backend/api/checkout.py"),
    issue(2, "Search facets", body="frontend/src/search/Facets.tsx"),
    issue(3, "Checkout address form", body="frontend/src/checkout/Address.tsx"),
]


@contextlib.contextmanager
def in_dir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


def tree(root):
    return sorted(str(p.relative_to(root)) for p in Path(root).rglob("*"))


class StartTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init"], cwd=self.root, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def run_start(self, issues, command="start", available=True, reason="", **flags):
        """Runs the real command with a tracker injected at the CLI's own seam."""
        args = argparse.Namespace(take_as_is=flags.get("take_as_is", False),
                                  fresh=flags.get("fresh", False))
        original = cli.get_tracker
        cli.get_tracker = lambda settings, root, runner=None: FakeTracker(
            issues, available=available, reason=reason)
        buffer = io.StringIO()
        try:
            with in_dir(self.root), contextlib.redirect_stdout(buffer):
                code = (cli.cmd_start if command == "start" else cli.cmd_intake)(args)
        finally:
            cli.get_tracker = original
        return code, buffer.getvalue()


class TestNoWorkWrittenDown(StartTestCase):
    def test_points_at_the_playbook_and_writes_nothing(self):
        before = tree(self.root)
        code, out = self.run_start([])
        self.assertEqual(code, 1)
        self.assertIn("product-playbook", out)
        for step in ("/vision", "/scope", "/plan"):
            self.assertIn(step, out)
        self.assertIn("changed nothing", out)
        self.assertEqual(tree(self.root), before,
                         "a stopped run must leave the project untouched")

    def test_works_without_any_configuration_file(self):
        # Step 1 runs before anything is set up, so a project that has never been
        # initialised is the normal case rather than an error.
        self.assertFalse(paths.config_path(self.root).exists())
        code, out = self.run_start([])
        self.assertEqual(code, 1)
        self.assertNotIn("Traceback", out)
        self.assertFalse(paths.config_path(self.root).exists())


class TestCoverage(StartTestCase):
    def test_reports_features_with_nothing_written_against_them(self):
        (self.root / "PRODUCT.md").write_text("## Scope\n- Checkout\n- Billing\n",
                                              encoding="utf-8")
        code, out = self.run_start(GOOD_ISSUES)
        self.assertEqual(code, 1)
        self.assertIn("Billing", out)
        self.assertIn("PRODUCT.md", out)
        self.assertNotIn("Checkout\n", out.split("nothing written")[-1][:40])

    def test_cannot_judge_is_said_plainly_and_never_guessed(self):
        code, out = self.run_start(GOOD_ISSUES)
        self.assertEqual(code, 1)
        self.assertIn("cannot tell whether that is", out)
        self.assertIn("I count 3 pieces of work", out)
        self.assertNotIn("every thing that document says", out)

    def test_a_covered_backlog_passes_and_says_what_is_not_built_yet(self):
        (self.root / "PRODUCT.md").write_text(PRODUCT_MD, encoding="utf-8")
        code, out = self.run_start(GOOD_ISSUES)
        self.assertEqual(code, 0)
        self.assertIn("The work is written down", out)
        self.assertIn("not built yet", out)


class TestResumeAndSideEffects(StartTestCase):
    def test_the_second_run_resumes_instead_of_restarting(self):
        (self.root / "PRODUCT.md").write_text(PRODUCT_MD, encoding="utf-8")
        first_code, _ = self.run_start(GOOD_ISSUES)
        self.assertEqual(first_code, 0)
        second_code, out = self.run_start(GOOD_ISSUES)
        self.assertEqual(second_code, 0)
        self.assertIn("already done", out)

    def test_fresh_checks_again(self):
        (self.root / "PRODUCT.md").write_text(PRODUCT_MD, encoding="utf-8")
        self.run_start(GOOD_ISSUES)
        _, out = self.run_start(GOOD_ISSUES, fresh=True)
        self.assertNotIn("already done", out)

    def test_start_never_writes_the_configuration_file(self):
        (self.root / "PRODUCT.md").write_text(PRODUCT_MD, encoding="utf-8")
        code, _ = self.run_start(GOOD_ISSUES)
        self.assertEqual(code, 0)
        # It records what step 1 decided, and nothing else.
        self.assertFalse(paths.config_path(self.root).exists())
        self.assertTrue(paths.intake_record_path(self.root).is_file())

    def test_an_existing_configuration_is_left_alone(self):
        cfg = Config.default(project_name="existing")
        save_config(cfg, self.root)
        before = paths.config_path(self.root).read_text(encoding="utf-8")
        (self.root / "PRODUCT.md").write_text(PRODUCT_MD, encoding="utf-8")
        self.run_start(GOOD_ISSUES)
        self.assertEqual(paths.config_path(self.root).read_text(encoding="utf-8"), before)

    def test_take_as_is_carries_on_when_coverage_cannot_be_judged(self):
        stopped, _ = self.run_start(GOOD_ISSUES)
        self.assertEqual(stopped, 1)
        passed, out = self.run_start(GOOD_ISSUES, take_as_is=True)
        self.assertEqual(passed, 0)
        self.assertIn("because you said so", out)


class TestUnreadableTracker(StartTestCase):
    def test_reports_why_rather_than_claiming_an_empty_backlog(self):
        code, out = self.run_start([], available=False,
                                   reason="Run 'gh auth login' and try again.")
        self.assertEqual(code, 1)
        self.assertIn("could not read", out)
        self.assertIn("gh auth login", out)
        self.assertNotIn("no written-down work", out)


class TestCommandWiring(unittest.TestCase):
    """The subcommands exist as a real process, and `init` is untouched."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        subprocess.run(["git", "init"], cwd=self.root, capture_output=True)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_start_and_intake_are_registered(self):
        res = run_cli(["--help"], self.root)
        self.assertIn("start", res.stdout, output_of(res))
        self.assertIn("intake", res.stdout, output_of(res))
        self.assertIn("init", res.stdout, output_of(res))

    def test_intake_with_no_tracker_configured_says_so(self):
        cfg = Config.default(project_name="untracked")
        cfg.intake.tracker = "none"
        save_config(cfg, self.root)
        res = run_cli(["intake"], self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("could not read", res.stdout, output_of(res))

    def test_an_unknown_tracker_fails_closed(self):
        cfg = Config.default(project_name="untracked")
        cfg.intake.tracker = "jira"
        save_config(cfg, self.root)
        res = run_cli(["intake"], self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("Unknown tracker", res.stderr, output_of(res))

    def test_init_still_behaves_exactly_as_before(self):
        res = run_cli(["init", "--name", "demo"], self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Initialized lanekeeper", res.stdout, output_of(res))
        self.assertTrue(paths.config_path(self.root).is_file())


if __name__ == "__main__":
    unittest.main()
