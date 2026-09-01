import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper.config import (
    Config,
    IntakeConfig,
    LaneConfig,
    PortRange,
    generate_default_config,
    load_config,
    save_config,
)


class TestConfig(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_generate_default_config(self):
        cfg = generate_default_config("MyTestApp")
        self.assertEqual(cfg.project_name, "MyTestApp")
        self.assertEqual(cfg.max_agents, 4)
        self.assertIn("backend", cfg.lanes)
        self.assertIn("frontend", cfg.lanes)
        self.assertEqual(cfg.port_ranges["backend"].start, 8001)
        self.assertEqual(cfg.port_ranges["backend"].end, 8099)
        self.assertEqual(cfg.database.strategy, "per-agent")

    def test_save_and_load_config(self):
        cfg = generate_default_config("SaveApp")
        saved_path = save_config(cfg, self.root)
        self.assertTrue(saved_path.exists())

        loaded = load_config(self.root)
        self.assertEqual(loaded.project_name, "SaveApp")
        self.assertEqual(loaded.max_agents, 4)
        self.assertEqual(len(loaded.lanes), len(cfg.lanes))
        self.assertEqual(loaded.database.name_template, "app_${AGENT_ID}")

    def test_custom_lane_config(self):
        cfg = generate_default_config("Custom")
        cfg.lanes["data"] = LaneConfig(
            name="data",
            allow=["data/**", "sql/**"],
            deny=["api/**"],
        )
        saved_path = save_config(cfg, self.root)
        loaded = load_config(self.root)
        self.assertIn("data", loaded.lanes)
        self.assertEqual(loaded.lanes["data"].allow, ["data/**", "sql/**"])
        self.assertEqual(loaded.lanes["data"].deny, ["api/**"])


class TestIntakeConfig(unittest.TestCase):
    """The intake section is absent from every configuration written before v0.7.

    A missing section must be a fully-defaulted one, or upgrading the tool would break
    a project that has one on disk — and a partially-set section must not silently lose
    the values the user did not mention.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_defaults(self):
        cfg = Config.default("x")
        self.assertEqual(cfg.intake.tracker, "github")
        self.assertEqual(cfg.intake.github.command, "gh")
        self.assertEqual(cfg.intake.spec_sources[0], "PRODUCT.md")
        self.assertIn("Scope", cfg.intake.spec_sections)

    def test_a_configuration_without_an_intake_section_still_loads(self):
        cfg = Config.default("legacy")
        data = cfg.to_dict()
        del data["intake"]
        path = Path(str(self.root)) / ".lanekeeper"
        path.mkdir(parents=True, exist_ok=True)
        (path / "config.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

        loaded = load_config(self.root)
        self.assertEqual(loaded.intake, IntakeConfig())

    def test_round_trip_preserves_an_edited_section(self):
        cfg = Config.default("edited")
        cfg.intake.tracker = "none"
        cfg.intake.github.repo = "kish21/parallel-agents"
        cfg.intake.thresholds.feature_match_score = 0.75
        cfg.intake.spec_sources = ["docs/PLAN.md"]
        save_config(cfg, self.root)

        loaded = load_config(self.root)
        self.assertEqual(loaded.intake.tracker, "none")
        self.assertEqual(loaded.intake.github.repo, "kish21/parallel-agents")
        self.assertEqual(loaded.intake.thresholds.feature_match_score, 0.75)
        self.assertEqual(loaded.intake.spec_sources, ["docs/PLAN.md"])

    def test_one_edited_threshold_does_not_drop_the_others(self):
        cfg = Config.default("partial")
        data = cfg.to_dict()
        data["intake"] = {"thresholds": {"thin_issue_count": 9}}
        path = Path(str(self.root)) / ".lanekeeper"
        path.mkdir(parents=True, exist_ok=True)
        (path / "config.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

        loaded = load_config(self.root)
        self.assertEqual(loaded.intake.thresholds.thin_issue_count, 9)
        self.assertEqual(loaded.intake.thresholds.feature_match_score,
                         IntakeConfig().thresholds.feature_match_score)
        self.assertEqual(loaded.intake.tracker, "github")


if __name__ == "__main__":
    unittest.main()
