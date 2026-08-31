import argparse
import concurrent.futures
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

from lanekeeper.cli import cmd_cleanup, cmd_init, cmd_spawn
from lanekeeper.config import generate_default_config, save_config
from lanekeeper.state import StateManager


class TestE2EConcurrent(unittest.TestCase):
    """End-to-end multi-agent concurrent execution tests proving mechanical isolation under load."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        # Initialize Git repo
        subprocess.run(["git", "init", "-b", "main"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "ConcurrentTester"], cwd=self.root, check=True)
        subprocess.run(["git", "config", "user.email", "tester@concurrency.com"], cwd=self.root, check=True)
        (self.root / "README.md").write_text("# Concurrent E2E Repo\n", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=self.root, check=True)

        self.orig_cwd = os.getcwd()
        os.chdir(self.root)

    def tearDown(self):
        os.chdir(self.orig_cwd)
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_concurrent_id(self):
        """Proves atomic agent ID generation under simultaneous concurrent spawn requests."""
        cmd_init(argparse.Namespace(name="ConcurrentIdApp", force=False))
        cfg = generate_default_config("ConcurrentIdApp")
        cfg.max_agents = 10
        save_config(cfg, self.root)

        def spawn_worker(idx):
            return cmd_spawn(
                argparse.Namespace(
                    name=f"worker-{idx}",
                    lane="backend",
                    task=f"Task {idx}",
                    seat="JR1",
                    command=None,
                    env=[],
                    force=False,
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(spawn_worker, range(1, 6)))

        for r in results:
            self.assertEqual(r, 0)

        state_mgr = StateManager(self.root)
        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 5)
        ids = [a.id for a in agents]
        self.assertEqual(len(set(ids)), 5, f"Duplicate IDs detected: {ids}")

    def test_concurrent_port(self):
        """Proves atomic port allocation under simultaneous concurrent spawn requests."""
        cmd_init(argparse.Namespace(name="ConcurrentPortApp", force=False))
        cfg = generate_default_config("ConcurrentPortApp")
        cfg.max_agents = 10
        save_config(cfg, self.root)

        def spawn_worker(idx):
            return cmd_spawn(
                argparse.Namespace(
                    name=f"port-worker-{idx}",
                    lane="frontend",
                    task=f"UI Task {idx}",
                    seat="JR1",
                    command=None,
                    env=[],
                    force=False,
                )
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            results = list(executor.map(spawn_worker, range(1, 6)))

        for r in results:
            self.assertEqual(r, 0)

        state_mgr = StateManager(self.root)
        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 5)
        ports = [a.ports["frontend"] for a in agents]
        self.assertEqual(len(set(ports)), 5, f"Duplicate frontend ports: {ports}")

    def test_ten_agents_concurrent_workflow(self):
        """Spawns 10 independent simultaneous agents, verifies isolation, and cleans up without leaks."""
        cmd_init(argparse.Namespace(name="E2ETenApp", force=False))
        cfg = generate_default_config("E2ETenApp")
        cfg.max_agents = 15
        save_config(cfg, self.root)

        configs = [
            (f"e2e-worker-{i}", "backend" if i % 2 == 0 else "frontend", f"Feature {i}", "JR1")
            for i in range(1, 11)
        ]

        def spawn_one(c):
            name, lane, task, seat = c
            return cmd_spawn(
                argparse.Namespace(name=name, lane=lane, task=task, seat=seat, command=None, env=[], force=False)
            )

        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            results = list(executor.map(spawn_one, configs))

        for r in results:
            self.assertEqual(r, 0)

        state_mgr = StateManager(self.root)
        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 10)

        # Assert unique IDs, worktrees, branches, ports
        ids = [a.id for a in agents]
        wts = [a.worktree_path for a in agents]
        branches = [a.branch for a in agents]
        be_ports = [a.ports["backend"] for a in agents]
        fe_ports = [a.ports["frontend"] for a in agents]

        self.assertEqual(len(set(ids)), 10, f"Colliding IDs: {ids}")
        self.assertEqual(len(set(wts)), 10, f"Colliding Worktrees: {wts}")
        self.assertEqual(len(set(branches)), 10, f"Colliding Branches: {branches}")
        self.assertEqual(len(set(be_ports)), 10, f"Colliding Backend Ports: {be_ports}")
        self.assertEqual(len(set(fe_ports)), 10, f"Colliding Frontend Ports: {fe_ports}")

        for wt in wts:
            self.assertTrue(Path(wt).exists(), f"Missing worktree directory: {wt}")

        # Concurrent cleanup
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            cleanup_results = list(
                executor.map(lambda a_id: cmd_cleanup(argparse.Namespace(agent=a_id, force=True)), ids)
            )

        for cr in cleanup_results:
            self.assertEqual(cr, 0)

        self.assertEqual(len(state_mgr.list_agents()), 0)
        self.assertEqual(len(state_mgr.get_allocated_ports()), 0)

    def test_ten_processes_concurrent_subprocess_spawns(self):
        """Spawns 10 independent OS subprocesses (separate PIDs) concurrently via CLI."""
        import sys
        cmd_init(argparse.Namespace(name="SubprocApp", force=False))
        cfg = generate_default_config("SubprocApp")
        cfg.max_agents = 15
        save_config(cfg, self.root)

        src_dir = str(Path(__file__).resolve().parent.parent / "src")
        env = {**os.environ, "PYTHONPATH": src_dir}

        # Launch 10 simultaneous independent OS processes
        procs = []
        for i in range(1, 11):
            lane = "backend" if i % 2 == 0 else "frontend"
            p = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "lanekeeper.cli",
                    "spawn",
                    "--name",
                    f"proc-worker-{i}",
                    "--lane",
                    lane,
                    "--task",
                    f"Task {i}",
                    "--seat",
                    "JR1",
                ],
                cwd=str(self.root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
            )
            procs.append(p)

        # Wait for all OS processes to complete
        for p in procs:
            stdout, stderr = p.communicate()
            self.assertEqual(p.returncode, 0, f"Process failed: {stderr.decode()}")

        state_mgr = StateManager(self.root)
        agents = state_mgr.list_agents()
        self.assertEqual(len(agents), 10, "Expected 10 agents from independent processes")

        ids = [a.id for a in agents]
        wts = [a.worktree_path for a in agents]
        be_ports = [a.ports["backend"] for a in agents]

        self.assertEqual(len(set(ids)), 10, f"Colliding IDs across OS processes: {ids}")
        self.assertEqual(len(set(wts)), 10, f"Colliding worktrees across OS processes: {wts}")
        self.assertEqual(len(set(be_ports)), 10, f"Colliding ports across OS processes: {be_ports}")


if __name__ == "__main__":
    unittest.main()
