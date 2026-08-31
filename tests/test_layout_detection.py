"""Tests for repository layout detection.

The stock lanes assume `backend/`, `src/backend/`, `frontend/`, `web/`. Real projects are
rarely shaped that way, so on a normal repository every lane matched nothing and a new
user's first `validate` reported entirely legitimate work as out-of-lane — pointing at the
file rather than at the lane configuration that was actually wrong.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import Config
from lanekeeper.layout import detect_layout, measure_coverage, tracked_files

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402

LAYOUTS = {
    "python-src": ["src/myapp/api.py", "src/myapp/models.py", "tests/test_api.py",
                   "pyproject.toml", "README.md"],
    "django": ["myproject/settings.py", "myproject/urls.py", "accounts/views.py",
               "accounts/models.py", "migrations/0001.sql", "manage.py"],
    "nextjs": ["app/page.tsx", "app/layout.tsx", "components/Nav.tsx", "lib/api.ts",
               "package.json"],
    "monorepo": ["packages/api/server.py", "packages/api/db.py", "packages/web/App.tsx",
                 "packages/web/index.tsx", "infra/main.tf", "README.md"],
}


def make_repo(files):
    root = Path(tempfile.mkdtemp())
    for args in (["init", "-q", "-b", "main", "."],
                 ["config", "user.email", "t@t.c"],
                 ["config", "user.name", "t"]):
        subprocess.run(["git", *args], cwd=root, check=True, capture_output=True)
    for rel in files:
        f = root / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text("content\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True, capture_output=True)
    subprocess.run(["git", "commit", "-qm", "init"], cwd=root, check=True, capture_output=True)
    return root


class TestDetectionBeatsTheStockDefaults(unittest.TestCase):
    def test_every_realistic_layout_is_fully_covered(self):
        stock = Config.default("x").lanes
        for name, files in LAYOUTS.items():
            with self.subTest(layout=name):
                root = make_repo(files)
                self.addCleanup(shutil.rmtree, root, ignore_errors=True)

                detected = detect_layout(root)
                stock_coverage, _, _ = measure_coverage(root, stock)

                self.assertEqual(detected.coverage, 1.0,
                                 f"{name}: uncovered {detected.uncovered_examples}")
                self.assertGreater(detected.coverage, stock_coverage,
                                   f"{name}: detection must beat the stock lanes")
                self.assertTrue(detected.is_meaningful)

    def test_stock_lanes_really_do_miss_these_layouts(self):
        """Pins the problem being solved, so a defaults change cannot mask it."""
        stock = Config.default("x").lanes
        root = make_repo(LAYOUTS["python-src"])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        coverage, total, _ = measure_coverage(root, stock)
        self.assertEqual(total, 5)
        self.assertLess(coverage, 0.5)


class TestDetectionSpecifics(unittest.TestCase):
    def _detect(self, files):
        root = make_repo(files)
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        return detect_layout(root), root

    def test_container_directories_are_transparent(self):
        """`src/` and `packages/` are not lanes; their children are."""
        layout, _ = self._detect(["packages/api/a.py", "packages/api/b.py",
                                  "packages/web/a.tsx", "packages/web/b.tsx"])
        self.assertIn("backend", layout.lanes)
        self.assertIn("frontend", layout.lanes)
        allow = layout.lanes["backend"].allow + layout.lanes["frontend"].allow
        self.assertNotIn("packages/**", allow)

    def test_lanes_are_mutually_exclusive(self):
        """One lane, one owner: each lane denies every other lane's paths."""
        layout, _ = self._detect(["api/a.py", "api/b.py", "web/a.tsx", "web/b.tsx"])
        for name, lane in layout.lanes.items():
            others = {p for other, o in layout.lanes.items() if other != name for p in o.allow}
            self.assertEqual(set(lane.deny), others, f"{name} must deny every other lane")

    def test_classification_falls_back_to_file_extensions(self):
        """A directory whose name says nothing is classified by what is in it."""
        layout, _ = self._detect(["zzz/handler.py", "zzz/models.py"])
        self.assertIn("backend", layout.lanes)

    def test_root_files_are_owned_by_platform(self):
        layout, _ = self._detect(["src/app/x.py", "src/app/y.py", "README.md", "pyproject.toml"])
        self.assertIn("*", layout.lanes["platform"].allow)
        self.assertEqual(layout.coverage, 1.0)

    def test_build_output_is_ignored(self):
        layout, _ = self._detect(["src/app/x.py", "src/app/y.py",
                                  "node_modules/pkg/index.js", "dist/bundle.js"])
        allow = [p for lane in layout.lanes.values() for p in lane.allow]
        self.assertFalse(any("node_modules" in p or "dist" in p for p in allow), allow)

    def test_repo_of_only_root_files_is_not_a_detected_structure(self):
        """A bare README yields only the root catch-all, which describes nothing."""
        layout, _ = self._detect(["README.md"])
        self.assertEqual(layout.substantive_lanes, [])
        self.assertFalse(layout.is_meaningful)

    def test_single_code_area_is_still_adopted(self):
        layout, _ = self._detect(["src/app/x.py", "src/app/y.py", "README.md"])
        self.assertEqual(layout.substantive_lanes, ["backend"])
        self.assertTrue(layout.is_meaningful)

    def test_untracked_files_are_not_considered(self):
        layout, root = self._detect(["src/app/x.py", "src/app/y.py"])
        (root / "scratch").mkdir()
        (root / "scratch" / "note.txt").write_text("x", encoding="utf-8")
        self.assertNotIn("scratch", tracked_files(root))

    def test_non_git_directory_degrades_quietly(self):
        tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        self.assertEqual(tracked_files(tmp), [])


