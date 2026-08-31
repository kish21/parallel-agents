"""Tests for capability gates — the mechanical form of the project's second thesis.

03-orchestration.md states the rule: a harness that cannot safely perform a task must
hard-stop and escalate rather than quietly hand in weaker work. Before this feature the
seat was a decorative string assigned by a name heuristic. These tests pin the enforced
behaviour, and follow the same fail-closed posture as lane validation: an unrated
capability, an unknown seat, and a missing card are all denials, never permissions.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.capabilities import (
    CapabilityCard,
    CapabilityCardError,
    CapabilityRegistry,
    CapabilityState,
    UnknownSeatError,
    default_cards,
    save_card,
)
from lanekeeper.config import CapabilityGate, QualityCommand, generate_default_config, save_config
from lanekeeper.state import AgentState, StateManager
from lanekeeper.validator import Validator
from lanekeeper.worktree import WorktreeManager

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402

AUTH_FILE = "src/backend/auth/login.py"
MIGRATION_FILE = "migrations/001_add_users.sql"
ORDINARY_FILE = "src/backend/api.py"


class TestCapabilityCard(unittest.TestCase):
    def test_unrated_capability_is_unavailable_not_permitted(self):
        """Absence must never mean permission."""
        card = CapabilityCard(seat="JR1", capabilities={"unit_test_generation": "native"})
        self.assertIs(card.state_for("security_review"), CapabilityState.UNAVAILABLE)
        self.assertFalse(card.declares("security_review"))

    def test_invalid_state_is_rejected_at_load(self):
        with self.assertRaises(CapabilityCardError):
            CapabilityCard.from_dict({"seat": "JR1", "capabilities": {"x": "sort-of"}})

    def test_card_without_seat_is_rejected(self):
        with self.assertRaises(CapabilityCardError):
            CapabilityCard.from_dict({"capabilities": {}})

    def test_empty_scope_means_unrestricted(self):
        card = CapabilityCard(seat="SR1", max_allowed_lane_scope=[])
        self.assertTrue(card.allows_lane("anything"))

    def test_non_empty_scope_is_exhaustive(self):
        card = CapabilityCard(seat="JR1", max_allowed_lane_scope=["backend"])
        self.assertTrue(card.allows_lane("backend"))
        self.assertFalse(card.allows_lane("platform"))

    def test_default_junior_cards_are_actually_restricted(self):
        """If the starter juniors were native everywhere, the gates would be decorative."""
        jr = next(c for c in default_cards(["backend"]) if c.seat == "JR1")
        self.assertIs(jr.state_for("security_review"), CapabilityState.UNAVAILABLE)
        self.assertIs(jr.state_for("database_migrations"), CapabilityState.AUTHOR_REQUIRED)
        sr = next(c for c in default_cards(["backend"]) if c.seat == "SR1")
        self.assertIs(sr.state_for("security_review"), CapabilityState.NATIVE)


class TestRegistryFailsClosed(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def test_unknown_seat_raises_and_names_valid_seats(self):
        save_card(CapabilityCard(seat="SR1"), self.tmp)
        registry = CapabilityRegistry.load(self.tmp)
        with self.assertRaises(UnknownSeatError) as ctx:
            registry.get("JR9")
        self.assertIn("JR9", str(ctx.exception))
        self.assertIn("SR1", str(ctx.exception))

    def test_missing_directory_yields_empty_registry(self):
        self.assertTrue(CapabilityRegistry.load(self.tmp).is_empty)

    def test_malformed_json_is_an_error_not_a_silent_skip(self):
        d = self.tmp / ".lanekeeper" / "capabilities"
        d.mkdir(parents=True)
        (d / "SR1.json").write_text("{not json", encoding="utf-8")
        with self.assertRaises(CapabilityCardError):
            CapabilityRegistry.load(self.tmp)


class GateTestCase(unittest.TestCase):
    """A real repo with a worktree, so changed-file detection is genuine."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for args in (["init", "-q", "-b", "main", "."],
                     ["config", "user.email", "t@t.c"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.tmp, check=True, capture_output=True)
        (self.tmp / "README.md").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.tmp, check=True, capture_output=True)

        self.config = generate_default_config("GateApp")
        save_config(self.config, self.tmp)
        for card in default_cards(sorted(self.config.lanes)):
            save_card(card, self.tmp)

        self.state = StateManager(self.tmp)
        self.wt_mgr = WorktreeManager(self.tmp)

    def _agent(self, seat, lane="backend", files=(ORDINARY_FILE,)):
        wt = self.wt_mgr.create_worktree(Path("wt"), f"parallel/agent-001/{seat}")
        for rel in files:
            f = wt / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("content", encoding="utf-8")
        agent = AgentState(id="agent-001", name="a", seat=seat, lane=lane, task="t",
                           branch=f"parallel/agent-001/{seat}", worktree_path=str(wt))
        self.state.save_agent(agent)
        return agent

    def _validate(self, seat, lane="backend", files=(ORDINARY_FILE,)):
        self._agent(seat, lane, files)
        return Validator(self.config, self.state, self.wt_mgr,
                         CapabilityRegistry.load(self.tmp)).validate_agent("agent-001")


