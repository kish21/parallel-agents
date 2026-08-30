import argparse
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from parallel_agents.cli import cmd_cleanup, cmd_init, cmd_repair, cmd_spawn
from parallel_agents.config import Config, PortRange, generate_default_config, save_config
from parallel_agents.doctor import Doctor
from parallel_agents.ports import PortError, PortManager
from parallel_agents.state import AgentState, AgentStatus, StateManager
from parallel_agents.worktree import GitError, WorktreeManager


class TestFailureModes(unittest.TestCase):
    """Rigorous tests proving failure recovery, transactional rollbacks, and error safety."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "FailureTester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "failure@tester.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Failure Testing\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True)

        self.orig_cwd = os.getcwd()
        os.chdir(self.root)
        cmd_init(argparse.Namespace(name="FailureApp", force=False))

    def tearDown(self):
        os.chdir(self.orig_cwd)
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_port_exhaustion_rollback(self):
        """When port pool is exhausted, already allocated ports are rolled back cleanly."""
        state_mgr = StateManager(self.root)
        # Configure a tiny port range of 1 port
        cfg = generate_default_config("TinyApp")
        cfg.port_ranges = {
            "backend": PortRange(start=9001, end=9001),
            "frontend": PortRange(start=9002, end=9002),
        }
        port_mgr = PortManager(cfg, state_mgr)

        # First allocation succeeds
        ports_1 = port_mgr.allocate_ports_for_agent("agent-001")
        self.assertEqual(ports_1["backend"], 9001)

        # Second allocation fails and rolls back
        with self.assertRaises(PortError):
            port_mgr.allocate_ports_for_agent("agent-002")

        # Confirm agent-002 has zero lingering port reservations
        allocated = state_mgr.get_allocated_ports()
        self.assertNotIn("agent-002", allocated.values())
        self.assertEqual(allocated["9001"], "agent-001")

    def test_worktree_creation_failure_rolls_back_ports(self):
        """If worktree creation fails during spawn, allocated ports must be released."""
        state_mgr = StateManager(self.root)

        # Mock worktree creation failure
        with patch.object(WorktreeManager, "create_worktree", side_effect=GitError("Simulated Git disk failure")):
            spawn_args = argparse.Namespace(
                name="failing-agent",
                lane="backend",
                task="Failing Task",
                seat="SR1",
                command=None,
                env=[],
                force=False,
            )
            res = cmd_spawn(spawn_args)
            self.assertEqual(res, 1)

        # Verify no ports remain reserved for the failed spawn
        allocated = state_mgr.get_allocated_ports()
        self.assertEqual(len(allocated), 0)
        self.assertEqual(len(state_mgr.list_agents()), 0)

    def test_dead_process_detection_and_repair(self):
        """When an agent process dies unexpectedly, doctor detects it and repair recovers state."""
        state_mgr = StateManager(self.root)
        agent = AgentState(
            id="agent-dead",
            name="dead-worker",
            seat="SR1",
            lane="backend",
            task="Dead task",
            branch="parallel/dead",
            worktree_path=str(self.root / ".parallel-agents" / "worktrees" / "agent-dead"),
            status=AgentStatus.RUNNING.value,
            pid=9999999, # Non-existent PID
            ports={"backend": 8001},
        )
        # Create dummy directory
        Path(agent.worktree_path).mkdir(parents=True, exist_ok=True)
        state_mgr.save_agent(agent)
        state_mgr.allocate_port(8001, "agent-dead")

        # Doctor diagnoses the dead PID
        doctor = Doctor(self.root)
        report = doctor.diagnose()
        self.assertFalse(report.is_healthy)
        self.assertTrue(any("PID 9999999 is dead" in c.details or "" for c in report.checks if c.details))

        # Repair cleans up dead agent
        repair_args = argparse.Namespace(agent=None)
        cmd_repair(repair_args)

        # Verify agent marked stopped or cleaned
        updated_agent = state_mgr.get_agent("agent-dead")
        self.assertIn(updated_agent.status, (AgentStatus.FAILED.value, AgentStatus.STOPPED.value))

    def test_cleanup_dirty_worktree_protection(self):
        """Cleanup fails if worktree has uncommitted modifications, unless force=True."""
        spawn_args = argparse.Namespace(
            name="dirty-agent",
            lane="backend",
            task="Dirty task",
            seat="SR1",
            command=None,
            env=[],
            force=False,
        )
        self.assertEqual(cmd_spawn(spawn_args), 0)

        state_mgr = StateManager(self.root)
        agent = state_mgr.get_agent("dirty-agent")
        wt_path = Path(agent.worktree_path)

        # Make uncommitted file modification
        (wt_path / "backend" / "dirty.py").parent.mkdir(parents=True, exist_ok=True)
        (wt_path / "backend" / "dirty.py").write_text("# uncommitted code", encoding="utf-8")

        # Cleanup without force and refusing confirmation must abort cleanly
        clean_args = argparse.Namespace(agent=agent.id, force=False)
        with patch("builtins.input", return_value="n"):
            res = cmd_cleanup(clean_args)
            self.assertEqual(res, 1)

        # Worktree and state must still exist
        self.assertTrue(wt_path.exists())
        self.assertIsNotNone(state_mgr.get_agent(agent.id))

        # Cleanup with force must SUCCEED
        clean_force = argparse.Namespace(agent=agent.id, force=True)
        self.assertEqual(cmd_cleanup(clean_force), 0)
        self.assertFalse(wt_path.exists())
        self.assertIsNone(state_mgr.get_agent(agent.id))


if __name__ == "__main__":
    unittest.main()
