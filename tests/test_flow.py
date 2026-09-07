"""The steps around `spawn --ticket`, done rather than described (0.9.0).

After the second deep-test run, every remaining piece of friction was the same shape:
the tool knew the next step and printed it for the person to do by hand. `next`, `pr`,
`work`, the pre-push hook, the gate offer, proposing files for a nameless ticket without
a second run, and a first project that gets no seat cards it did not ask for.
"""

import argparse
import contextlib
import io
import os
import shlex
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import cli
from lanekeeper import flow
from lanekeeper.config import Config, LaneConfig, load_config, save_config
from lanekeeper.state import AgentState, StateManager
from lanekeeper.trackers.base import TrackedIssue
from lanekeeper.trackers.github_issues import CommandResult
from lanekeeper.worktree import WorktreeManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import cli_env, output_of, run_cli  # noqa: E402
from _intake_fakes import FakeTracker  # noqa: E402


def _git(cwd, *args):
    return subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


class RepoWithRemote(unittest.TestCase):
    def setUp(self):
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, ignore_errors=True)
        self.origin = base / "origin.git"
        _git(base, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.root = base / "clone"
        self.root.mkdir()
        _git(self.root, "init", "-q", "-b", "main", ".")
        _git(self.root, "config", "user.email", "t@t.c")
        _git(self.root, "config", "user.name", "t")
        _git(self.root, "remote", "add", "origin", str(self.origin))
        (self.root / "src").mkdir()
        (self.root / "src" / "a.py").write_text("x\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")
        _git(self.root, "push", "-q", "-u", "origin", "main")
        self.mgr = WorktreeManager(self.root)
        os.environ["LANEKEEPER_INVOCATION"] = "lanekeeper"
        self.addCleanup(os.environ.pop, "LANEKEEPER_INVOCATION", None)

    def policy(self, commit=True):
        cfg = Config.default("p")
        cfg.capability_gates = {}
        cfg.lanes = {"feat-02": LaneConfig("feat-02", allow=["src/**"])}
        save_config(cfg, self.root)
        cli.ensure_gitignore(self.root)
        if commit:
            _git(self.root, "add", "-A")
            _git(self.root, "commit", "-qm", "policy")
        return cfg

    def spawn(self):
        res = run_cli(["spawn", "--lane", "feat-02", "--task", "#2 [FEAT-02] Thing"],
                      cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        return self.root / ".lanekeeper" / "worktrees" / "agent-001"

    def commit_in(self, wt, name="work.py"):
        (wt / "src" / name).write_text("new\n", encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-qm", "work")


# --- next --------------------------------------------------------------------------


class TestNext(RepoWithRemote):
    def test_before_anything_it_says_spawn(self):
        res = run_cli(["next"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("spawn --ticket", res.stdout)

    def test_the_policy_comes_first_then_the_gate(self):
        self.policy(commit=False)
        res = run_cli(["next"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("▶ Next:", res.stdout)
        self.assertLess(res.stdout.index("Commit the policy"), res.stdout.index("install-gate"))
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "policy")
        res = run_cli(["next"], cwd=self.root)
        self.assertNotIn("Commit the policy", res.stdout)
        self.assertIn("lanekeeper install-gate", res.stdout)

    def test_an_uncommitted_gate_workflow_is_the_next_thing(self):
        self.policy()
        run_cli(["install-gate"], cwd=self.root)
        res = run_cli(["next"], cwd=self.root)
        self.assertIn("Commit the gate workflow", res.stdout)

    def test_it_follows_an_agent_through_its_life(self):
        self.policy()
        run_cli(["install-gate"], cwd=self.root)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "gate")
        wt = self.spawn()
        res = run_cli(["next"], cwd=self.root)
        self.assertIn("agent-001 has not started", res.stdout)
        self.assertIn("lanekeeper work agent-001 -- claude", res.stdout)
        (wt / "src" / "b.py").write_text("y\n", encoding="utf-8")
        res = run_cli(["next"], cwd=self.root)
        self.assertIn("uncommitted work", res.stdout)
        self.assertIn("check --lane feat-02", res.stdout)
        self.commit_in(wt)
        res = run_cli(["next"], cwd=self.root)
        self.assertIn("not yet on the remote", res.stdout)
        self.assertIn("lanekeeper pr agent-001", res.stdout)
        _git(wt, "push", "-q", "-u", "origin", "HEAD")
        res = run_cli(["next"], cwd=self.root)
        self.assertIn("branch is pushed", res.stdout)
        self.assertIn("lanekeeper cleanup agent-001", res.stdout)

    def test_all_clear_when_nothing_is_waiting(self):
        self.policy()
        run_cli(["install-gate"], cwd=self.root)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "gate")
        res = run_cli(["next"], cwd=self.root)
        self.assertIn("Nothing waiting on you", res.stdout)
        self.assertIn("spawn --ticket", res.stdout)


# --- pr ------------------------------------------------------------------------------


class FakeGh:
    def __init__(self, fail_create=False, exists=False):
        self.calls = []
        self.fail_create = fail_create
        self.exists = exists

    def __call__(self, argv):
        self.calls.append(list(argv))
        if argv[1:3] == ["label", "create"]:
            return CommandResult(0, "", "")
        if argv[1:3] == ["pr", "create"]:
            if self.exists:
                return CommandResult(1, "", "a pull request for branch already exists")
            if self.fail_create:
                return CommandResult(1, "", "gh: not logged in")
            return CommandResult(0, "https://github.com/o/r/pull/12\n", "")
        if argv[1:3] == ["pr", "edit"]:
            return CommandResult(0, "", "")
        return CommandResult(1, "", "unsupported")


class TestPr(RepoWithRemote):
    def _agent(self):
        wt = self.spawn()
        self.commit_in(wt)
        return StateManager(self.root).get_agent("agent-001")

    def test_it_pushes_and_opens_the_labelled_pull_request(self):
        self.policy()
        agent = self._agent()
        gh = FakeGh()
        out = flow.open_pull_request(agent, self.mgr, base="main", gh="gh", runner=gh)
        self.assertTrue(out.pushed)
        self.assertEqual(out.url, "https://github.com/o/r/pull/12")
        self.assertEqual(out.label, "lane: feat-02")
        self.assertIn(agent.branch, self.mgr.remote_branches(agent.branch).branches)
        create = next(c for c in gh.calls if c[1:3] == ["pr", "create"])
        self.assertIn("--label", create)
        self.assertEqual(create[create.index("--label") + 1], "lane: feat-02")
        self.assertEqual(create[create.index("--head") + 1], agent.branch)
        self.assertEqual(create[create.index("--base") + 1], "main")
        label = next(c for c in gh.calls if c[1:3] == ["label", "create"])
        self.assertEqual(label[3], "lane: feat-02")

    def test_without_gh_the_push_still_happens_and_the_rest_is_said(self):
        self.policy()
        agent = self._agent()
        out = flow.open_pull_request(agent, self.mgr, base="main", gh="gh-not-here-xyz",
                                     runner=None)
        self.assertTrue(out.pushed)
        self.assertEqual(out.url, "")
        self.assertTrue(out.manual, "the remaining steps are printed, not lost")
        self.assertIn("lane: feat-02", out.manual[0])

    def test_an_existing_pull_request_gets_the_label(self):
        self.policy()
        agent = self._agent()
        gh = FakeGh(exists=True)
        out = flow.open_pull_request(agent, self.mgr, base="main", gh="gh", runner=gh)
        self.assertTrue(out.pushed)
        self.assertTrue(any(c[1:3] == ["pr", "edit"] for c in gh.calls))
        self.assertIn("already exists", " ".join(out.lines))

    def test_the_command_refuses_to_push_a_red_change(self):
        self.policy()
        wt = self.spawn()
        (wt / "README.md").write_text("stray\n", encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-qm", "stray")
        res = run_cli(["pr", "agent-001"], cwd=self.root)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("README.md: outside lane", res.stdout)
        self.assertIn("Not pushed", res.stderr)
        agent = StateManager(self.root).get_agent("agent-001")
        self.assertNotIn(agent.branch, self.mgr.remote_branches(agent.branch).branches)

    def test_the_command_refuses_uncommitted_work(self):
        self.policy()
        wt = self.spawn()
        (wt / "src" / "b.py").write_text("y\n", encoding="utf-8")
        res = run_cli(["pr", "agent-001"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("uncommitted", res.stderr)


# --- work ----------------------------------------------------------------------------


class TestWork(RepoWithRemote):
    def test_the_prompt_carries_the_task_and_the_current_boundary(self):
        lane = LaneConfig("feat-02", allow=["src/a.py", "src/b.py"])
        agent = AgentState(id="agent-001", name="w", seat="JR1", lane="feat-02",
                           task="#2 [FEAT-02] Thing", branch="b", worktree_path="/w")
        prompt = flow.prompt_for(agent, lane)
        self.assertIn("#2 [FEAT-02] Thing", prompt)
        self.assertIn("src/a.py, src/b.py", prompt)
        self.assertIn("stop and say so", prompt)

    def test_the_prompt_is_appended_or_substituted(self):
        self.assertEqual(flow.command_with_prompt(["claude"], "P"), ["claude", "P"])
        self.assertEqual(flow.command_with_prompt(["cursor", "--prompt", "{prompt}"], "P"),
                         ["cursor", "--prompt", "P"])

    def test_the_command_runs_in_the_worktree_with_the_prompt(self):
        self.policy()
        wt = self.spawn()
        # A stand-in agent: records where it ran and what it was told.
        stub = self.root.parent / "agent-stub.py"
        # The stub writes UTF-8 explicitly: the prompt carries an em dash, and on
        # Windows the platform default is cp1252, which cannot encode it.
        stub.write_text("import os, sys, pathlib\n"
                        "pathlib.Path(sys.argv[1]).write_text(os.getcwd() + '\\n' + sys.argv[2],"
                        " encoding='utf-8')\n",
                        encoding="utf-8")
        record = self.root.parent / "record.txt"
        res = run_cli(["work", "agent-001", "--", sys.executable, str(stub), str(record)],
                      cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        cwd, prompt = record.read_text(encoding="utf-8").split("\n", 1)
        self.assertEqual(Path(cwd).resolve(), wt.resolve())
        self.assertIn("You may only create or modify these files: src/**", prompt)

    def test_print_only(self):
        self.policy()
        self.spawn()
        res = run_cli(["work", "agent-001", "--print"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("You may only create or modify", res.stdout)

    def test_a_missing_command_is_named(self):
        self.policy()
        self.spawn()
        res = run_cli(["work", "agent-001", "--", "no-such-agent-xyz"], cwd=self.root)
        self.assertEqual(res.returncode, 127, output_of(res))
        self.assertIn("not on PATH", res.stderr)


# --- the pre-push hook -----------------------------------------------------------------


class TestHook(RepoWithRemote):
    def test_install_writes_one_hook_in_the_common_dir(self):
        self.policy()
        res = run_cli(["install-gate", "--hooks"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        hook = self.root / ".git" / "hooks" / "pre-push"
        self.assertTrue(hook.exists())
        if os.name != "nt":
            # NTFS has no executable bit; Git for Windows runs hooks through sh
            # regardless, so only the POSIX platforms have anything to assert.
            self.assertTrue(hook.stat().st_mode & stat.S_IXUSR)
        text = hook.read_text(encoding="utf-8")
        self.assertIn("parallel/*", text)
        self.assertIn("--lane-from-branch", text)
        # The fallback is the installing interpreter by absolute path, spelled with
        # forward slashes so sh reads it the same on Windows (`python.exe` there).
        self.assertIn(shlex.quote(Path(sys.executable).as_posix()) + " -m lanekeeper", text)
        self.assertNotIn("\\", text)

    def test_somebody_elses_hook_is_left_alone_without_force(self):
        self.policy()
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-push").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        res = run_cli(["install-gate", "--hooks"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("left alone", res.stdout)
        self.assertEqual((hooks / "pre-push").read_text(encoding="utf-8"), "#!/bin/sh\necho mine\n")
        res = run_cli(["install-gate", "--hooks", "--force"], cwd=self.root)
        self.assertIn(flow.HOOK_MARK, (hooks / "pre-push").read_text(encoding="utf-8"))

    @unittest.skipIf(os.name == "nt", "the hook is a sh script")
    def test_the_hook_blocks_a_red_push_and_ignores_other_branches(self):
        self.policy()
        run_cli(["install-gate", "--hooks"], cwd=self.root)
        wt = self.spawn()
        (wt / "README.md").write_text("stray\n", encoding="utf-8")
        _git(wt, "add", "-A")
        _git(wt, "commit", "-qm", "stray")
        env = cli_env()
        env["PATH"] = str(Path(sys.executable).parent) + os.pathsep + env.get("PATH", "")
        push = subprocess.run(["git", "push", "-u", "origin", "HEAD"], cwd=str(wt),
                              capture_output=True, text=True, env=env)
        self.assertNotEqual(push.returncode, 0, push.stdout + push.stderr)
        self.assertIn("README.md", push.stdout + push.stderr)
        # A branch lanekeeper did not make is pushed untouched.
        _git(self.root, "checkout", "-qb", "my-own-branch")
        (self.root / "anything.txt").write_text("x\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "mine")
        push = subprocess.run(["git", "push", "-u", "origin", "HEAD"], cwd=str(self.root),
                              capture_output=True, text=True, env=env)
        self.assertEqual(push.returncode, 0, push.stdout + push.stderr)


# --- the first spawn: gate offered, no cards, files proposed -----------------------


class TestTheFirstSpawn(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True)
        (self.root / "src").mkdir()
        (self.root / "src" / "a.ts").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        self.issues = [TrackedIssue("2", "[FEAT-02] Thing", "## Allowed File Paths\n- src/a.ts\n"),
                       TrackedIssue("9", "Sticky header", "One sentence.")]
        cli.get_tracker = lambda settings, root: FakeTracker(self.issues)
        self.addCleanup(setattr, cli, "get_tracker", cli.get_tracker)
        os.environ["LANEKEEPER_INVOCATION"] = "lanekeeper"
        self.addCleanup(os.environ.pop, "LANEKEEPER_INVOCATION", None)

    def spawn(self, answers=(), **kw):
        args = argparse.Namespace(name=None, lane=None, ticket=None,
                                  task=cli.p_spawn_default_task(), seat=None, command=None,
                                  force=False, open=False, allow=None, propose=False,
                                  yes=False, accept_overlap=False, no_gate=False)
        for k, v in kw.items():
            setattr(args, k, v)
        answers = list(answers)
        original_input = __builtins__["input"] if isinstance(__builtins__, dict) \
            else __builtins__.input
        import builtins
        builtins.input = lambda prompt="": answers.pop(0) if answers else ""
        self.addCleanup(setattr, builtins, "input", original_input)
        out, err = io.StringIO(), io.StringIO()
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.cmd_spawn(args)
        finally:
            os.chdir(previous)
        return code, out.getvalue(), err.getvalue()

    def test_no_terminal_no_offer(self):
        code, out, err = self.spawn(ticket="2")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("Install the pull-request gate now", out)
        self.assertFalse((self.root / ".github").exists())
        self.assertIn("What now:    lanekeeper next", out)

    def test_on_a_terminal_the_gate_is_offered_and_yes_installs_it(self):
        original = cli._interactive
        cli._interactive = lambda: True
        self.addCleanup(setattr, cli, "_interactive", original)
        code, out, err = self.spawn(answers=["y"], ticket="2")
        self.assertEqual(code, 0, out + err)
        self.assertTrue((self.root / ".github" / "workflows" / "lanekeeper-gate.yml").exists())
        self.assertIn("commit it with the policy", out)

    def test_no_declines_and_no_gate_flag_never_asks(self):
        original = cli._interactive
        cli._interactive = lambda: True
        self.addCleanup(setattr, cli, "_interactive", original)
        code, out, err = self.spawn(answers=["n"], ticket="2")
        self.assertEqual(code, 0, out + err)
        self.assertFalse((self.root / ".github").exists())
        code, out, err = self.spawn(ticket="2", force=True, no_gate=True, answers=["y"])
        self.assertNotIn("Install the pull-request gate now", out)

    def test_a_fresh_project_gets_no_gates_and_no_cards(self):
        code, out, err = self.spawn(ticket="2")
        self.assertEqual(code, 0, out + err)
        cfg = load_config(self.root)
        self.assertEqual(cfg.capability_gates, {})
        self.assertFalse((self.root / ".lanekeeper" / "capabilities").exists())
        text = (self.root / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8")
        self.assertNotIn("capability_gates", text)
        # validate and doctor still work without a card in sight.
        res = run_cli(["validate", "agent-001"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        res = run_cli(["doctor"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))

    def test_a_nameless_ticket_is_proposed_at_once_on_a_terminal(self):
        from lanekeeper.divide import advisor as advisor_mod
        real = advisor_mod.ClaudeCodeAdvisor
        calls = []

        class Patched(real):
            def __init__(self, command, root, runner=None):
                def fake(argv):
                    calls.append(list(argv))
                    return CommandResult(0, '{"paths": ["src/**"]}', "")
                super().__init__(command, root, runner=fake)

            def check_available(self):
                return None

        advisor_mod.ClaudeCodeAdvisor = Patched
        self.addCleanup(setattr, advisor_mod, "ClaudeCodeAdvisor", real)
        original = cli._interactive
        cli._interactive = lambda: True
        self.addCleanup(setattr, cli, "_interactive", original)
        real_which = cli.shutil.which
        cli.shutil.which = lambda cmd: "/usr/bin/claude" if cmd == "claude" else real_which(cmd)
        self.addCleanup(setattr, cli.shutil, "which", real_which)
        # No --propose: the tool asks the advisor itself, then asks the person.
        code, out, err = self.spawn(answers=["y", "n"], ticket="9")
        self.assertEqual(code, 0, out + err)
        self.assertIn("names no files. Asking Claude Code", out)
        self.assertEqual(len(calls), 1)
        self.assertEqual(load_config(self.root).lanes["issue-9"].allow, ["src/**"])
        self.assertEqual(load_config(self.root).lanes["issue-9"].paths_from, "proposed")

    def test_without_a_terminal_a_nameless_ticket_is_still_refused(self):
        code, out, err = self.spawn(ticket="9")
        self.assertEqual(code, 1)
        self.assertIn("names no files", err)
        self.assertIn("--propose", err)


if __name__ == "__main__":
    unittest.main()


class TestTheReviewFindings(RepoWithRemote):
    """What the code review of 0.9.0 found, each reproduced before it was fixed."""

    def test_the_hook_is_written_with_lf_and_the_installing_interpreter(self):
        self.policy()
        run_cli(["install-gate", "--hooks"], cwd=self.root)
        raw = (self.root / ".git" / "hooks" / "pre-push").read_bytes()
        self.assertNotIn(b"\r\n", raw)
        text = raw.decode("utf-8")
        self.assertIn(sys.executable.split("/")[-1].split("\\")[-1], text)
        self.assertIn("symbolic-ref -q --short refs/remotes/origin/HEAD", text)
        self.assertNotIn("\n  python -m lanekeeper", text)

    def test_a_hook_is_refused_when_there_is_no_base_to_compare_against(self):
        with self.assertRaises(flow.HookNotInstalled):
            flow.install_hook(self.root, self.mgr, "parallel/", "HEAD")

    def test_print_after_the_separator_belongs_to_the_agent(self):
        self.policy()
        self.spawn()
        stub = self.root.parent / "agent-stub.py"
        stub.write_text("import sys, pathlib\n"
                        "pathlib.Path(sys.argv[1]).write_text(' '.join(sys.argv[2:]),"
                        " encoding='utf-8')\n",
                        encoding="utf-8")
        record = self.root.parent / "record.txt"
        res = run_cli(["work", "agent-001", "--", sys.executable, str(stub), str(record),
                       "--print"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("--print", record.read_text(encoding="utf-8"), "claude's own flag")
        res = run_cli(["work", "agent-001", "--print", "--", "no-such-agent-xyz"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("You may only create or modify", res.stdout)

    def test_next_pr_and_work_answer_from_inside_a_worktree(self):
        self.policy()
        run_cli(["install-gate"], cwd=self.root)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "gate")
        wt = self.spawn()
        self.commit_in(wt)
        res = run_cli(["next"], cwd=wt)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("lanekeeper pr agent-001", res.stdout)
        self.assertFalse((wt / ".lanekeeper" / "state").exists(), "no stray state directory")
        res = run_cli(["work", "agent-001", "--print"], cwd=wt)
        self.assertEqual(res.returncode, 0, output_of(res))
        res = run_cli(["pr", "agent-001", "--no-check"], cwd=wt)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("Pushed", res.stdout)

    def test_uninit_removes_the_hook_it_installed(self):
        self.policy()
        run_cli(["install-gate", "--hooks"], cwd=self.root)
        hook = self.root / ".git" / "hooks" / "pre-push"
        self.assertTrue(hook.exists())
        res = run_cli(["uninit", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("pre-push hook", res.stdout)
        self.assertFalse(hook.exists())

    def test_uninit_leaves_somebody_elses_hook(self):
        self.policy()
        hooks = self.root / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-push").write_text("#!/bin/sh\necho mine\n", encoding="utf-8")
        run_cli(["uninit", "--force"], cwd=self.root)
        self.assertTrue((hooks / "pre-push").exists())

    def test_a_gh_that_hangs_after_the_push_is_a_printed_step_not_a_traceback(self):
        self.policy()
        wt = self.spawn()
        self.commit_in(wt)
        agent = StateManager(self.root).get_agent("agent-001")

        def runner(argv):
            if argv[1:3] == ["label", "create"]:
                return CommandResult(0, "", "")
            raise subprocess.TimeoutExpired(argv, 120)

        out = flow.open_pull_request(agent, self.mgr, base="main", gh="gh", runner=runner)
        self.assertTrue(out.pushed)
        self.assertIn("Pushed", out.lines[0])
        self.assertTrue(out.manual)

    def test_the_prompt_is_the_same_wording_in_both_places(self):
        from lanekeeper import ticket as ticket_mod
        lane = LaneConfig("feat-02", allow=["src/a.py"])
        agent = AgentState(id="agent-001", name="w", seat="JR1", lane="feat-02",
                           task="#2 Thing", branch="b", worktree_path="/w")
        via_work = flow.prompt_for(agent, lane)
        via_spawn = ticket_mod.build_prompt("#2 Thing", ["src/a.py"])
        self.assertEqual(via_work, via_spawn)

    def test_the_most_urgent_agent_comes_first(self):
        self.policy()
        run_cli(["install-gate"], cwd=self.root)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "gate")
        self.spawn()   # agent-001: not started
        cfg = load_config(self.root)
        cfg.lanes["feat-03"] = LaneConfig("feat-03", allow=["lib/**"])
        save_config(cfg, self.root)
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "lane")
        res = run_cli(["spawn", "--lane", "feat-03", "--task", "t"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        wt2 = self.root / ".lanekeeper" / "worktrees" / "agent-002"
        (wt2 / "lib").mkdir()
        (wt2 / "lib" / "x.py").write_text("x\n", encoding="utf-8")
        _git(wt2, "add", "-A")
        _git(wt2, "commit", "-qm", "work")
        res = run_cli(["next"], cwd=self.root)
        first = res.stdout.split("Then:")[0]
        self.assertIn("lanekeeper pr agent-002", first)
        self.assertNotIn("agent-001", first)