class TestGateEnforcement(GateTestCase):
    def test_unavailable_capability_is_a_hard_stop(self):
        """The central test: an in-lane file blocked purely by capability."""
        report = self._validate("JR1", files=(AUTH_FILE,))
        self.assertTrue(report.lane_result.is_valid, "file must be in-lane, so only the gate can block it")
        self.assertFalse(report.is_valid)
        self.assertEqual(len(report.capability_violations), 1)
        cv = report.capability_violations[0]
        self.assertEqual(cv.capability, "security_review")
        self.assertEqual(cv.state, "unavailable")
        self.assertEqual(cv.filepath, AUTH_FILE)

    def test_native_capability_passes_the_same_file(self):
        report = self._validate("SR1", files=(AUTH_FILE,))
        self.assertTrue(report.is_valid, report.errors)
        self.assertEqual(report.capability_violations, [])

    def test_ungated_file_is_not_blocked(self):
        report = self._validate("JR1", files=(ORDINARY_FILE,))
        self.assertTrue(report.is_valid, report.errors)

    def test_author_required_without_a_verified_script_is_blocked(self):
        report = self._validate("JR1", lane="data", files=(MIGRATION_FILE,))
        self.assertFalse(report.is_valid)
        cv = next(c for c in report.capability_violations if c.capability == "database_migrations")
        self.assertEqual(cv.state, "author-required")

    def test_author_required_passes_when_its_script_passes(self):
        self.config.quality.commands = [
            QualityCommand(command="echo ok", satisfies="database_migrations")]
        report = self._validate("JR1", lane="data", files=(MIGRATION_FILE,))
        self.assertTrue(report.is_valid, report.errors)

    def test_author_required_stays_blocked_when_its_script_fails(self):
        self.config.quality.commands = [
            QualityCommand(command="exit 1", satisfies="database_migrations")]
        report = self._validate("JR1", lane="data", files=(MIGRATION_FILE,))
        self.assertFalse(report.is_valid)

    def test_a_passing_untagged_command_does_not_satisfy_a_gate(self):
        """An unrelated green command must not be mistaken for the verified script."""
        self.config.quality.commands = [QualityCommand(command="echo ok", satisfies=None)]
        report = self._validate("JR1", lane="data", files=(MIGRATION_FILE,))
        self.assertFalse(report.is_valid)

    def test_forbidden_paths_override_the_lane_allow(self):
        save_card(CapabilityCard(
            seat="JR1", capabilities={"security_review": "native", "database_migrations": "native"},
            max_allowed_lane_scope=["backend"], forbidden_paths=["src/backend/api.py"]), self.tmp)
        report = self._validate("JR1", files=(ORDINARY_FILE,))
        self.assertFalse(report.is_valid)
        self.assertEqual(report.capability_violations[0].state, "forbidden")

    def test_forbidden_directory_prefix_form_is_supported(self):
        """The card examples use 'dir/' rather than a glob; both must work."""
        save_card(CapabilityCard(
            seat="JR1", capabilities={"security_review": "native", "database_migrations": "native"},
            max_allowed_lane_scope=["backend"], forbidden_paths=["src/backend/"]), self.tmp)
        report = self._validate("JR1", files=(ORDINARY_FILE,))
        self.assertFalse(report.is_valid)

    def test_seat_outside_its_lane_scope_is_rejected(self):
        save_card(CapabilityCard(
            seat="JR1", capabilities={"security_review": "native", "database_migrations": "native"},
            max_allowed_lane_scope=["frontend"]), self.tmp)
        report = self._validate("JR1", lane="backend", files=(ORDINARY_FILE,))
        self.assertFalse(report.is_valid)
        self.assertTrue(any("not permitted in lane" in e for e in report.errors))

    def test_missing_card_fails_closed_when_gates_are_configured(self):
        report = self._validate("SEAT-WITH-NO-CARD", files=(AUTH_FILE,))
        self.assertFalse(report.is_valid)
        self.assertTrue(any("Unknown seat" in e for e in report.errors))

    def test_capability_absent_from_card_fails_closed(self):
        """A card that forgot to rate a gated capability must not thereby pass it."""
        save_card(CapabilityCard(seat="JR1", capabilities={"unit_test_generation": "native"},
                                 max_allowed_lane_scope=["backend"]), self.tmp)
        report = self._validate("JR1", files=(AUTH_FILE,))
        self.assertFalse(report.is_valid)
        cv = report.capability_violations[0]
        self.assertEqual(cv.state, "unavailable")
        self.assertIn("not rated on the card", cv.detail)

    def test_no_gates_configured_means_no_gating(self):
        """Gating applies only where the operator declared gates."""
        self.config.capability_gates = {}
        report = self._validate("SEAT-WITH-NO-CARD", files=(AUTH_FILE,))
        self.assertTrue(report.is_valid, report.errors)
        self.assertEqual(report.gates_evaluated, [])


