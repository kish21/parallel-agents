"""Shared code that belongs to no feature — issue #25.

Feature lanes (#23) are clean where a repository is genuinely separable. The part
that is not — the store, the shared types, the page files every feature touches — is
where parallel agents actually collide, and under a feature split it is not a
configuration defect to be tidied away. It is a permanent state, so it gets a lane
whose owner is nobody, and a change there is escalated rather than reported as a
misconfigured boundary.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.check import check_files
from lanekeeper.config import (Config, InvalidLaneError, LaneConfig, generate_default_config,
                               load_config, save_config)
from lanekeeper.lanes import LaneEngine

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


def _config():
    cfg = generate_default_config("Shared")
    cfg.lanes = {
        "checkout": LaneConfig(name="checkout", allow=["frontend/src/**", "backend/checkout/**"]),
        "catalog": LaneConfig(name="catalog", allow=["frontend/src/**", "backend/catalog/**"]),
        "shared-ui": LaneConfig(name="shared-ui", allow=["frontend/src/store/**",
                                                         "frontend/src/types/**"], shared=True),
    }
    return cfg


class TestTheGateSeesASharedZone(unittest.TestCase):
    def setUp(self):
        self.config = _config()
        self.shared = LaneEngine.shared_lanes(self.config)

    def test_a_shared_file_beats_the_lanes_own_allow(self):
        # 'checkout' allows frontend/src/** — which is exactly why an overlap-only
        # reading would be silent here, in the one case the zone exists for.
        v = LaneEngine.check_file("frontend/src/store/cart.ts",
                                  self.config.lanes["checkout"], self.shared)
        self.assertIsNotNone(v)
        self.assertEqual(v.reason, "shared")
        self.assertEqual(v.shared_lane, "shared-ui")

    def test_ordinary_work_in_the_same_tree_still_passes(self):
        self.assertIsNone(LaneEngine.check_file("frontend/src/checkout/Cart.tsx",
                                                self.config.lanes["checkout"], self.shared))

    def test_the_zone_itself_may_change_its_own_files(self):
        # The deliberate, escalated change: made under the shared lane, by a person.
        self.assertIsNone(LaneEngine.check_file("frontend/src/store/cart.ts",
                                                self.config.lanes["shared-ui"], self.shared))

    def test_check_files_reports_it_as_shared(self):
        result = check_files(self.config, "checkout", ["frontend/src/store/cart.ts"])
        self.assertFalse(result.is_valid)
        self.assertEqual([v.reason for v in result.violations], ["shared"])


class TestTheGateInCiSaysIt(unittest.TestCase):
    """The message an agent reads when its own change reaches the shared middle."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True, capture_output=True)
        store = self.root / "frontend" / "src" / "store"
        store.mkdir(parents=True)
        (store / "cart.ts").write_text("export const cart = 1\n", encoding="utf-8")
        save_config(_config(), self.root)
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True, capture_output=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        subprocess.run(["git", "checkout", "-qb", "work"], cwd=self.root, check=True)
        (store / "cart.ts").write_text("export const cart = 2\n", encoding="utf-8")
        subprocess.run(["git", "commit", "-qam", "touch the store"], cwd=self.root, check=True)

    def test_it_fails_and_tells_the_agent_to_raise_it(self):
        res = run_cli(["check", "--lane", "checkout", "--base", "main"], cwd=self.root)
        self.assertEqual(res.returncode, 2, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn("shared code", out, output_of(res))
        self.assertIn("shared-ui", out, output_of(res))
        self.assertNotIn("outside lane", out, output_of(res))


class TestSharedIsDeclaredNotGuessed(unittest.TestCase):
    def test_it_survives_a_round_trip_through_the_file(self):
        root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, str(root), ignore_errors=True)
        save_config(_config(), root)
        lanes = load_config(root).lanes
        self.assertTrue(lanes["shared-ui"].shared)
        self.assertFalse(lanes["checkout"].shared)

    def test_an_ordinary_lane_writes_no_shared_key(self):
        text = Config.default().to_dict()
        for lane in text["lanes"]:
            self.assertNotIn("shared", lane)

    def test_a_non_boolean_is_refused_rather_than_read_as_true(self):
        from lanekeeper.config import _parse_lane
        with self.assertRaises(InvalidLaneError):
            _parse_lane("x", {"allow": ["a/**"], "shared": "yes"})


class TestNobodyIsSpawnedIntoIt(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True, capture_output=True)
        (self.root / "README.md").write_text("# r\n", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)
        cfg = _config()
        cfg.capability_gates = {}
        save_config(cfg, self.root)

    def test_spawn_refuses_and_says_why(self):
        res = run_cli(["spawn", "--lane", "shared-ui", "--name", "w", "--task", "t"],
                      cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        out = res.stdout + res.stderr
        self.assertIn("shared code", out)
        self.assertIn("no agent", out.lower())

    def test_a_feature_lane_still_spawns(self):
        res = run_cli(["spawn", "--lane", "checkout", "--name", "w", "--task", "t"],
                      cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))


if __name__ == "__main__":
    unittest.main()
