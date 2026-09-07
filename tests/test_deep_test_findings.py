"""What the owner hit running the deep-test protocol against published 0.7.12.

Nineteen issues came out of that run. The ones in this file are about what `spawn
--ticket` and `open` *say* — the editor window that had not opened (#67), the branch
the policy was to be committed on (#69), the dependencies a fresh worktree does not
have (#73), the command that does not resolve in the window `open` created (#76) — and
one about the core guarantee: the collision warning that arrived after the collision
had been written into the policy, and never named the remedy that already shipped (#80).
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

from lanekeeper import cli
from lanekeeper import deps
from lanekeeper import invocation as inv_mod
from lanekeeper import ticket as ticket_mod
from lanekeeper.config import Config, LaneConfig, load_config, save_config
from lanekeeper.trackers.base import TrackedIssue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import cli_env, output_of, run_cli  # noqa: E402
from _intake_fakes import FakeTracker  # noqa: E402


def _lane(**kw):
    fields = dict(name="feat-03", paths=("src/domain/contracts.ts", "src/export/**"),
                  source=ticket_mod.Source.TICKET,
                  issue=TrackedIssue("3", "[FEAT-03] Export profiles"))
    fields.update(kw)
    return ticket_mod.TicketLane(**fields)


@contextlib.contextmanager
def in_dir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class RepoTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True)
        for rel in ("src/domain/contracts.ts", "src/export/csv.ts", "src/cluster/svc.ts"):
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        self.issues = [
            TrackedIssue("3", "[FEAT-03] Export profiles",
                         "## Allowed File Paths\n- src/domain/contracts.ts\n- src/export/**\n"),
        ]
        self.original_tracker = cli.get_tracker
        cli.get_tracker = lambda settings, root: FakeTracker(self.issues)
        self.addCleanup(setattr, cli, "get_tracker", self.original_tracker)
        # The suite runs under a test runner, so what the process would print for
        # itself is the documented shim; say so explicitly rather than depend on it.
        os.environ["LANEKEEPER_INVOCATION"] = "lanekeeper"
        self.addCleanup(os.environ.pop, "LANEKEEPER_INVOCATION", None)

    def write_policy(self, lanes=None):
        cfg = Config.default("p")
        cfg.capability_gates = {}
        cfg.lanes = lanes or {}
        save_config(cfg, self.root)
        return cfg

    def spawn(self, **kw):
        args = argparse.Namespace(name=None, lane=None, ticket=None,
                                  task=cli.p_spawn_default_task(), seat=None, command=None,
                                  force=False, open=False, allow=None, propose=False,
                                  yes=False, accept_overlap=False, no_gate=True)
        for k, v in kw.items():
            setattr(args, k, v)
        out, err = io.StringIO(), io.StringIO()
        with in_dir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.cmd_spawn(args)
        return code, out.getvalue(), err.getvalue()


# --- #67: the editor window that had not opened ----------------------------------


class TestTheInstructionsDoNotMentionAWindowThatIsNotThere(unittest.TestCase):
    def test_without_open_it_points_at_the_open_command(self):
        text = ticket_mod.how_to_work(_lane(), Path("/r/.lanekeeper/worktrees/agent-001"),
                                      "agent-001", editor_opened=False)
        self.assertNotIn("window that just opened", text)
        self.assertIn("lanekeeper open agent-001", text)

    def test_with_open_it_keeps_the_window_wording(self):
        text = ticket_mod.how_to_work(_lane(), Path("/r/.lanekeeper/worktrees/agent-001"),
                                      "agent-001", editor_opened=True)
        self.assertIn("window that just opened", text)


# --- #69: "commit the policy here, on 'main'" ------------------------------------


class TestTheCommitAdviceNamesTheBranchYouAreOn(unittest.TestCase):
    def test_off_the_default_branch_it_names_that_branch(self):
        text = ticket_mod.commit_policy_advice(branch="my-test", protected=["main", "master"])
        self.assertIn("on 'my-test'", text)
        self.assertNotIn("on 'main'", text)
        self.assertIn("lane: policy", text)
        self.assertIn("in this checkout", text)

    def test_on_a_protected_branch_it_names_no_branch(self):
        for branch in ("main", "master", ""):
            text = ticket_mod.commit_policy_advice(branch=branch, protected=["main", "master"])
            self.assertNotIn(f"on '{branch}'", text, branch)
            self.assertIn("branch of its own", text)
            self.assertIn("lane: policy", text)

    def test_a_branch_the_configuration_protects_is_never_named(self):
        text = ticket_mod.commit_policy_advice(branch="release", protected=["release"])
        self.assertNotIn("on 'release'", text)

    def test_next_steps_threads_the_branch_through(self):
        text = ticket_mod.next_steps(_lane(policy_uncommitted=True), gate_workflow_exists=True,
                                     branch="feature/x", protected=["main"])
        self.assertIn("on 'feature/x'", text)
        self.assertLess(text.index("Commit the policy"), text.index("label it"))


class TestSpawnReadsTheRealBranch(RepoTestCase):
    def test_the_advice_names_the_branch_the_person_is_on(self):
        subprocess.run(["git", "checkout", "-q", "-b", "my-test"], cwd=self.root, check=True)
        self.write_policy()
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        self.assertIn("on 'my-test'", out)
        self.assertNotIn("on 'main'", out)


# --- #73: a fresh worktree has no dependencies -----------------------------------


class TestTheDependencyStep(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_a_lockfile_names_the_command(self):
        (self.root / "package-lock.json").write_text("{}", encoding="utf-8")
        step = deps.detect(self.root)
        self.assertEqual(step.command, "npm ci")
        for lockfile, command in (("pnpm-lock.yaml", "pnpm install --frozen-lockfile"),
                                  ("yarn.lock", "yarn install --immutable"),
                                  ("uv.lock", "uv sync"), ("poetry.lock", "poetry install")):
            root = Path(tempfile.mkdtemp())
            self.addCleanup(shutil.rmtree, root, ignore_errors=True)
            (root / lockfile).write_text("", encoding="utf-8")
            self.assertEqual(deps.detect(root).command, command, lockfile)

    def test_a_manifest_without_a_lockfile_makes_no_claim(self):
        (self.root / "package.json").write_text("{}", encoding="utf-8")
        step = deps.detect(self.root)
        self.assertIsNone(step.command)
        self.assertEqual(step.evidence, "package.json")
        self.assertIn("your call", step.line())

    def test_nothing_recognisable_gets_no_line(self):
        (self.root / "README.md").write_text("x", encoding="utf-8")
        self.assertIsNone(deps.detect(self.root))
        text = ticket_mod.how_to_work(_lane(), self.root / "wt", "agent-001",
                                      dependencies=None)
        self.assertNotIn("install", text.lower())

    def test_the_step_comes_before_starting_the_agent_and_says_once_per_worktree(self):
        step = deps.DependencyStep("package-lock.json", "npm ci")
        text = ticket_mod.how_to_work(_lane(), Path("/r/.lanekeeper/worktrees/agent-001"),
                                      "agent-001", dependencies=step)
        self.assertIn("npm ci", text)
        self.assertIn("Once per worktree", text)
        self.assertLess(text.index("npm ci"), text.index("coding agent"))
        self.assertTrue(text.index("1. Once per worktree") >= 0)


class TestSpawnAndOpenNameTheInstall(RepoTestCase):
    def test_spawn_names_it_for_a_project_with_a_lockfile(self):
        (self.root / "package-lock.json").write_text("{}", encoding="utf-8")
        self.write_policy()
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        self.assertIn("npm ci", out)

    def test_spawn_says_nothing_for_a_project_with_no_manifest(self):
        self.write_policy()
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("install the dependencies", out)

    def test_open_names_it_too(self):
        (self.root / "package-lock.json").write_text("{}", encoding="utf-8")
        self.write_policy()
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        env = cli_env()
        env["PATH"] = str(self.root) + os.pathsep + env.get("PATH", "")
        # An "editor" that does nothing, so the command reaches its notes.
        editor = self.root / ("true.cmd" if os.name == "nt" else "true-editor")
        editor.write_text("@echo off\n" if os.name == "nt" else "#!/bin/sh\nexit 0\n",
                          encoding="utf-8")
        editor.chmod(0o755)
        cfg = load_config(self.root)
        cfg.editor.command = editor.name if os.name != "nt" else "true"
        save_config(cfg, self.root)
        res = subprocess.run([sys.executable, "-m", "lanekeeper.cli", "open", "agent-001"],
                             cwd=str(self.root), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("npm ci", res.stdout)
        self.assertIn("python -m lanekeeper", res.stdout)


# --- #76: the command that does not resolve in the other window ------------------


class TestTheInvocationForm(unittest.TestCase):
    def setUp(self):
        os.environ.pop("LANEKEEPER_INVOCATION", None)

    def test_the_shim_prints_the_shim(self):
        self.assertEqual(inv_mod.invocation("/usr/local/bin/lanekeeper", env={}), "lanekeeper")
        self.assertEqual(inv_mod.invocation(r"C:\Users\k\Scripts\lanekeeper.exe", env={}),
                         "lanekeeper")

    def test_the_module_form_prints_the_module_form_with_the_interpreter_typed(self):
        self.assertEqual(
            inv_mod.invocation(r"C:\Python\Lib\site-packages\lanekeeper\cli.py",
                               orig_argv=["python", "-m", "lanekeeper.cli", "status"], env={}),
            "python -m lanekeeper")
        self.assertEqual(
            inv_mod.invocation("/x/lanekeeper/cli.py",
                               orig_argv=["python3", "-m", "lanekeeper.cli"], env={}),
            "python3 -m lanekeeper")
        self.assertEqual(
            inv_mod.invocation("/x/lanekeeper/cli.py",
                               orig_argv=["/venv/bin/python3.12", "-m", "lanekeeper.cli"],
                               env={}),
            "python3.12 -m lanekeeper")

    def test_an_explicit_override_wins(self):
        self.assertEqual(inv_mod.invocation("/x/lanekeeper/cli.py",
                                            env={"LANEKEEPER_INVOCATION": "lk"}), "lk")

    def test_the_fallback_line_only_when_the_shim_is_in_use(self):
        self.assertIn("python -m lanekeeper", inv_mod.fallback_line("lanekeeper"))
        self.assertEqual(inv_mod.fallback_line("python -m lanekeeper"), "")

    def test_every_run_this_next_line_uses_the_form_the_person_used(self):
        for form in ("lanekeeper", "python -m lanekeeper"):
            os.environ["LANEKEEPER_INVOCATION"] = form
            try:
                text = ticket_mod.how_to_work(_lane(), Path("/r/wt"), "agent-001")
                self.assertIn(f"{form} check --lane feat-03", text)
                self.assertIn(f"{form} open agent-001", text)
                steps = ticket_mod.next_steps(_lane(), gate_workflow_exists=False)
                self.assertIn(f"{form} install-gate", steps)
            finally:
                os.environ.pop("LANEKEEPER_INVOCATION", None)

    def test_the_hand_over_carries_the_fallback_and_ordinary_lines_do_not(self):
        os.environ["LANEKEEPER_INVOCATION"] = "lanekeeper"
        try:
            text = ticket_mod.how_to_work(_lane(), Path("/r/wt"), "agent-001")
            self.assertIn("'python -m lanekeeper' is the same program", text)
            steps = ticket_mod.next_steps(_lane(), gate_workflow_exists=False)
            self.assertNotIn("same program", steps)
        finally:
            os.environ.pop("LANEKEEPER_INVOCATION", None)


class TestTheSubprocessPrintsWhatItWasStartedAs(RepoTestCase):
    def test_started_with_dash_m_the_lines_say_dash_m(self):
        self.write_policy({"feat-03": LaneConfig("feat-03", allow=["src/export/**"])})
        env = cli_env()
        env.pop("LANEKEEPER_INVOCATION", None)
        res = subprocess.run([sys.executable, "-m", "lanekeeper.cli", "spawn", "--lane",
                              "feat-03", "--task", "t"],
                             cwd=str(self.root), capture_output=True, text=True,
                             encoding="utf-8", errors="replace", env=env)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("-m lanekeeper open agent-001", res.stdout)
        self.assertNotIn("To open:     lanekeeper open", res.stdout)
        self.assertNotIn("lanekeeper.cli open", res.stdout)


# --- #80: the collision warning ---------------------------------------------------


class TestTheOverlapIsReportedBeforeAnythingIsWritten(RepoTestCase):
    def setUp(self):
        super().setUp()
        self.write_policy({"feat-02": LaneConfig(
            "feat-02", allow=["src/domain/contracts.ts", "src/cluster/**"])})

    def test_the_report_says_what_the_gate_will_do_and_names_the_remedy(self):
        lane = _lane(collisions=[("feat-02", "src/domain/contracts.ts",
                                  "src/domain/contracts.ts")])
        text = ticket_mod.collision_report(lane)
        self.assertIn("Both lanes allow them", text)
        self.assertIn("pass their own checks", text)
        self.assertIn("shared: true", text)
        self.assertIn("- src/domain/contracts.ts", text)
        self.assertIn("Nothing has been written yet", text)
        self.assertNotIn("settle it first", text)

    def test_the_contested_zone_is_the_narrower_pattern(self):
        self.assertEqual(ticket_mod.contested_pattern("src/pages/**", "src/pages/checkout/**"),
                         "src/pages/checkout/**")
        self.assertEqual(ticket_mod.contested_pattern("src/a.ts", "src/a.ts"), "src/a.ts")

    def test_non_interactive_proceeds_with_the_warning_and_says_why(self):
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Another lane could touch the same files", out)
        self.assertIn("no terminal to ask on", out)
        self.assertIn("--accept-overlap", out)
        # Reported before the lane went in: the report precedes "Written into the policy".
        self.assertLess(out.index("Another lane could touch"), out.index("Written into the policy"))
        self.assertIn("feat-03", load_config(self.root).lanes)

    def test_the_flag_says_it_was_deliberate_and_asks_nothing(self):
        asked = []
        cli._ask_about_overlap = lambda: asked.append(1) or "p"
        self.addCleanup(setattr, cli, "_ask_about_overlap", cli._ask_about_overlap)
        code, out, err = self.spawn(ticket="3", accept_overlap=True)
        self.assertEqual(code, 0, out + err)
        self.assertIn("--accept-overlap says this overlap is deliberate", out)
        self.assertEqual(asked, [])

    def _interactive(self, answer):
        original_tty, original_ask = cli._interactive, cli._ask_about_overlap
        cli._interactive = lambda: True
        cli._ask_about_overlap = lambda: answer
        self.addCleanup(setattr, cli, "_interactive", original_tty)
        self.addCleanup(setattr, cli, "_ask_about_overlap", original_ask)

    def test_on_a_terminal_stopping_writes_nothing(self):
        self._interactive("n")
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 1, out + err)
        self.assertIn("Nothing was written", out)
        self.assertNotIn("feat-03", load_config(self.root).lanes)
        self.assertFalse((self.root / ".lanekeeper" / "worktrees" / "agent-001").exists())

    def test_on_a_terminal_proceeding_proceeds(self):
        self._interactive("p")
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        self.assertIn("feat-03", load_config(self.root).lanes)

    def test_on_a_terminal_sharing_writes_the_zone_and_the_gate_escalates_it(self):
        self._interactive("s")
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        cfg = load_config(self.root)
        zone = next(l for l in cfg.lanes.values() if l.shared)
        self.assertEqual(zone.allow, ["src/domain/contracts.ts"])
        self.assertIn("shared zone", out)
        from lanekeeper import check
        for lane in ("feat-02", "feat-03"):
            verdict = check.check_files(cfg, lane, ["src/domain/contracts.ts"])
            self.assertFalse(verdict.is_valid, lane)
            self.assertEqual(verdict.violations[0].reason, "shared", lane)
        # Settled, so the next ticket over the same file is not warned again.
        self.assertEqual(ticket_mod.collisions(cfg, "feat-04", ["src/domain/contracts.ts"]), [])

    def test_the_gates_verdicts_are_unchanged_by_the_report(self):
        code, out, err = self.spawn(ticket="3")
        self.assertEqual(code, 0, out + err)
        from lanekeeper import check
        cfg = load_config(self.root)
        self.assertTrue(check.check_files(cfg, "feat-03", ["src/export/csv.ts"]).is_valid)
        self.assertFalse(check.check_files(cfg, "feat-03", ["src/cluster/svc.ts"]).is_valid)


class TestMarkShared(unittest.TestCase):
    def test_an_existing_zone_is_extended_and_a_taken_name_is_not_hijacked(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, root, ignore_errors=True)
        cfg = Config.default("p")
        cfg.lanes = {"shared": LaneConfig("shared", allow=["lib/**"])}
        name = ticket_mod.mark_shared(cfg, root, ["src/a.ts"])
        self.assertEqual(name, "shared-zone")
        self.assertTrue(load_config(root).lanes["shared-zone"].shared)
        self.assertFalse(load_config(root).lanes["shared"].shared)
        again = ticket_mod.mark_shared(load_config(root), root, ["src/b.ts"])
        self.assertEqual(again, "shared-zone")
        self.assertEqual(load_config(root).lanes["shared-zone"].allow, ["src/a.ts", "src/b.ts"])


if __name__ == "__main__":
    unittest.main()


class TestASharedZoneSettlesOnlyWhatItCovers(unittest.TestCase):
    """The review's finding: a zone holding one file inside `src/domain/**` must not
    silence an overlap over the whole directory."""

    def test_covers(self):
        self.assertTrue(ticket_mod.covers("src/domain/contracts.ts", "src/domain/contracts.ts"))
        self.assertTrue(ticket_mod.covers("src/domain/**", "src/domain/contracts.ts"))
        self.assertTrue(ticket_mod.covers("src/**", "src/domain/**"))
        self.assertFalse(ticket_mod.covers("src/domain/contracts.ts", "src/domain/**"))
        self.assertFalse(ticket_mod.covers("src/other/**", "src/domain/**"))

    def test_a_narrow_zone_inside_a_wide_overlap_does_not_silence_it(self):
        cfg = Config.default("p")
        cfg.lanes = {
            "domain": LaneConfig("domain", allow=["src/domain/**"]),
            "zone": LaneConfig("zone", allow=["src/domain/contracts.ts"], shared=True),
        }
        found = ticket_mod.collisions(cfg, "feat-04", ["src/domain/**"])
        self.assertEqual(found, [("domain", "src/domain/**", "src/domain/**")])
        # But the file the zone holds is settled.
        self.assertEqual(ticket_mod.collisions(cfg, "feat-04", ["src/domain/contracts.ts"]), [])
