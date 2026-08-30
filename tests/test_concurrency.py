import argparse
import concurrent.futures
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from parallel_agents.cli import cmd_cleanup, cmd_init, cmd_spawn
from parallel_agents.config import generate_default_config, save_config
from parallel_agents.state import StateManager


class TestConcurrency(unittest.TestCase):
    """Rigorous tests proving true concurrent multi-process/thread safety.
    
    Spawns multiple agents in parallel threads simultaneously to verify:
      - Re-entrant StateLock prevents race conditions
      - Unique agent IDs are assigned without collisions
      - Unique physical worktrees and branches are created
      - Unique, non-colliding ports are allocated atomically
      - No lost state in agents.json or ports.json
      - Concurrent cleanup releases all resources cleanly
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        # Initialize Git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "ConcurrentTester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@concurrency.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Concurrency Testing\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True)

        self.orig_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_concurrent_agent_spawning(self):
        # 1. Init with max_agents = 8
        init_args = argparse.Namespace(name="ConcurrencyApp", force=False)
        cmd_init(init_args)

        # Update max_agents to 8
        cfg = generate_default_config("ConcurrencyApp")
        cfg.max_agents = 8
        save_config(cfg, self.root)

        # 2. Concurrently spawn 6 agents simultaneously
        spawn_configs = [
            ("backend-worker-1", "backend", "API Auth", "SR1"),
            ("frontend-worker-1", "frontend", "Login Screen", "JR1"),
            ("backend-worker-2", "backend", "Stripe Billing", "SR2"),
            ("frontend-worker-2", "frontend", "Checkout UI", "JR2"),
            ("data-worker-1", "backend", "Database Schema", "SR1"),
            ("service-worker-1", "backend", "Email Notifications", "JR1"),
        ]

        def spawn_agent(config_tuple):
            name, lane, task, seat = config_tuple
            args = argparse.Namespace(
                name=name,
                lane=lane,
                task=task,
                seat=seat,
                command=None,
                env=[],
                force=False,
            )
            return cmd_spawn(args)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(spawn_agent, c) for c in spawn_configs]
            results = [f.result() for f in futures]

        # All 6 spawns must succeed
        for res in results:
            self.assertEqual(res, 0, "Spawn failed during concurrent execution")

        # 3. Audit State & Assert Atomicity
        state_mgr = StateManager(self.root)
        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 6, "Expected exactly 6 registered agents in state")

        agent_ids = [a.id for a in agents]
        self.assertEqual(len(agent_ids), len(set(agent_ids)), f"Duplicate Agent IDs: {agent_ids}")

        wt_paths = [a.worktree_path for a in agents]
        self.assertEqual(len(wt_paths), len(set(wt_paths)), f"Duplicate Worktrees: {wt_paths}")

        branches = [a.branch for a in agents]
        self.assertEqual(len(branches), len(set(branches)), f"Duplicate Branches: {branches}")

        be_ports = [a.ports["backend"] for a in agents]
        self.assertEqual(len(be_ports), len(set(be_ports)), f"Duplicate Backend Ports: {be_ports}")

        fe_ports = [a.ports["frontend"] for a in agents]
        self.assertEqual(len(fe_ports), len(set(fe_ports)), f"Duplicate Frontend Ports: {fe_ports}")

        # Check all physical worktrees exist
        for wt_p in wt_paths:
            self.assertTrue(Path(wt_p).exists(), f"Worktree missing on disk: {wt_p}")

        # 4. Concurrently Cleanup all 6 agents
        def cleanup_agent(agent_id):
            args = argparse.Namespace(agent=agent_id, force=True)
            return cmd_cleanup(args)

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as executor:
            futures = [executor.submit(cleanup_agent, a.id) for a in agents]
            cleanup_results = [f.result() for f in futures]

        for res in cleanup_results:
            self.assertEqual(res, 0, "Cleanup failed during concurrent execution")

        # Assert full reclamation
        self.assertEqual(len(state_mgr.list_agents()), 0)
        self.assertEqual(len(state_mgr.get_allocated_ports()), 0)


if __name__ == "__main__":
    unittest.main()
