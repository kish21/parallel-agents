"""The gate, as the deep-test run found it against published 0.7.12.

The verdict was never wrong. What was wrong is everything around it: it never said
which checkout it inspected (#77), it trusted a hand-typed label when the branch name
already carried the lane (#72), its one line of product was behind a click on the
pull-request page (#79), a legitimate file it blocked left the person hand-editing YAML
(#62), and a tracked build artifact tripped every lane forever (#63).

None of these change a verdict. The existing pass/fail tests are untouched.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper import check
from lanekeeper.config import Config, InvalidLaneError, LaneConfig, load_config, save_config
from lanekeeper.lanes import LaneEngine, LaneValidationResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import cli_env, output_of, run_cli  # noqa: E402


class CheckoutTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._git("init", "-q", "-b", "main", ".")
        self._git("config", "user.email", "t@t.c")
        self._git("config", "user.name", "t")
        for rel in ["src/checkout/cart.py", "src/catalog/list.py", "tests/unit/cart_test.py",
                    "tsconfig.tsbuildinfo", "lib/store.py"]:
            f = self.tmp / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("original\n", encoding="utf-8")
        cfg = Config.default("proj")
        cfg.lanes = {
            "feat-02": LaneConfig(name="feat-02", allow=["src/checkout/**"], deny=[]),
            "catalog": LaneConfig(name="catalog", allow=["src/catalog/**"], deny=[]),
            "store": LaneConfig(name="store", allow=["lib/store.py"], shared=True),
        }
        cfg.capability_gates = {}
        save_config(cfg, self.tmp)
        self._git("add", "-A")
        self._git("commit", "-qm", "init")

    def _git(self, *args, cwd=None):
        return subprocess.run(["git", *args], cwd=cwd or self.tmp, check=True,
                              capture_output=True)

    def _commit(self, rel, text="changed\n", cwd=None):
        f = (cwd or self.tmp) / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(text, encoding="utf-8")
        self._git("add", "-A", cwd=cwd)
        self._git("commit", "-qm", f"touch {rel}", cwd=cwd)

    def _branch(self, name):
        self._git("checkout", "-qb", name)

    def _check(self, *args, cwd=None):
        return run_cli(["check", "--base", "main", *args], cwd=cwd or self.tmp)


# --- #77: where did it run -------------------------------------------------------


class TestTheReportSaysWhereItRan(CheckoutTestCase):
    def test_the_main_checkout_is_named_on_pass_and_on_fail(self):
        self._branch("feature")
        self._commit("src/checkout/cart.py")
        res = self._check("--lane", "feat-02")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("the main checkout", res.stdout)
        self.assertIn(str(self.tmp.resolve().name), res.stdout)
        self._commit("src/catalog/list.py")
        res = self._check("--lane", "feat-02")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("the main checkout", res.stdout)

    def _worktree(self, agent="agent-001", lane="feat-02"):
        wt = self.tmp / ".lanekeeper" / "worktrees" / agent
        wt.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "-q", "-b", f"parallel/{agent}/2-{lane}-x", str(wt))
        (wt / ".lane").write_text(f"LANE='{lane}'\nAGENT_ID='{agent}'\n", encoding="utf-8")
        return wt

    def test_a_worktree_is_named_with_its_agent(self):
        wt = self._worktree()
        self._commit("src/checkout/cart.py", cwd=wt)
        res = self._check("--lane", "feat-02", cwd=wt)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("agent-001's worktree, lane 'feat-02'", res.stdout)

    def test_a_worktree_asked_about_another_lane_says_so_above_the_verdict(self):
        wt = self._worktree()
        self._commit("src/checkout/cart.py", cwd=wt)
        res = self._check("--lane", "catalog", cwd=wt)
        self.assertEqual(res.returncode, 2, "the verdict is unchanged\n" + output_of(res))
        self.assertIn("This worktree's .lane says 'feat-02'", res.stdout)
        self.assertIn("--lane feat-02", res.stdout)
        self.assertLess(res.stdout.index(".lane says"), res.stdout.index("CHECK FAILED"))

    def test_the_main_checkout_names_the_worktrees_that_exist(self):
        self._worktree()
        self._branch("feature")
        self._commit("src/catalog/list.py")
        res = self._check("--lane", "feat-02")
        self.assertIn("Agent worktrees exist: agent-001", res.stdout)
        self.assertIn("run this from inside its worktree", res.stdout)

    def test_the_lane_file_is_read_unquoted(self):
        p = self.tmp / ".lane"
        p.write_text("LANE='feat-02'\nAGENT_ID='agent-007'\nTASK='it'\"'\"'s fine'\n",
                     encoding="utf-8")
        values = check.read_lane_file(p)
        self.assertEqual(values["LANE"], "feat-02")
        self.assertEqual(values["AGENT_ID"], "agent-007")
        self.assertEqual(values["TASK"], "it's fine")
        self.assertEqual(check.read_lane_file(self.tmp / "nope"), {})


# --- #72: the lane the branch already knows --------------------------------------


class TestTheLaneFromTheBranch(unittest.TestCase):
    lanes = ["feat-02", "feat", "catalog", "issue-13"]

    def test_a_lanekeeper_branch_yields_its_lane(self):
        self.assertEqual(check.lane_from_branch(
            "parallel/agent-001/2-feat-02-automated-semantic-clustering", self.lanes), "feat-02")
        self.assertEqual(check.lane_from_branch(
            "refs/heads/parallel/agent-003/2-feat-02-x", self.lanes), "feat-02")
        self.assertEqual(check.lane_from_branch(
            "parallel/agent-002/13-search-box", self.lanes), "issue-13")

    def test_the_longer_lane_name_wins_over_its_prefix(self):
        self.assertEqual(check.lane_from_branch("parallel/agent-001/2-feat-02-x", self.lanes),
                         "feat-02")
        self.assertEqual(check.lane_from_branch("parallel/agent-001/2-feat-x", self.lanes),
                         "feat")

    def test_any_other_shape_yields_nothing(self):
        for branch in ("main", "my-test", "feature/feat-02", "parallel/agent-001/t",
                       "parallel/agent-001/feat-02-no-number", "parallel/agent-001/2-nope-x",
                       ""):
            self.assertEqual(check.lane_from_branch(branch, self.lanes), "", branch)

    def test_a_custom_prefix(self):
        self.assertEqual(check.lane_from_branch("lk/agent-001/2-feat-02-x", self.lanes,
                                                prefix="lk/"), "feat-02")


class TestPrecedence(unittest.TestCase):
    lanes = ["feat-02", "catalog"]
    branch = "parallel/agent-001/2-feat-02-x"

    def resolve(self, **kw):
        base = dict(lanes=self.lanes, branch=self.branch, from_branch=True)
        base.update(kw)
        return check.resolve_lane(**base)

    def test_label_present_label_wins(self):
        self.assertEqual(self.resolve(labels_json='["lane: feat-02"]'), "feat-02")

    def test_label_absent_branch(self):
        self.assertEqual(self.resolve(labels_json='["bug"]'), "feat-02")
        self.assertEqual(self.resolve(labels_json=None), "feat-02")

    def test_both_present_and_different_fails_naming_both(self):
        with self.assertRaises(check.NoLaneError) as ctx:
            self.resolve(labels_json='["lane: catalog"]')
        self.assertIn("'catalog'", str(ctx.exception))
        self.assertIn("'feat-02'", str(ctx.exception))

    def test_explicit_lane_wins_over_everything(self):
        self.assertEqual(self.resolve(explicit="catalog", labels_json='["lane: feat-02"]'),
                         "catalog")

    def test_without_the_flag_the_branch_is_only_a_hint(self):
        with self.assertRaises(check.NoLaneError) as ctx:
            self.resolve(labels_json='[]', from_branch=False)
        self.assertIn("looks like lane 'feat-02'", str(ctx.exception))
        self.assertIn("--lane-from-branch", str(ctx.exception))

    def test_a_hand_made_branch_keeps_the_old_refusal(self):
        with self.assertRaises(check.NoLaneError) as ctx:
            self.resolve(labels_json='[]', branch="my-test")
        self.assertIn("no 'lane: <name>' label", str(ctx.exception))
        self.assertNotIn("looks like", str(ctx.exception))

    def test_two_labels_still_fail_whatever_the_branch_says(self):
        with self.assertRaises(check.NoLaneError) as ctx:
            self.resolve(labels_json='["lane: feat-02", "lane: catalog"]')
        self.assertIn("2 lane labels", str(ctx.exception))


class TestTheBranchFlagOnTheCommandLine(CheckoutTestCase):
    def test_the_lane_is_read_from_the_branch_the_person_is_on(self):
        self._branch("parallel/agent-001/2-feat-02-cart")
        self._commit("src/checkout/cart.py")
        res = self._check("--lane-from-branch")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("lane 'feat-02'", res.stdout)

    def test_the_branch_can_be_named_as_ci_does_on_a_detached_head(self):
        self._branch("feature")
        self._commit("src/checkout/cart.py")
        res = self._check("--lane-from-branch", "--branch", "parallel/agent-001/2-feat-02-cart",
                          "--labels-json", "[]")
        self.assertEqual(res.returncode, 0, output_of(res))

    def test_the_no_label_refusal_names_the_candidate(self):
        self._branch("parallel/agent-001/2-feat-02-cart")
        self._commit("src/checkout/cart.py")
        res = self._check("--labels-json", "[]")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("looks like lane 'feat-02'", res.stderr)

    def test_a_mislabelled_pull_request_fails(self):
        self._branch("parallel/agent-001/2-feat-02-cart")
        self._commit("src/checkout/cart.py")
        res = self._check("--labels-json", '["lane: catalog"]', "--lane-from-branch")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("'catalog'", res.stderr)
        self.assertIn("'feat-02'", res.stderr)

    def test_the_workflow_passes_the_head_ref(self):
        text = check.workflow_text()
        self.assertIn("github.head_ref", text)
        self.assertIn("--lane-from-branch", text)
        self.assertIn("--github", text)
        doc = yaml.safe_load(text)
        steps = doc["jobs"]["lane"]["steps"]
        self.assertTrue(any("HEAD_REF" in str(s.get("env", "")) for s in steps))


# --- #79: the verdict on the pull-request page -----------------------------------


class TestTheGitHubSummary(CheckoutTestCase):
    def test_pass_and_fail_both_write_the_summary(self):
        self._branch("feature")
        self._commit("src/checkout/cart.py")
        summary = self.tmp / "summary.md"
        env = cli_env()
        env["GITHUB_STEP_SUMMARY"] = str(summary)

        def run(*args):
            return subprocess.run([sys.executable, "-m", "lanekeeper.cli", "check", "--base",
                                   "main", "--lane", "feat-02", "--github", *args],
                                  cwd=str(self.tmp), capture_output=True, text=True,
                                  encoding="utf-8", errors="replace", env=env)

        res = run()
        self.assertEqual(res.returncode, 0, output_of(res))
        text = summary.read_text(encoding="utf-8")
        self.assertIn("Passed", text)
        self.assertIn("1 changed file stays", text)
        self._commit("README.md")
        res = run()
        self.assertEqual(res.returncode, 2, output_of(res))
        text = summary.read_text(encoding="utf-8")
        self.assertIn("Failed", text)
        self.assertIn("README.md: outside lane 'feat-02'", text)
        # The annotation reaches the Files tab through stdout, against the file.
        self.assertIn("::error file=README.md", res.stdout)

    def test_without_the_flag_local_output_carries_none_of_it(self):
        self._branch("feature")
        self._commit("README.md")
        env = cli_env()
        env["GITHUB_STEP_SUMMARY"] = str(self.tmp / "summary.md")
        res = subprocess.run([sys.executable, "-m", "lanekeeper.cli", "check", "--base",
                              "main", "--lane", "feat-02"],
                             cwd=str(self.tmp), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertNotIn("::error", res.stdout)
        self.assertFalse((self.tmp / "summary.md").exists())

    def test_annotations_only_for_violations_that_name_a_file(self):
        report = check.CheckReport(
            lane="l", base="b", head="h",
            result=LaneValidationResult(lane_name="l", is_valid=False),
            errors=["Could not read the change, so nothing was checked: boom",
                    "src/a.py: outside lane 'l'.\n      If this file belongs: x"])
        lines = check.annotations(report)
        self.assertEqual(len(lines), 1)
        self.assertTrue(lines[0].startswith("::error file=src/a.py,"))
        self.assertNotIn("\n", lines[0])


# --- #62: the file the gate blocked ----------------------------------------------


class TestAllow(CheckoutTestCase):
    def test_the_whole_loop_gate_fails_allow_gate_passes(self):
        self._branch("parallel/agent-001/2-feat-02-cart")
        self._commit("tests/unit/cart_test.py")
        res = self._check("--lane", "feat-02")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("lanekeeper allow --lane feat-02 tests/unit/cart_test.py", res.stdout)

        res = run_cli(["allow", "--lane", "feat-02", "tests/unit/cart_test.py"], cwd=self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("now allowed in lane 'feat-02'", res.stdout)
        self.assertIn("commit it", res.stdout)
        self.assertEqual(load_config(self.tmp).lanes["feat-02"].allow,
                         ["src/checkout/**", "tests/unit/cart_test.py"])

        res = self._check("--lane", "feat-02")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("CHECK PASSED", res.stdout)

    def test_it_is_idempotent(self):
        first = run_cli(["allow", "--lane", "feat-02", "tests/unit/cart_test.py"], cwd=self.tmp)
        second = run_cli(["allow", "--lane", "feat-02", "tests/unit/cart_test.py"], cwd=self.tmp)
        self.assertEqual(second.returncode, 0, output_of(second))
        self.assertIn("already allowed", second.stdout)
        self.assertEqual(load_config(self.tmp).lanes["feat-02"].allow.count(
            "tests/unit/cart_test.py"), 1)
        del first

    def test_a_path_another_lane_claims_is_refused_and_nothing_changes(self):
        before = (self.tmp / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8")
        res = run_cli(["allow", "--lane", "feat-02", "src/catalog/list.py"], cwd=self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("lane 'catalog' already claims it", res.stderr)
        self.assertIn("Nothing was changed", res.stderr)
        self.assertEqual((self.tmp / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8"),
                         before)

    def test_policy_paths_and_shared_zones_are_refused(self):
        res = run_cli(["allow", "--lane", "feat-02", ".lanekeeper/config.yaml"], cwd=self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("policy file", res.stderr)
        res = run_cli(["allow", "--lane", "feat-02", "lib/store.py"], cwd=self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("shared zone 'store'", res.stderr)
        res = run_cli(["allow", "--lane", "store", "src/x.py"], cwd=self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("shared zone", res.stderr)

    def test_inside_a_worktree_the_lane_is_the_worktrees_own(self):
        wt = self.tmp / ".lanekeeper" / "worktrees" / "agent-001"
        wt.parent.mkdir(parents=True, exist_ok=True)
        self._git("worktree", "add", "-q", "-b", "parallel/agent-001/2-feat-02-x", str(wt))
        (wt / ".lane").write_text("LANE='feat-02'\nAGENT_ID='agent-001'\n", encoding="utf-8")
        res = run_cli(["allow", "tests/unit/cart_test.py"], cwd=wt)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("tests/unit/cart_test.py",
                      load_config(self.tmp).lanes["feat-02"].allow)
        # Written to the main checkout: the worktree's committed copy is untouched.
        self.assertNotIn("cart_test", (wt / ".lanekeeper" / "config.yaml").read_text(
            encoding="utf-8"))
        self.assertIn("cart_test", (self.tmp / ".lanekeeper" / "config.yaml").read_text(
            encoding="utf-8"))

    def test_with_no_lane_anywhere_it_asks(self):
        res = run_cli(["allow", "tests/unit/cart_test.py"], cwd=self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("--lane", res.stderr)

    def test_validate_offers_the_command_too(self):
        res = run_cli(["spawn", "--lane", "feat-02", "--task", "t"], cwd=self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        wt = self.tmp / ".lanekeeper" / "worktrees" / "agent-001"
        (wt / "tests" / "unit").mkdir(parents=True, exist_ok=True)
        (wt / "tests" / "unit" / "cart_test.py").write_text("new\n", encoding="utf-8")
        res = run_cli(["validate", "agent-001"], cwd=self.tmp)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("lanekeeper allow --lane feat-02 tests/unit/cart_test.py", res.stdout)


# --- #63: the tracked build artifact ---------------------------------------------


class TestGeneratedFiles(CheckoutTestCase):
    def test_by_default_it_trips_every_lane(self):
        self._branch("feature")
        self._commit("src/checkout/cart.py")
        self._commit("tsconfig.tsbuildinfo", "rebuilt\n")
        res = self._check("--lane", "feat-02")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("tsconfig.tsbuildinfo", res.stdout)

    def _declare(self, patterns):
        cfg = load_config(self.tmp)
        cfg.generated = list(patterns)
        save_config(cfg, self.tmp)
        self._git("add", "-A")
        self._git("commit", "-qm", "declare generated files")

    def test_declared_it_is_left_out_and_said_so(self):
        self._declare(["*.tsbuildinfo"])
        self._branch("feature")
        self._commit("src/checkout/cart.py")
        self._commit("tsconfig.tsbuildinfo", "rebuilt\n")
        res = self._check("--lane", "feat-02")
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("1 generated file(s) left out", res.stdout)
        self.assertIn("tsconfig.tsbuildinfo", res.stdout)
        self.assertIn("CHECK PASSED", res.stdout)

    def test_validate_and_diff_leave_it_out_too(self):
        self._declare(["*.tsbuildinfo"])
        res = run_cli(["spawn", "--lane", "feat-02", "--task", "t"], cwd=self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        wt = self.tmp / ".lanekeeper" / "worktrees" / "agent-001"
        (wt / "tsconfig.tsbuildinfo").write_text("rebuilt\n", encoding="utf-8")
        (wt / "src" / "checkout" / "cart.py").write_text("new\n", encoding="utf-8")
        res = run_cli(["validate", "agent-001"], cwd=self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        res = run_cli(["diff", "agent-001"], cwd=self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Total Modified Files: 1", res.stdout)
        self.assertIn("left out", res.stdout)

    def test_an_agent_cannot_declare_one_from_inside_its_lane(self):
        """The list lives in the policy, which no lane may edit."""
        self._branch("parallel/agent-001/2-feat-02-cart")
        self._commit("tsconfig.tsbuildinfo", "rebuilt\n")
        cfg = load_config(self.tmp)
        cfg.generated = ["*.tsbuildinfo"]
        save_config(cfg, self.tmp)
        self._git("add", "-A")
        self._git("commit", "-qm", "sneak the artifact past the gate")
        res = self._check("--lane", "feat-02")
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn(".lanekeeper/config.yaml: this file defines the lanes", res.stdout)

    def test_the_policy_can_never_be_declared_generated(self):
        lane = LaneConfig("l", allow=["**"])
        result = LaneEngine.validate_files([".lanekeeper/config.yaml"], lane,
                                           generated=[".lanekeeper/**", "**"])
        self.assertFalse(result.is_valid)
        self.assertEqual(result.violations[0].reason, "policy")

    def test_the_default_is_empty_and_a_bad_value_is_refused(self):
        self.assertEqual(Config.default("p").generated, [])
        self.assertEqual(Config.from_dict({}).generated, [])
        with self.assertRaises(InvalidLaneError):
            Config.from_dict({"generated": "*.tsbuildinfo"})
        self.assertEqual(Config.from_dict({"generated": ["a", None, " b "]}).generated,
                         ["a", "b"])

    def test_it_round_trips_and_is_absent_when_empty(self):
        cfg = Config.default("p")
        self.assertNotIn("generated", cfg.to_dict())
        cfg.generated = ["*.tsbuildinfo"]
        self.assertEqual(Config.from_dict(cfg.to_dict()).generated, ["*.tsbuildinfo"])


if __name__ == "__main__":
    unittest.main()
