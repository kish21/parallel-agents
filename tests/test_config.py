import tempfile
import unittest
from pathlib import Path

import yaml

from lanekeeper.config import (
    Config,
    DivideConfig,
    IntakeConfig,
    InvalidDivideSettingError,
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


class TestDivideConfig(unittest.TestCase):
    """The divide section, absent from every configuration written before v0.7.

    Same contract as the intake section above, plus one of its own: `advisor` has no
    implementation other than `none`, so a configuration asking for another one is
    refused rather than accepted and quietly ignored.
    """

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def _write(self, data):
        path = Path(str(self.root)) / ".lanekeeper"
        path.mkdir(parents=True, exist_ok=True)
        (path / "config.yaml").write_text(yaml.safe_dump(data), encoding="utf-8")

    def test_defaults(self):
        cfg = Config.default("x")
        self.assertEqual(cfg.divide.advisor, "none")
        self.assertEqual(cfg.divide.lane_file, "lanes.yaml")
        self.assertEqual(cfg.divide.thresholds.min_group_tickets, 2)
        self.assertIn("backend", cfg.divide.containers)

    def test_a_configuration_without_a_divide_section_still_loads(self):
        data = Config.default("legacy").to_dict()
        del data["divide"]
        self._write(data)
        self.assertEqual(load_config(self.root).divide, DivideConfig())

    def test_round_trip_preserves_an_edited_section(self):
        cfg = Config.default("edited")
        cfg.divide.thresholds.min_group_tickets = 4
        cfg.divide.generic_dirs = ["widgets"]
        cfg.divide.lane_file = "config/lanes.yaml"
        save_config(cfg, self.root)
        loaded = load_config(self.root)
        self.assertEqual(loaded.divide.thresholds.min_group_tickets, 4)
        self.assertEqual(loaded.divide.generic_dirs, ["widgets"])
        self.assertEqual(loaded.divide.lane_file, "config/lanes.yaml")

    def test_one_edited_threshold_does_not_lose_the_others(self):
        data = Config.default("partial").to_dict()
        data["divide"] = {"thresholds": {"min_slice_files": 7}}
        self._write(data)
        loaded = load_config(self.root)
        self.assertEqual(loaded.divide.thresholds.min_slice_files, 7)
        self.assertEqual(loaded.divide.thresholds.min_group_tickets, 2)

    def test_an_advisor_that_does_not_exist_is_refused(self):
        """Never accepted and ignored: that would promise a behaviour that is absent."""
        data = Config.default("advised").to_dict()
        data["divide"] = {"advisor": "gpt"}
        self._write(data)
        with self.assertRaises(InvalidDivideSettingError) as ctx:
            load_config(self.root)
        self.assertIn("divide.advisor", str(ctx.exception))

    def test_an_unusable_threshold_names_the_setting(self):
        data = Config.default("bad").to_dict()
        data["divide"] = {"thresholds": {"min_group_tickets": "two"}}
        self._write(data)
        with self.assertRaises(InvalidDivideSettingError) as ctx:
            load_config(self.root)
        self.assertIn("divide.thresholds.min_group_tickets", str(ctx.exception))

    def test_a_feature_slice_spanning_the_stack_is_not_flagged_as_too_broad(self):
        """The threshold parked for #38: a slice spans backend, frontend and tests.

        At the old default of 3 a correctly written ticket tripped the flag that exists
        to catch a ticket which is really several. The default is now 5; a project that
        wants the old behaviour still sets it.
        """
        self.assertEqual(Config.default("x").intake.thresholds.broad_ticket_areas, 5)
        data = Config.default("kept").to_dict()
        data["intake"]["thresholds"]["broad_ticket_areas"] = 3
        self._write(data)
        self.assertEqual(load_config(self.root).intake.thresholds.broad_ticket_areas, 3)


if __name__ == "__main__":
    unittest.main()
