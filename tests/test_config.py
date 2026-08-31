import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import (
    Config,
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


if __name__ == "__main__":
    unittest.main()
