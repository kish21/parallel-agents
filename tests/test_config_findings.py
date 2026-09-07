"""What `config.yaml` said about itself on the deep-test run against 0.7.12.

#68: a fresh `spawn --ticket` wrote ~180 lines, ten of which were the lanes; every
default in it was frozen at the version that wrote it. #70: a lane recorded no ticket,
no provenance and no end, so the file only ever grew and nobody could tell a path the
filer wrote from a path a model proposed at six in the evening.
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

from lanekeeper import cli
from lanekeeper import codeowners
from lanekeeper.config import (Config, InvalidLaneError, IntakeThresholds, LaneConfig,
                               load_config, minimal_dict, save_config)
from lanekeeper.trackers.base import TrackedIssue

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402
from _intake_fakes import FakeTracker  # noqa: E402


def _configs_equal(a: Config, b: Config) -> bool:
    return a.to_dict() == b.to_dict()


# --- #68 --------------------------------------------------------------------------


class TestOnlyWhatDiffersIsWritten(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_the_minimal_and_exhaustive_files_load_identically(self):
        cfg = Config.default("mini-issue-tracker")
        cfg.lanes = {"feat-02": LaneConfig("feat-02", allow=["src/domain/contracts.ts"],
                                           ticket="2", paths_from="ticket")}
        cfg.capability_gates = {}
        full = cfg.to_dict()
        small = cfg.to_dict(minimal=True)
        self.assertLess(len(yaml.safe_dump(small)), len(yaml.safe_dump(full)) / 3)
        self.assertTrue(_configs_equal(Config.from_dict(full), Config.from_dict(small)))

    def test_version_and_project_are_always_written(self):
        small = Config.from_dict({}).to_dict(minimal=True)
        self.assertEqual(small["version"], 1)
        self.assertIn("project", small)
        self.assertNotIn("divide", small)
        self.assertNotIn("intake", small)

    def test_a_hand_set_value_survives_alone_in_its_section(self):
        cfg = Config.from_dict({})
        cfg.intake.thresholds.broad_ticket_areas = 3
        cfg.divide.advisor = "claude-code"
        small = cfg.to_dict(minimal=True)
        self.assertEqual(small["intake"], {"thresholds": {"broad_ticket_areas": 3}})
        self.assertEqual(small["divide"], {"advisor": "claude-code"})

    def test_an_explicitly_empty_list_that_differs_is_kept(self):
        cfg = Config.from_dict({})
        cfg.intake.spec_sources = []
        self.assertEqual(cfg.to_dict(minimal=True)["intake"], {"spec_sources": []})

    def test_a_section_that_is_omitted_picks_up_the_current_default(self):
        """The bug that actually bites: a default written into the file wins forever."""
        (self.root / ".lanekeeper").mkdir()
        (self.root / ".lanekeeper" / "config.yaml").write_text(
            "version: 1\nproject:\n  name: p\nlanes:\n- name: a\n  allow: ['a/**']\n",
            encoding="utf-8")
        loaded = load_config(self.root)
        self.assertEqual(loaded.intake.thresholds.broad_ticket_areas,
                         IntakeThresholds().broad_ticket_areas)

    def test_the_baseline_is_a_missing_key_not_the_starter_policy(self):
        """`Config.default()` carries port ranges a missing key does not restore."""
        cfg = Config.default("p")
        small = cfg.to_dict(minimal=True)
        self.assertIn("ports", small)
        self.assertIn("capability_gates", small)
        self.assertTrue(_configs_equal(Config.from_dict(small), cfg))

    def test_save_writes_the_minimal_form_and_the_full_form_is_still_available(self):
        cfg = Config.default("p")
        cfg.lanes = {"x": LaneConfig("x", allow=["x/**"])}
        save_config(cfg, self.root)
        text = (self.root / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8")
        self.assertNotIn("generic_dirs", text)
        self.assertIn("name: x", text)
        self.assertTrue(_configs_equal(load_config(self.root), cfg))
        save_config(cfg, self.root, minimal=False)
        text = (self.root / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8")
        self.assertIn("generic_dirs", text)

    def test_an_existing_exhaustive_file_keeps_every_value_it_holds(self):
        cfg = Config.default("old")
        cfg.intake.thresholds.broad_ticket_areas = 3   # an old default, or a choice
        cfg.lanes = {"x": LaneConfig("x", allow=["x/**"])}
        save_config(cfg, self.root, minimal=False)
        loaded = load_config(self.root)
        self.assertEqual(loaded.intake.thresholds.broad_ticket_areas, 3)
        # Written again in the minimal form, the value that differs is still there.
        save_config(loaded, self.root)
        self.assertEqual(load_config(self.root).intake.thresholds.broad_ticket_areas, 3)
        self.assertIn("broad_ticket_areas: 3",
                      (self.root / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8"))

    def test_minimal_dict_is_a_pure_function_of_the_full_one(self):
        full = Config.default("p").to_dict()
        self.assertEqual(minimal_dict(full), Config.default("p").to_dict(minimal=True))


class TestAFreshSpawnWritesAFileDominatedByTheLanes(unittest.TestCase):
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
        cli.get_tracker = lambda settings, root: FakeTracker([
            TrackedIssue("2", "[FEAT-02] Thing", "## Allowed File Paths\n- src/a.ts\n")])
        self.addCleanup(setattr, cli, "get_tracker", cli.get_tracker)

    def test_it(self):
        args = argparse.Namespace(name=None, lane=None, ticket="2",
                                  task=cli.p_spawn_default_task(), seat=None, command=None,
                                  force=False, open=False, allow=None, propose=False,
                                  yes=False, accept_overlap=False)
        previous = Path.cwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
                code = cli.cmd_spawn(args)
        finally:
            os.chdir(previous)
        self.assertEqual(code, 0)
        text = (self.root / ".lanekeeper" / "config.yaml").read_text(encoding="utf-8")
        lines = [l for l in text.splitlines() if l.strip()]
        self.assertLess(len(lines), 40, text)
        self.assertNotIn("generic_dirs", text)
        self.assertIn("ticket: '2'", text.replace('ticket: "2"', "ticket: '2'"))
        self.assertIn("paths_from: ticket", text)


# --- #70 --------------------------------------------------------------------------


class TestProvenance(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)

    def test_a_pre_0_8_file_loads_unchanged(self):
        lane = Config.from_dict({"lanes": [{"name": "a", "allow": ["a/**"]}]}).lanes["a"]
        self.assertEqual((lane.ticket, lane.paths_from, lane.retired), ("", "", False))
        self.assertNotIn("ticket", Config.from_dict(
            {"lanes": [{"name": "a", "allow": ["a/**"]}]}).to_dict()["lanes"][0])

    def test_the_fields_round_trip(self):
        cfg = Config.from_dict({"lanes": [{"name": "a", "allow": ["a/**"], "ticket": 7,
                                           "paths_from": "proposed", "retired": True}]})
        lane = cfg.lanes["a"]
        self.assertEqual((lane.ticket, lane.paths_from, lane.retired), ("7", "proposed", True))
        again = Config.from_dict(cfg.to_dict()).lanes["a"]
        self.assertEqual((again.ticket, again.paths_from, again.retired), ("7", "proposed", True))

    def test_bad_values_are_refused(self):
        with self.assertRaises(InvalidLaneError):
            Config.from_dict({"lanes": [{"name": "a", "allow": ["a"], "paths_from": "guess"}]})
        with self.assertRaises(InvalidLaneError):
            Config.from_dict({"lanes": [{"name": "a", "allow": ["a"], "retired": "yes"}]})

    def test_spawn_records_the_source_for_flag_and_proposed(self):
        from lanekeeper import ticket as ticket_mod
        issue = TrackedIssue("13", "Search", "no files")
        cfg = Config.default("p")
        cfg.lanes = {}
        lane = ticket_mod.resolve(cfg, issue, allow=["src/search/**"])
        ticket_mod.ensure_lane(cfg, self.root, lane)
        written = load_config(self.root).lanes["issue-13"]
        self.assertEqual((written.ticket, written.paths_from), ("13", "flag"))
        cfg = Config.default("q")
        cfg.lanes = {}
        lane = ticket_mod.resolve(cfg, issue, proposed=["src/search/**"])
        ticket_mod.ensure_lane(cfg, self.root, lane)
        written = load_config(self.root).lanes["issue-13"]
        self.assertEqual((written.ticket, written.paths_from), ("13", "proposed"))

    def test_divide_confirm_writes_both(self):
        from lanekeeper.divide import draft
        document = {"version": 1, "lanes": {
            "checkout": {"allow": ["src/checkout/**"], "tickets": ["2", "5"]},
            "search": {"allow": ["src/search/**"], "tickets": ["7"]},
        }}
        draft.apply_to_config(document, self.root, project_name="p")
        lanes = load_config(self.root).lanes
        self.assertEqual((lanes["checkout"].ticket, lanes["checkout"].paths_from),
                         ("2, 5", "ticket"))
        self.assertEqual(lanes["search"].ticket, "7")


class TestRetiringIsBookkeepingNeverALoosening(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        self.cfg = Config.default("p")
        self.cfg.capability_gates = {}
        self.cfg.lanes = {
            "feat-02": LaneConfig("feat-02", allow=["src/domain/contracts.ts", "src/c/**"],
                                  ticket="2", retired=True, owner=["@a"]),
            "feat-03": LaneConfig("feat-03", allow=["src/e/**"], ticket="3", owner=["@b"]),
        }

    def test_the_gate_verdict_for_a_retired_lane_is_unchanged(self):
        from lanekeeper import check
        self.assertTrue(check.check_files(self.cfg, "feat-02", ["src/c/x.ts"]).is_valid)
        self.assertFalse(check.check_files(self.cfg, "feat-02", ["src/e/x.ts"]).is_valid)
        self.assertFalse(check.check_files(self.cfg, "feat-03",
                                           ["src/domain/contracts.ts"]).is_valid)

    def test_the_collision_report_skips_it(self):
        from lanekeeper import ticket as ticket_mod
        self.assertEqual(
            ticket_mod.collisions(self.cfg, "feat-04", ["src/domain/contracts.ts"]), [])
        self.cfg.lanes["feat-02"].retired = False
        self.assertEqual(
            len(ticket_mod.collisions(self.cfg, "feat-04", ["src/domain/contracts.ts"])), 1)

    def test_codeowners_skips_it_and_says_so(self):
        plan = codeowners.build_plan(self.cfg, default_owner=["@d"])
        self.assertEqual([r.lane for r in plan.rules if r.lane != "policy"], ["feat-03"])
        self.assertEqual(plan.retired_lanes, ["feat-02"])

    def test_spawn_refuses_a_retired_lane_unless_forced(self):
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True)
        (self.root / "a").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        save_config(self.cfg, self.root)
        res = run_cli(["spawn", "--lane", "feat-02", "--task", "t"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("retired", res.stderr)
        self.assertIn("--force", res.stderr)
        res = run_cli(["spawn", "--lane", "feat-02", "--task", "t", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        status = run_cli(["status"], cwd=self.root)
        self.assertIn("1 retired: feat-02", status.stdout)
        # Cleanup suggests retiring a lane with a ticket, as a suggestion.
        res = run_cli(["spawn", "--lane", "feat-03", "--task", "t"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        res = run_cli(["cleanup", "agent-002", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("If #3 is finished", res.stdout)
        self.assertIn("A suggestion", res.stdout)
        self.assertFalse(load_config(self.root).lanes["feat-03"].retired)


if __name__ == "__main__":
    unittest.main()
