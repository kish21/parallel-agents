"""`repair` must converge: a second run is a no-op and doctor stops complaining.

The failure this covers was self-inflicted. Marking a dead agent FAILED turned its live
port reservations into orphans, and the port-cleanup step only released ports belonging to
agents missing from state entirely — so it never cleared what it had just created. Doctor
said "run repair", repair said "complete", and the same two problems were reported forever.
"""

import subprocess
import tempfile
import unittest
from pathlib import Path

from lanekeeper.capabilities import default_cards, save_card
from lanekeeper.config import generate_default_config
from lanekeeper.doctor import Doctor
from lanekeeper.state import AgentState, AgentStatus, StateManager


class TestRepairConvergence(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Tester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True, capture_output=True)

        self.config = generate_default_config("RepairApp")
        for card in default_cards(sorted(self.config.lanes)):
            save_card(card, self.root)
        self.state = StateManager(self.root)
        self.doctor = Doctor(self.root, self.config, self.state)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def _agent(self, agent_id="agent-001", status=AgentStatus.RUNNING.value, pid=None,
               make_worktree=True):
        worktree = self.root / self.config.worktree_dir / agent_id
        if make_worktree:
            worktree.mkdir(parents=True, exist_ok=True)
        agent = AgentState(
            id=agent_id, name=agent_id, seat="SR1", lane="backend", task="t",
            branch=f"parallel/{agent_id}/t", worktree_path=str(worktree),
            ports={"backend": 8001, "frontend": 3001}, status=status, pid=pid,
        )
        self.state.save_agent(agent)
        self.state.allocate_ports_atomic({8001: agent_id, 3001: agent_id})
        return agent

    def test_repair_releases_ports_held_by_a_terminal_agent(self):
        self._agent(status=AgentStatus.FAILED.value)
        self.assertTrue(self.state.get_allocated_ports())

        self.doctor.repair()

        self.assertEqual(self.state.get_allocated_ports(), {})

    def test_repair_marks_an_agent_whose_worktree_vanished(self):
        self._agent(status=AgentStatus.RUNNING.value, make_worktree=False)

        self.doctor.repair()

        agent = self.state.get_agent("agent-001")
        self.assertEqual(agent.status, AgentStatus.FAILED.value)

    def test_doctor_is_healthy_after_a_single_repair(self):
        """The whole contract in one assertion."""
        self._agent(status=AgentStatus.RUNNING.value, make_worktree=False)
        self.assertFalse(self.doctor.diagnose().is_healthy)

        self.doctor.repair()

        report = self.doctor.diagnose()
        self.assertTrue(report.is_healthy,
                        msg="\n".join(f"{c.name}: {c.message} {c.details or ''}"
                                      for c in report.checks if not c.passed))

    def test_second_repair_takes_no_corrective_action(self):
        self._agent(status=AgentStatus.RUNNING.value, make_worktree=False)
        self.doctor.repair()

        second = self.doctor.repair()

        corrective = [a for a in second if "Pruned" not in a]
        self.assertEqual(corrective, [])

    def test_terminal_agent_with_no_worktree_is_not_a_problem(self):
        """A finished agent legitimately has no working directory."""
        self._agent(status=AgentStatus.STOPPED.value, make_worktree=False)
        self.state.release_ports_for_agent("agent-001")

        report = self.doctor.diagnose()

        self.assertTrue(report.is_healthy,
                        msg="\n".join(f"{c.name}: {c.message}" for c in report.checks if not c.passed))

    def test_unclaimed_directory_is_reported_but_not_repairable(self):
        """Lanekeeper will not delete a directory that may hold uncommitted work."""
        stray = self.root / self.config.worktree_dir / "agent-999"
        stray.mkdir(parents=True)
        (stray / "work.py").write_text("unmerged work\n", encoding="utf-8")

        report = self.doctor.diagnose()

        check = next(c for c in report.checks if c.name == "Worktree directory")
        self.assertFalse(check.passed)
        self.assertFalse(check.repairable)
        self.assertFalse(report.has_repairable_problems)
        self.doctor.repair()
        self.assertTrue(stray.exists(), "repair must never delete unclaimed work")


if __name__ == "__main__":
    unittest.main()
