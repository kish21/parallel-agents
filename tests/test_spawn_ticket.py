"""`spawn --ticket N` with no board: the ticket itself is the boundary.

A person with a backlog already written hands one ticket to one agent. What is tested:
the lane is read from the ticket's file list and written into the policy under the
ticket's own name; a ticket with no files is refused unless the person supplies them;
a proposal is used only once accepted; a collision with an existing lane is reported
and not blocked on; the pull-request label the gate needs is named at the end.
"""

import argparse
import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper import cli
from lanekeeper import ticket as ticket_mod
from lanekeeper.capabilities import CapabilityRegistry, default_cards, save_card
from lanekeeper.config import Config, LaneConfig, load_config, save_config
from lanekeeper.divide.advisor import AdvisorError
from lanekeeper.trackers.github_issues import CommandResult, GitHubIssuesTracker
from lanekeeper.trackers.base import TrackedIssue
from lanekeeper.config import GitHubTrackerConfig

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _intake_fakes import FakeTracker  # noqa: E402

PLAYBOOK_BODY = """\
## 📁 Target Modules & Exact File Names

- [x] **Service:** `src/checkout/service.ts` *(the cart)*
- [x] **Page:** `src/pages/checkout/**`

---

## Notes
Keep it small.
"""


@contextlib.contextmanager
def in_dir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class TicketSpawnTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True)
        for rel in ("src/checkout/service.ts", "src/pages/checkout/index.tsx",
                    "src/search/index.ts"):
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        self.issues = [
            TrackedIssue("12", "[FEAT-02] Checkout cart", PLAYBOOK_BODY),
            TrackedIssue("13", "Search box", "Just a sentence, no files."),
        ]
        self.original_tracker = cli.get_tracker
        cli.get_tracker = lambda settings, root: FakeTracker(self.issues)
        self.addCleanup(setattr, cli, "get_tracker", self.original_tracker)

    def write_policy(self, lanes=None):
        cfg = Config.default("p")
        cfg.capability_gates = {}
        cfg.lanes = lanes or {}
        save_config(cfg, self.root)
        return cfg

    def spawn(self, **kw):
        args = argparse.Namespace(name=None, lane=None, ticket=None, task=cli.p_spawn_default_task(),
                                  seat=None, command=None, force=False, open=False,
                                  allow=None, propose=False, yes=False)
        for k, v in kw.items():
            setattr(args, k, v)
        out, err = io.StringIO(), io.StringIO()
        with in_dir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.cmd_spawn(args)
        return code, out.getvalue(), err.getvalue()

    def agents(self):
        f = self.root / ".lanekeeper" / "state" / "agents.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


class TestTheTicketIsTheBoundary(TicketSpawnTestCase):
    def test_the_lane_comes_from_the_tickets_file_list(self):
        self.write_policy()
        code, out, err = self.spawn(ticket="12")
        self.assertEqual(code, 0, out + err)
        cfg = load_config(self.root)
        self.assertEqual(cfg.lanes["feat-02"].allow,
                         ["src/checkout/service.ts", "src/pages/checkout/**"])
        self.assertIn("Lane:     feat-02", out)
        self.assertEqual(self.agents()["agent-001"]["task"], "#12 [FEAT-02] Checkout cart")
        lane_file = self.root / ".lanekeeper" / "worktrees" / "agent-001" / ".lane"
        self.assertIn("src/pages/checkout/**", lane_file.read_text(encoding="utf-8"))
        self.assertIn("label it 'lane: feat-02'", out)
        self.assertIn("lanekeeper install-gate", out)

    def test_a_ticket_without_a_tag_is_named_by_its_number(self):
        self.write_policy()
        code, out, err = self.spawn(ticket="13", allow=["src/search/**"])
        self.assertEqual(code, 0, out + err)
        self.assertIn("issue-13", load_config(self.root).lanes)

    def test_a_ticket_with_no_files_is_refused_with_the_fix(self):
        self.write_policy()
        code, out, err = self.spawn(ticket="13")
        self.assertEqual(code, 1)
        self.assertIn("names no files", err)
        self.assertIn("--allow", err)
        self.assertIn("--propose", err)
        self.assertEqual(self.agents(), {})
        self.assertNotIn("issue-13", load_config(self.root).lanes)

    def test_allow_overrides_the_ticket_and_accepts_commas(self):
        self.write_policy()
        code, out, err = self.spawn(ticket="12", allow=["src/search/**, src/checkout/**"])
        self.assertEqual(code, 0, out + err)
        self.assertEqual(load_config(self.root).lanes["feat-02"].allow,
                         ["src/search/**", "src/checkout/**"])
        self.assertIn("--allow", out)

    def test_an_unknown_ticket_is_refused(self):
        self.write_policy()
        code, out, err = self.spawn(ticket="#99")
        self.assertEqual(code, 1)
        self.assertIn("could not find ticket #99", err)

    def test_a_lane_already_in_the_policy_is_reused_not_rewritten(self):
        self.write_policy({"feat-02": LaneConfig("feat-02", allow=["src/checkout/**"])})
        code, out, err = self.spawn(ticket="12")
        self.assertEqual(code, 0, out + err)
        self.assertEqual(load_config(self.root).lanes["feat-02"].allow, ["src/checkout/**"])
        self.assertIn("already in the policy", out)

    def test_a_collision_with_another_lane_is_reported_and_not_blocked_on(self):
        self.write_policy({"pages": LaneConfig("pages", allow=["src/pages/**"])})
        code, out, err = self.spawn(ticket="12")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Another lane could touch the same files", out)
        self.assertIn("'pages' claims src/pages/**", out)

    def test_a_scoped_seat_card_is_let_into_the_new_lane(self):
        self.write_policy({"search": LaneConfig("search", allow=["src/search/**"])})
        for card in default_cards(["search"]):
            save_card(card, self.root)
        code, out, err = self.spawn(ticket="12", seat="SR1")
        self.assertEqual(code, 0, out + err)
        self.assertIn("feat-02", CapabilityRegistry.load(self.root).get("SR1").max_allowed_lane_scope)
        self.assertIn("now allow", out)

    def test_a_project_with_no_policy_yet_gets_one_with_only_this_lane(self):
        code, out, err = self.spawn(ticket="12")
        self.assertEqual(code, 0, out + err)
        cfg = load_config(self.root)
        self.assertEqual(list(cfg.lanes), ["feat-02"])
        self.assertTrue((self.root / ".lanekeeper" / "capabilities" / "JR1.json").exists())
        self.assertIn("first agent on this project", out)

    def test_the_gate_reads_the_same_boundary(self):
        """The whole point: the lane the agent got is the lane `check` enforces."""
        self.write_policy()
        code, out, err = self.spawn(ticket="12")
        self.assertEqual(code, 0, out + err)
        from lanekeeper import check
        cfg = load_config(self.root)
        inside = check.check_files(cfg, "feat-02", ["src/pages/checkout/cart.tsx"])
        outside = check.check_files(cfg, "feat-02", ["src/search/index.ts"])
        self.assertTrue(inside.is_valid)
        self.assertFalse(outside.is_valid)


