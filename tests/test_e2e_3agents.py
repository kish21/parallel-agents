import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from lanekeeper.cli import (
    cmd_cleanup,
    cmd_doctor,
    cmd_init,
    cmd_spawn,
    cmd_status,
    cmd_validate,
)
from lanekeeper.config import load_config
from lanekeeper.state import StateManager


class TestE2E3Agents(unittest.TestCase):
    """The Killer 3-Agent Integration Test.
    
    Proves simultaneous 3-agent isolation:
      - 3 independent physical worktrees
      - 3 deterministic branches
      - 3 non-colliding port allocations
      - 3 parallel in-lane modifications that pass validation
      - Deliberate cross-lane intrusion detection (exit code 2)
      - 100% clean resource reclamation
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        # Git Repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "E2ETester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@parallel.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Production App\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "initial commit"], cwd=self.root, check=True)

        self.orig_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_three_agents_concurrent_workflow(self):
        import argparse
        import concurrent.futures

        # 1. Initialize
        init_args = argparse.Namespace(name="MultiAgentApp", force=False)
        self.assertEqual(cmd_init(init_args), 0)

        # 2. Concurrently spawn 3 agents simultaneously
        spawn_requests = [
            argparse.Namespace(name="backend-agent", lane="backend", task="Build Auth API", seat="SR1", command=None, env=[], force=False),
            argparse.Namespace(name="frontend-agent", lane="frontend", task="Build Login UI", seat="JR1", command=None, env=[], force=False),
            # force=True: this one shares `backend` with the first agent deliberately, so
            # the workflow exercises two agents whose lanes overlap. One-lane-one-owner
            # (#24) is a separate rule with its own tests.
            argparse.Namespace(name="service-agent", lane="backend", task="Build Stripe Webhook", seat="JR2", command=None, env=[], force=True),
        ]

        with concurrent.futures.ThreadPoolExecutor(max_workers=3) as executor:
            spawn_results = list(executor.map(cmd_spawn, spawn_requests))

        for res in spawn_results:
            self.assertEqual(res, 0)

        # Verify state
        state_mgr = StateManager(self.root)
        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 3)

        wt_paths = [Path(a.worktree_path) for a in agents]
        branches = [a.branch for a in agents]
        ports = [a.ports["backend"] for a in agents]

        # Verify 3 distinct physical worktrees & branches
        self.assertEqual(len(set(wt_paths)), 3)
        self.assertEqual(len(set(branches)), 3)
        self.assertEqual(len(set(ports)), 3)
        for wt in wt_paths:
            self.assertTrue(wt.exists())

        agent_1 = state_mgr.get_agent("backend-agent")
        agent_2 = state_mgr.get_agent("frontend-agent")
        agent_3 = state_mgr.get_agent("service-agent")

        wt_1 = Path(agent_1.worktree_path)
        wt_2 = Path(agent_2.worktree_path)
        wt_3 = Path(agent_3.worktree_path)

        # 5. Concurrent In-Lane Modifications
        # Agent 1 (Backend) modifies backend/auth.py
        (wt_1 / "backend").mkdir(parents=True, exist_ok=True)
        (wt_1 / "backend" / "auth.py").write_text("def auth(): pass\n", encoding="utf-8")

        # Agent 2 (Frontend) modifies frontend/Login.tsx
        (wt_2 / "frontend").mkdir(parents=True, exist_ok=True)
        (wt_2 / "frontend" / "Login.tsx").write_text("export const Login = () => null;\n", encoding="utf-8")

        # Agent 3 (Service) modifies backend/stripe.py
        (wt_3 / "backend").mkdir(parents=True, exist_ok=True)
        (wt_3 / "backend" / "stripe.py").write_text("def webhook(): pass\n", encoding="utf-8")

        # 6. Validate all 3 agents -> ALL PASS
        val_1 = argparse.Namespace(agent="backend-agent", json=False)
        val_2 = argparse.Namespace(agent="frontend-agent", json=False)
        val_3 = argparse.Namespace(agent="service-agent", json=False)

        self.assertEqual(cmd_validate(val_1), 0)
        self.assertEqual(cmd_validate(val_2), 0)
        self.assertEqual(cmd_validate(val_3), 0)

        # 7. Deliberately introduce cross-lane violation: Agent 1 touches Frontend
        (wt_1 / "frontend").mkdir(parents=True, exist_ok=True)
        (wt_1 / "frontend" / "App.tsx").write_text("corrupted", encoding="utf-8")

        # Validation must REJECT Agent 1 with exit code 2
        self.assertEqual(cmd_validate(val_1), 2)

        # 8. Clean up all 3 agents cleanly
        for a in agents:
            cln = argparse.Namespace(agent=a.id, force=True)
            self.assertEqual(cmd_cleanup(cln), 0)

        # Verify all worktrees removed & all ports released
        for wt in wt_paths:
            self.assertFalse(wt.exists())
        self.assertEqual(len(state_mgr.get_allocated_ports()), 0)
        self.assertEqual(len(state_mgr.list_agents()), 0)


if __name__ == "__main__":
    unittest.main()
