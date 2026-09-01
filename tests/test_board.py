"""The board: created from the configuration, and read back as the source of truth.

`gh` is a fake runner replaying its JSON. What is tested is that the script's inputs
come from `config.yaml`, that the cards are read by ticket number, that a card's Lane
outranks the ticket form, and that `spawn --ticket` takes lane and seat from the board.
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

from lanekeeper import board as board_mod
from lanekeeper import cli
from lanekeeper.capabilities import default_cards, save_card
from lanekeeper.config import BoardConfig, Config, DivideConfig, LaneConfig, load_config, save_config
from lanekeeper.divide.proposal import propose
from lanekeeper.intake.models import CoverageReport, CoverageVerdict, IntakeResult, Verdict
from lanekeeper.trackers.github_issues import CommandResult

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _divide_fixtures import feature_files, ticket  # noqa: E402


PROJECTS = json.dumps({"projects": [{"title": "Other", "number": 3},
                                    {"title": "Delivery board", "number": 7}]})
ITEMS = json.dumps({"items": [
    {"content": {"type": "Issue", "number": 12, "title": "Cart"}, "lane": "checkout",
     "owner": "junior", "seat": "JR1", "status": "Todo"},
    {"content": {"type": "Issue", "number": 13, "title": "Search"}, "Lane": "search",
     "Seat": "SR1"},
    {"content": {"type": "DraftIssue", "title": "no number"}, "lane": "x"},
    {"content": {"type": "Issue", "number": 14, "title": "Blank"}},
]})


class GhRunner:
    def __init__(self, projects=PROJECTS, items=ITEMS, fail=None):
        self.projects, self.items, self.fail = projects, items, fail
        self.calls = []

    def __call__(self, argv):
        self.calls.append(list(argv))
        if self.fail:
            return CommandResult(1, "", self.fail)
        if argv[1:3] == ["project", "list"]:
            return CommandResult(0, self.projects, "")
        if argv[1:3] == ["project", "item-list"]:
            return CommandResult(0, self.items, "")
        return CommandResult(1, "", "unexpected")


class TestReadingCards(unittest.TestCase):
    def test_cards_are_keyed_by_ticket_number_with_either_field_spelling(self):
        cards = board_mod.parse_items(json.loads(ITEMS)["items"])
        self.assertEqual(set(cards), {"12", "13", "14"})
        self.assertEqual(cards["12"], board_mod.BoardCard("12", "checkout", "junior", "JR1", "Todo"))
        self.assertEqual(cards["13"].lane, "search")
        self.assertEqual(cards["13"].seat, "SR1")
        self.assertEqual(cards["14"].lane, "")

    def test_reader_finds_the_board_by_title_and_lists_its_items(self):
        runner = GhRunner()
        reader = board_mod.BoardReader(BoardConfig(title="Delivery board", owner="kish"),
                                       Path("."), runner=runner)
        cards = reader.cards()
        self.assertEqual(cards["12"].lane, "checkout")
        self.assertIn("7", runner.calls[1])
        self.assertIn("kish", runner.calls[1])

    def test_a_missing_board_says_how_to_create_it(self):
        reader = board_mod.BoardReader(BoardConfig(title="Nope"), Path("."), runner=GhRunner())
        with self.assertRaises(board_mod.BoardError) as ctx:
            reader.cards()
        self.assertIn("lanekeeper board", str(ctx.exception))

    def test_a_scope_error_names_the_fix(self):
        reader = board_mod.BoardReader(
            BoardConfig(), Path("."),
            runner=GhRunner(fail="error: your token has not been granted the required scopes: project"))
        with self.assertRaises(board_mod.BoardError) as ctx:
            reader.cards()
        self.assertIn("gh auth refresh", str(ctx.exception))

    def test_render_names_cards_without_a_lane(self):
        text = board_mod.render_cards(board_mod.parse_items(json.loads(ITEMS)["items"]))
        self.assertIn("#12", text)
        self.assertIn("no Lane", text)
        self.assertIn("#14", text)


class TestCreatingTheBoard(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.cfg = Config.default("p")
        self.cfg.lanes = {
            "checkout": LaneConfig("checkout", allow=["src/checkout/**"]),
            "search": LaneConfig("search", allow=["src/search/**"]),
        }
        self.cfg.board = BoardConfig(title="My board", owner="acme")
        save_config(self.cfg, self.tmp)
        for card in default_cards(["checkout", "search"]):
            save_card(card, self.tmp)

    def test_the_inputs_come_from_the_configuration(self):
        conf = board_mod.write_conf(self.cfg, self.tmp, repo="acme/shop")
        text = conf.read_text(encoding="utf-8")
        self.assertIn("PROJECT_TITLE='My board'", text)
        self.assertIn("PROJECT_OWNER='acme'", text)
        self.assertIn("REPO='acme/shop'", text)
        self.assertIn("  checkout\n  search\n", text)
        self.assertIn("lane: checkout|", text)
        self.assertIn("  JR1\n", text)
        for layer in ("interface", "service", "platform"):
            self.assertNotIn(f"\n  {layer}\n", text)

    def test_the_script_can_source_the_generated_inputs(self):
        bash = board_mod.find_bash()
        if bash is None or subprocess.run([bash, "-c", "echo ok"], capture_output=True,
                                          text=True).stdout.strip() != "ok":
            self.skipTest("no working bash on this machine")
        conf = board_mod.write_conf(self.cfg, self.tmp)
        res = subprocess.run(
            [bash, "-c", f". '{board_mod.bash_path(conf)}' && printf '%s' \"$PROJECT_TITLE\" "
                         f"&& printf '|%s' \"$LANES\""],
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue(res.stdout.startswith("My board|"))
        self.assertIn("checkout", res.stdout)

    def test_the_packaged_script_exists_and_the_root_wrapper_forwards_to_it(self):
        self.assertTrue(board_mod.SCRIPT.is_file())
        wrapper = Path(__file__).resolve().parents[1] / "bootstrap.sh"
        self.assertIn("src/lanekeeper/scripts/bootstrap.sh", wrapper.read_text(encoding="utf-8"))

    @unittest.skipIf(board_mod.find_bash() is None, "bash is needed to run the script")
    def test_create_runs_the_script_with_the_inputs(self):
        seen = {}

        def launcher(argv):
            seen["argv"] = list(argv)
            return 0

        code = board_mod.create(self.cfg, self.tmp, dry_run=True, launcher=launcher)
        self.assertEqual(code, 0)
        self.assertEqual(Path(seen["argv"][1]).resolve(), board_mod.SCRIPT)
        self.assertIn("--dry-run", seen["argv"])
        self.assertIn("--config", seen["argv"])


def _result(issues):
    return IntakeResult(verdict=Verdict.READY, issue_count=len(issues),
                        coverage=CoverageReport(verdict=CoverageVerdict.CANNOT_JUDGE),
                        issues=tuple(issues))


class TestTheBoardOutranksTheForm(unittest.TestCase):
    def test_a_board_lane_replaces_the_declared_one(self):
        issues = [
            ticket(1, "Cart page", ["backend/app/domains/catalog/**"], lane="catalog"),
            ticket(2, "Cart api", ["backend/app/api/catalog.py"]),
        ]
        with_board = propose(Path("."), DivideConfig(), _result(issues), files=feature_files(),
                             board_lanes={"1": "checkout", "2": "checkout"})
        names = {lane.name for lane in with_board.lanes}
        self.assertIn("checkout", names)
        self.assertNotIn("catalog", names)


@contextlib.contextmanager
def in_dir(path):
    previous = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(previous)


class FakeReader:
    cards_by_ref = {"12": board_mod.BoardCard("12", lane="backend", seat="SR1"),
                    "14": board_mod.BoardCard("14")}

    def __init__(self, settings, root, gh="gh", runner=None):
        pass

    def cards(self):
        return dict(self.cards_by_ref)


class TestSpawnFromATicket(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        subprocess.run(["git", "init", "-q", "-b", "main", "."], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.c"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=self.root, check=True)
        (self.root / "backend").mkdir()
        (self.root / "backend" / "app.py").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        cfg = Config.default("p")
        cfg.capability_gates = {}
        save_config(cfg, self.root)
        self.original = cli.board_mod.BoardReader
        cli.board_mod.BoardReader = FakeReader

    def tearDown(self):
        cli.board_mod.BoardReader = self.original

    def _spawn(self, **kw):
        args = argparse.Namespace(name=None, lane=None, ticket=None, task=cli.p_spawn_default_task(),
                                  seat=None, command=None, force=False, open=False)
        for k, v in kw.items():
            setattr(args, k, v)
        out, err = io.StringIO(), io.StringIO()
        with in_dir(self.root), contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.cmd_spawn(args)
        return code, out.getvalue(), err.getvalue()

    def test_lane_seat_and_task_come_from_the_card(self):
        code, out, err = self._spawn(ticket="12")
        self.assertEqual(code, 0, out + err)
        self.assertIn("Lane:     backend", out)
        self.assertIn("Seat:     SR1", out)
        status = load_config(self.root)  # config still loads; state has the agent
        self.assertIsNotNone(status)
        agents = json.loads((self.root / ".lanekeeper" / "state" / "agents.json").read_text())
        self.assertEqual(agents["agent-001"]["task"], "#12")

    def test_a_card_with_no_lane_is_refused(self):
        code, out, err = self._spawn(ticket="14")
        self.assertEqual(code, 1)
        self.assertIn("no Lane", err)

    def test_a_ticket_not_on_the_board_is_refused(self):
        code, out, err = self._spawn(ticket="99")
        self.assertEqual(code, 1)
        self.assertIn("not on the board", err)

    def test_neither_lane_nor_ticket_is_refused(self):
        code, out, err = self._spawn()
        self.assertEqual(code, 1)
        self.assertIn("--ticket", err)


if __name__ == "__main__":
    unittest.main()