class FakeClaude:
    """A `claude -p` that answers with a fixed list."""

    def __init__(self, answer):
        self.answer, self.calls = answer, []

    def __call__(self, argv):
        self.calls.append(list(argv))
        return CommandResult(0, self.answer, "")


class TestAProposalIsUsedOnlyWhenAccepted(TicketSpawnTestCase):
    def setUp(self):
        super().setUp()
        self.write_policy()
        self.claude = FakeClaude('{"paths": ["src/search/**", "not/in/repo.py"]}')
        original = cli.ClaudeCodeAdvisor if hasattr(cli, "ClaudeCodeAdvisor") else None
        from lanekeeper.divide import advisor as advisor_mod
        real = advisor_mod.ClaudeCodeAdvisor
        fake = self

        class Patched(real):
            def __init__(self, command, root, runner=None):
                super().__init__(command, root, runner=fake.claude)

            def check_available(self):
                return None

        advisor_mod.ClaudeCodeAdvisor = Patched
        self.addCleanup(setattr, advisor_mod, "ClaudeCodeAdvisor", real)
        del original

    def test_without_a_terminal_the_proposal_is_shown_and_not_used(self):
        code, out, err = self.spawn(ticket="13", propose=True)
        self.assertEqual(code, 1, out + err)
        self.assertIn("src/search/**", out)
        self.assertNotIn("not/in/repo.py", out, "only paths that exist in the tree")
        self.assertIn("--allow 'src/search/**'", out)
        self.assertEqual(self.agents(), {})

    def test_yes_accepts_the_proposal(self):
        code, out, err = self.spawn(ticket="13", propose=True, yes=True)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(load_config(self.root).lanes["issue-13"].allow, ["src/search/**"])
        self.assertIn("advisor's proposal", out)

    def test_a_ticket_that_names_files_is_not_sent_to_the_advisor(self):
        code, out, err = self.spawn(ticket="12", propose=True, yes=True)
        self.assertEqual(code, 0, out + err)
        self.assertEqual(self.claude.calls, [])

    def test_an_advisor_that_fails_is_one_message(self):
        self.claude.answer = "I have no idea"
        code, out, err = self.spawn(ticket="13", propose=True, yes=True)
        self.assertEqual(code, 1)
        self.assertIn("--allow", err)


class TestReadingOneTicketFromGitHub(unittest.TestCase):
    def test_get_issue_uses_issue_view(self):
        calls = []

        def runner(argv):
            calls.append(list(argv))
            return CommandResult(0, json.dumps({"number": 12, "title": "T", "body": "b",
                                                "labels": [{"name": "bug"}], "state": "OPEN",
                                                "url": "u"}), "")
        tracker = GitHubIssuesTracker(GitHubTrackerConfig(repo="a/b"), Path("."), runner=runner)
        issue = tracker.get_issue("#12")
        self.assertEqual(calls[0][:4], ["gh", "issue", "view", "12"])
        self.assertIn("a/b", calls[0])
        self.assertEqual(issue, TrackedIssue("12", "T", "b", ("bug",), "open", "u"))

    def test_a_missing_ticket_is_none_not_an_error(self):
        tracker = GitHubIssuesTracker(
            GitHubTrackerConfig(), Path("."),
            runner=lambda argv: CommandResult(1, "", "GraphQL: Could not resolve to an Issue"))
        self.assertIsNone(tracker.get_issue("404"))

    def test_the_default_reads_the_list(self):
        fake = FakeTracker([TrackedIssue("7", "seven")])
        self.assertEqual(fake.get_issue("7").title, "seven")
        self.assertIsNone(fake.get_issue("8"))


class TestTheResolver(unittest.TestCase):
    def test_lane_names(self):
        self.assertEqual(ticket_mod.lane_name(TrackedIssue("4", "[BUG-01] x")), "bug-01")
        self.assertEqual(ticket_mod.lane_name(TrackedIssue("4", "plain")), "issue-4")
        self.assertEqual(ticket_mod.lane_name(TrackedIssue("4", "[BUG-01] x"), "mine"), "mine")

    def test_confirmation(self):
        self.assertTrue(ticket_mod.confirm_proposal("1", ["a"], " Y "))
        self.assertFalse(ticket_mod.confirm_proposal("1", ["a"], ""))
        self.assertFalse(ticket_mod.confirm_proposal("1", [], "y"))


if __name__ == "__main__":
    unittest.main()
