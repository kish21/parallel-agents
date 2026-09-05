"""Issues #24 and #29: the two open bugs a real run would reach.

#24 is the serious one. Two agents in one lane can edit the same files, and the gate
passes both — because both *are* inside the boundary. The tool's whole promise is that
it prevents exactly that, so it has to refuse at the point the second agent is created;
by merge time the collision has already happened.

#29 is the one that stops people acting on the tool's own advice. Every message that
says "add the path to its lane in config.yaml" produces a lane the capability cards
have never heard of, and the next spawn failed with a seat error naming the old lanes.
"""

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.capabilities import CapabilityRegistry, default_cards, save_card
from lanekeeper.config import Config, LaneConfig, save_config

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


class LaneRepoTestCase(unittest.TestCase):
    def setUp(self):
        self.root = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.root, ignore_errors=True)
        for cmd in (["git", "init", "-q", "-b", "main", "."],
                    ["git", "config", "user.email", "t@t.c"],
                    ["git", "config", "user.name", "t"]):
            subprocess.run(cmd, cwd=self.root, check=True)
        for rel in ("src/a/f.ts", "src/b/f.ts"):
            f = self.root / rel
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "-A"], cwd=self.root, check=True)
        subprocess.run(["git", "commit", "-qm", "init"], cwd=self.root, check=True)

    def write_config(self, lanes, gates=True):
        cfg = Config.default("p")
        cfg.lanes = {name: LaneConfig(name, allow=allow) for name, allow in lanes.items()}
        if not gates:
            cfg.capability_gates = {}
        save_config(cfg, self.root)
        return cfg

    def write_cards(self, scope):
        for card in default_cards(list(scope)):
            save_card(card, self.root)

    def agents(self):
        f = self.root / ".lanekeeper" / "state" / "agents.json"
        return json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}


class TestOneLaneOneOwner(LaneRepoTestCase):
    """#24."""

    def setUp(self):
        super().setUp()
        self.write_config({"alpha": ["src/a/**"], "beta": ["src/b/**"]})
        self.write_cards(["alpha", "beta"])
        first = run_cli(["spawn", "--lane", "alpha", "--task", "one"], cwd=self.root)
        self.assertEqual(first.returncode, 0, output_of(first))

    def test_a_second_agent_in_the_same_lane_is_refused(self):
        res = run_cli(["spawn", "--lane", "alpha", "--task", "two"], cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("already belongs to agent-001", res.stderr)
        self.assertIn("cleanup agent-001", res.stderr)
        self.assertEqual(list(self.agents()), ["agent-001"], "nothing was provisioned")

    def test_another_lane_is_unaffected(self):
        res = run_cli(["spawn", "--lane", "beta", "--task", "two"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertEqual(sorted(self.agents()), ["agent-001", "agent-002"])

    def test_force_still_allows_it_deliberately(self):
        res = run_cli(["spawn", "--lane", "alpha", "--task", "two", "--force"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertEqual(sorted(self.agents()), ["agent-001", "agent-002"])

    def test_the_lane_frees_up_when_the_agent_is_cleaned_away(self):
        clean = run_cli(["cleanup", "agent-001", "--force"], cwd=self.root)
        self.assertEqual(clean.returncode, 0, output_of(clean))
        res = run_cli(["spawn", "--lane", "alpha", "--task", "two"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))

    def test_a_stopped_agent_does_not_hold_its_lane(self):
        stop = run_cli(["stop", "agent-001"], cwd=self.root)
        self.assertEqual(stop.returncode, 0, output_of(stop))
        res = run_cli(["spawn", "--lane", "alpha", "--task", "two"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))


class TestCardsAreReconciledWithHandEditedLanes(LaneRepoTestCase):
    """#29."""

    def test_a_lane_no_card_has_heard_of_is_a_stale_card_not_a_refusal(self):
        self.write_config({"alpha": ["src/a/**"]})
        self.write_cards(["frontend"])  # cards written before 'alpha' existed
        res = run_cli(["spawn", "--lane", "alpha", "--task", "one"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("newer than the seat cards", res.stdout)
        for seat in ("JR1", "SR1"):
            self.assertIn("alpha", CapabilityRegistry.load(self.root).get(seat).max_allowed_lane_scope)

    def test_a_lane_other_cards_do_name_is_a_real_restriction(self):
        self.write_config({"alpha": ["src/a/**"]})
        self.write_cards(["alpha"])
        card = CapabilityRegistry.load(self.root).get("JR1")
        card.max_allowed_lane_scope = ["beta"]
        save_card(card, self.root)
        res = run_cli(["spawn", "--lane", "alpha", "--task", "one", "--seat", "JR1"],
                      cwd=self.root)
        self.assertEqual(res.returncode, 1, output_of(res))
        self.assertIn("not permitted in lane 'alpha'", res.stderr)
        self.assertIn("--seat", res.stderr)

    def test_an_unrestricted_card_is_left_alone(self):
        self.write_config({"alpha": ["src/a/**"]})
        for card in default_cards([]):  # empty scope means no restriction
            save_card(card, self.root)
        res = run_cli(["spawn", "--lane", "alpha", "--task", "one"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertEqual(CapabilityRegistry.load(self.root).get("JR1").max_allowed_lane_scope, [])


class TestTheReadmeSaysWhatWindowsDoes(unittest.TestCase):
    """#27: the install succeeds and the command does not exist."""

    def test_the_install_section_covers_store_python(self):
        readme = (Path(__file__).resolve().parents[1] / "README.md").read_text(encoding="utf-8")
        install = readme.split("### 1. Install", 1)[1].split("### 2.", 1)[0]
        self.assertIn("pip install --upgrade lanekeeper", install)
        self.assertIn("not recognized", install)
        self.assertIn("python -m lanekeeper.cli", install)


if __name__ == "__main__":
    unittest.main()