class TestCliIntegration(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        for args in (["init", "-q", "-b", "main", "."],
                     ["config", "user.email", "t@t.c"],
                     ["config", "user.name", "t"]):
            subprocess.run(["git", *args], cwd=self.tmp, check=True, capture_output=True)
        (self.tmp / "README.md").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.tmp, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.tmp, check=True, capture_output=True)
        res = run_cli(["init", "--name", "proj"], self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))

    def _worktree_of(self, agent_id):
        agents = json.loads((self.tmp / ".lanekeeper/state/agents.json").read_text())
        return Path(agents[agent_id]["worktree_path"])

    def test_init_writes_cards_for_every_standard_seat(self):
        cards_dir = self.tmp / ".lanekeeper" / "capabilities"
        self.assertTrue(cards_dir.is_dir())
        self.assertEqual({p.stem for p in cards_dir.glob("*.json")}, {"SR1", "SR2", "JR1", "JR2"})

    def test_spawn_rejects_an_undeclared_seat(self):
        res = run_cli(["spawn", "--lane", "backend", "--seat", "JR9", "--name", "x",
                       "--task", "t"], self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("Unknown seat", res.stderr)
        agents = json.loads((self.tmp / ".lanekeeper/state/agents.json").read_text())
        self.assertEqual(agents, {}, "a rejected spawn must provision nothing")

    def test_validate_blocks_a_gated_file_with_exit_code_2(self):
        self.assertEqual(run_cli(["spawn", "--lane", "backend", "--seat", "JR1",
                                  "--name", "jr", "--task", "t"], self.tmp).returncode, 0)
        wt = self._worktree_of("agent-001")
        (wt / "src" / "backend" / "auth").mkdir(parents=True, exist_ok=True)
        (wt / "src" / "backend" / "auth" / "login.py").write_text("x", encoding="utf-8")

        res = run_cli(["validate", "agent-001"], self.tmp)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("security_review", res.stdout)
        self.assertNotIn("VALIDATION PASSED", res.stdout)

    def test_declare_reports_the_block_and_exits_nonzero(self):
        self.assertEqual(run_cli(["spawn", "--lane", "backend", "--seat", "JR1",
                                  "--name", "jr", "--task", "t"], self.tmp).returncode, 0)
        wt = self._worktree_of("agent-001")
        (wt / "src" / "backend" / "auth").mkdir(parents=True, exist_ok=True)
        (wt / "src" / "backend" / "auth" / "login.py").write_text("x", encoding="utf-8")

        res = run_cli(["declare", "agent-001"], self.tmp)
        self.assertEqual(res.returncode, 2, output_of(res))
        self.assertIn("**Seat**: JR1", res.stdout)
        self.assertIn("security_review", res.stdout)
        self.assertIn("BLOCKED", res.stdout)

    def test_declare_is_clean_for_a_native_seat(self):
        self.assertEqual(run_cli(["spawn", "--lane", "backend", "--seat", "SR1",
                                  "--name", "sr", "--task", "t"], self.tmp).returncode, 0)
        wt = self._worktree_of("agent-001")
        (wt / "src" / "backend" / "auth").mkdir(parents=True, exist_ok=True)
        (wt / "src" / "backend" / "auth" / "login.py").write_text("x", encoding="utf-8")

        res = run_cli(["declare", "agent-001"], self.tmp)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("[x] `security_review` (seat rated: native)", res.stdout)
        self.assertIn("Clean / All Passed", res.stdout)

    def test_doctor_flags_an_agent_whose_seat_has_no_card(self):
        self.assertEqual(run_cli(["spawn", "--lane", "backend", "--seat", "JR1",
                                  "--name", "jr", "--task", "t"], self.tmp).returncode, 0)
        (self.tmp / ".lanekeeper" / "capabilities" / "JR1.json").unlink()
        res = run_cli(["doctor"], self.tmp)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("Capability cards", res.stdout)


if __name__ == "__main__":
    unittest.main()