class TestInitUsesDetection(unittest.TestCase):
    def test_init_adopts_detected_lanes_and_reports_coverage(self):
        root = make_repo(LAYOUTS["monorepo"])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        res = run_cli(["init", "--name", "proj"], root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Detected", res.stdout)
        self.assertIn("100%", res.stdout)

    def test_generic_flag_opts_out_and_warns_about_poor_coverage(self):
        root = make_repo(LAYOUTS["python-src"])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        res = run_cli(["init", "--name", "proj", "--generic"], root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("generic starter lanes", res.stdout)
        self.assertIn("match little of this repository", res.stdout)

    def test_detected_lanes_make_a_real_edit_validate_cleanly(self):
        """The end-to-end symptom: legitimate work must not read as out-of-lane."""
        root = make_repo(LAYOUTS["python-src"])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        self.assertEqual(run_cli(["init", "--name", "proj"], root).returncode, 0)
        spawn = run_cli(["spawn", "--lane", "backend", "--seat", "SR1",
                         "--name", "w1", "--task", "t"], root)
        self.assertEqual(spawn.returncode, 0, output_of(spawn))

        import json
        agents = json.loads((root / ".lanekeeper/state/agents.json").read_text())
        wt = Path(agents["agent-001"]["worktree_path"])
        target = wt / "src" / "myapp" / "api.py"
        target.write_text(target.read_text(encoding="utf-8") + "\ndef new(): pass\n", encoding="utf-8")

        res = run_cli(["validate", "agent-001"], root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("VALIDATION PASSED", res.stdout)


class TestOutOfLaneErrorIsActionable(unittest.TestCase):
    def test_error_points_at_the_lane_config_when_no_lane_claims_the_path(self):
        root = make_repo(LAYOUTS["python-src"])
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        # --generic forces lanes that match nothing, reproducing the original experience.
        self.assertEqual(run_cli(["init", "--name", "proj", "--generic"], root).returncode, 0)
        self.assertEqual(run_cli(["spawn", "--lane", "backend", "--seat", "SR1",
                                  "--name", "w1", "--task", "t"], root).returncode, 0)

        import json
        agents = json.loads((root / ".lanekeeper/state/agents.json").read_text())
        wt = Path(agents["agent-001"]["worktree_path"])
        target = wt / "src" / "myapp" / "api.py"
        target.write_text(target.read_text(encoding="utf-8") + "\nx = 1\n", encoding="utf-8")

        res = run_cli(["validate", "agent-001"], root)
        self.assertEqual(res.returncode, 2)
        self.assertIn("No declared lane allows", res.stdout)
        self.assertIn("config.yaml", res.stdout)
        # The path must be reported intact, not truncated by porcelain mis-parsing.
        self.assertIn("src/myapp/api.py", res.stdout)


if __name__ == "__main__":
    unittest.main()
