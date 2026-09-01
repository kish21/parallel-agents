"""`lanekeeper check`: the boundary check as a pull-request gate.

The gate runs on a plain checkout with no agent state, so these tests build a repository
with a tracked lane policy, make a branch, and run the CLI as a subprocess exactly as CI
would. The base is the local `main` here; in CI it is `origin/<target>`.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper import check
from lanekeeper.config import Config, InvalidLaneError, LaneConfig, load_config, save_config

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


class CheckoutTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._git("init", "-q", "-b", "main", ".")
        self._git("config", "user.email", "t@t.c")
        self._git("config", "user.name", "t")
        for rel in ["src/checkout/cart.py", "src/catalog/list.py", "secrets/prod.pem"]:
            f = self.tmp / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("original\n", encoding="utf-8")
        cfg = Config.default("proj")
        cfg.lanes = {
            "checkout": LaneConfig(name="checkout", allow=["src/checkout/**"], deny=["secrets/"]),
            "catalog": LaneConfig(name="catalog", allow=["src/catalog/**"], deny=[]),
        }
        cfg.capability_gates = {}
        save_config(cfg, self.tmp)
        self._git("add", "-A")
        self._git("commit", "-qm", "init")
        self._git("checkout", "-qb", "feature")

    def _git(self, *args):
        return subprocess.run(["git", *args], cwd=self.tmp, check=True, capture_output=True)

    def _commit(self, rel, text="changed\n"):
        f = self.tmp / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        self._git("add", "-A")
        self._git("commit", "-qm", f"touch {rel}")

    def _check(self, *args):
        return run_cli(["check", "--base", "main", *args], cwd=self.tmp)


class TestTheGateVerdict(CheckoutTestCase):
    def test_a_change_inside_its_lane_passes(self):
        self._commit("src/checkout/cart.py")
        res = self._check("--lane", "checkout")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("CHECK PASSED", res.stdout)

    def test_a_change_outside_its_lane_fails_and_names_the_file(self):
        self._commit("src/catalog/list.py")
        res = self._check("--lane", "checkout")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("src/catalog/list.py", res.stdout)
        self.assertIn("CHECK FAILED", res.stdout)

    def test_a_denied_file_fails(self):
        self._commit("secrets/prod.pem")
        res = self._check("--lane", "checkout")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("denied", res.stdout)

    def test_an_undeclared_lane_is_not_a_pass(self):
        self._commit("src/checkout/cart.py")
        res = self._check("--lane", "chekout")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("chekout", res.stdout)

    def test_no_lane_at_all_is_refused(self):
        self._commit("src/checkout/cart.py")
        res = self._check()
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("--lane", res.stderr)

    def test_a_base_that_cannot_be_diffed_is_a_failure(self):
        self._commit("secrets/prod.pem")
        res = run_cli(["check", "--lane", "checkout", "--base", "no-such-branch"], cwd=self.tmp)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("nothing was checked", res.stdout)

    def test_working_tree_flag_includes_uncommitted_files(self):
        (self.tmp / "src" / "catalog" / "list.py").write_text("edited\n", encoding="utf-8")
        clean = self._check("--lane", "checkout")
        self.assertEqual(clean.returncode, 0, output_of(clean))
        dirty = self._check("--lane", "checkout", "--working-tree")
        self.assertEqual(dirty.returncode, 2, output_of(dirty))

    def test_a_rename_out_of_another_lane_fails(self):
        self._git("mv", "src/catalog/list.py", "src/checkout/list.py")
        self._git("commit", "-qm", "move")
        res = self._check("--lane", "checkout")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("src/catalog/list.py", res.stdout)


class TestTheLaneComesFromTheLabels(CheckoutTestCase):
    def test_one_lane_label_is_used(self):
        self._commit("src/checkout/cart.py")
        res = self._check("--labels-json", '["bug", "lane: checkout"]')
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("lane 'checkout'", res.stdout)

    def test_no_lane_label_fails_closed(self):
        self._commit("src/checkout/cart.py")
        res = self._check("--labels-json", '["bug"]')
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("no 'lane: <name>' label", res.stderr)

    def test_two_lane_labels_fail_closed(self):
        self._commit("src/checkout/cart.py")
        res = self._check("--labels-json", '["lane: checkout", "lane: catalog"]')
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("2 lane labels", res.stderr)

    def test_label_parsing(self):
        self.assertEqual(check.lane_from_labels(["Lane:  Checkout ", "x"]), "Checkout")
        with self.assertRaises(check.NoLaneError):
            check.lane_from_labels(["lane:"])
        with self.assertRaises(check.NoLaneError):
            check.lane_from_labels_json("not json")
        with self.assertRaises(check.NoLaneError):
            check.lane_from_labels_json('{"a": 1}')


class TestAPolicyChangeIsItsOwnLane(CheckoutTestCase):
    def test_a_change_to_the_policy_alone_passes_as_policy(self):
        self._commit(".lanekeeper/config.yaml", (self.tmp / ".lanekeeper/config.yaml")
                     .read_text(encoding="utf-8") + "\n# reviewed\n")
        res = self._check("--lane", "policy")
        self.assertEqual(res.returncode, 0, output_of(res))

    def test_a_policy_change_that_also_touches_code_fails(self):
        self._commit(".lanekeeper/config.yaml", "project:\n  name: p\nlanes:\n  "
                     "checkout:\n    allow: ['**']\n")
        self._commit("src/checkout/cart.py")
        res = self._check("--lane", "policy")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("src/checkout/cart.py", res.stdout)

    def test_a_policy_change_under_an_ordinary_lane_fails(self):
        self._commit(".lanekeeper/config.yaml", "project:\n  name: p\nlanes:\n  "
                     "checkout:\n    allow: ['**']\n")
        res = self._check("--lane", "checkout")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("defines the lanes", res.stdout)

    def test_policy_cannot_be_declared_as_a_lane(self):
        cfg_dir = self.tmp / ".lanekeeper"
        (cfg_dir / "config.yaml").write_text(
            yaml.safe_dump({"lanes": {"policy": {"allow": ["**"]}}}), encoding="utf-8")
        with self.assertRaises(InvalidLaneError):
            load_config(self.tmp)


class TestTheWorkflow(CheckoutTestCase):
    def test_write_workflow_writes_a_valid_workflow_once(self):
        res = run_cli(["check", "--write-workflow"], cwd=self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        path = self.tmp / check.WORKFLOW_PATH
        self.assertTrue(path.exists())
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        # YAML reads a bare `on` as boolean True; either spelling means the trigger key.
        self.assertIn("pull_request", doc.get("on", doc.get(True)))
        steps = doc["jobs"]["lane"]["steps"]
        self.assertTrue(any("lanekeeper check" in (s.get("run") or "") for s in steps))
        self.assertTrue(any("fetch-depth" in str(s.get("with", "")) for s in steps),
                        "the merge base needs history")

        again = run_cli(["check", "--write-workflow"], cwd=self.tmp)
        self.assertEqual(again.returncode, 0, output_of(again))
        self.assertIn("already exists", again.stdout)

    def test_the_workflow_reads_the_lane_from_labels_and_fails_without_one(self):
        text = check.workflow_text()
        self.assertIn("--labels-json", text)
        self.assertIn("labels.*.name", text)


if __name__ == "__main__":
    unittest.main()
