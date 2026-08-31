import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lanekeeper import paths
from lanekeeper.adapters.process_adapter import ProcessAdapter
from lanekeeper.config import Config
from lanekeeper.state import StateManager


class TestHomeDirname(unittest.TestCase):
    """The directory name resolves from the environment, with a safe default."""

    def test_defaults_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.home_dirname(), ".lanekeeper")

    def test_environment_overrides_default(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            self.assertEqual(paths.home_dirname(), ".agents")

    def test_blank_value_falls_back_to_default(self):
        for blank in ("", "   "):
            with self.subTest(blank=blank):
                with mock.patch.dict(os.environ, {paths.ENV_HOME: blank}):
                    self.assertEqual(paths.home_dirname(), ".lanekeeper")

    def test_resolved_per_call_not_at_import(self):
        """A value set after import must still take effect."""
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".first"}):
            self.assertEqual(paths.home_dirname(), ".first")
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".second"}):
            self.assertEqual(paths.home_dirname(), ".second")


class TestHomeValidation(unittest.TestCase):
    """An override that would escape the repository is refused, not obeyed."""

    def test_absolute_path_rejected(self):
        absolute = "C:\\lanekeeper" if os.name == "nt" else "/tmp/lanekeeper"
        with mock.patch.dict(os.environ, {paths.ENV_HOME: absolute}):
            with self.assertRaises(paths.InvalidHomeError):
                paths.home_dirname()

    def test_parent_traversal_rejected(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: "../outside"}):
            with self.assertRaises(paths.InvalidHomeError):
                paths.home_dirname()

    def test_nested_relative_name_allowed(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: "build/lanekeeper"}):
            self.assertEqual(paths.home_dirname(), "build/lanekeeper")


class TestDerivedPaths(unittest.TestCase):
    """Every path derives from the one directory name."""

    def test_relative_when_no_root_given(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.config_path(), Path(".lanekeeper/config.yaml"))
            self.assertEqual(paths.state_dir(), Path(".lanekeeper/state"))
            self.assertEqual(paths.logs_dir(), Path(".lanekeeper/logs"))
            self.assertEqual(paths.worktrees_dir(), Path(".lanekeeper/worktrees"))

    def test_joined_onto_root_when_given(self):
        root = Path("repo")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.config_path(root), root / ".lanekeeper" / "config.yaml")
            self.assertEqual(paths.state_dir(root), root / ".lanekeeper" / "state")

    def test_override_reaches_every_derived_path(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            self.assertEqual(paths.home(), Path(".agents"))
            self.assertEqual(paths.config_path(), Path(".agents/config.yaml"))
            self.assertEqual(paths.state_dir(), Path(".agents/state"))
            self.assertEqual(paths.logs_dir(), Path(".agents/logs"))
            self.assertEqual(paths.worktrees_dir(), Path(".agents/worktrees"))
            self.assertEqual(paths.default_worktree_dir(), ".agents/worktrees")
            self.assertEqual(paths.ignored_prefixes(), (".agents/", ".git/"))

    def test_default_worktree_dir_uses_forward_slashes(self):
        """The value is written into a config file read on every platform."""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.default_worktree_dir(), ".lanekeeper/worktrees")
            self.assertNotIn("\\", paths.default_worktree_dir())

    def test_ignored_prefixes_always_include_git(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            self.assertIn(".git/", paths.ignored_prefixes())


class TestConsumersHonourOverride(unittest.TestCase):
    """The override must reach real behaviour, not just the paths module."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def test_state_manager_writes_under_overridden_home(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            StateManager(self.root)
        self.assertTrue((self.root / ".agents" / "state" / "agents.json").exists())
        self.assertFalse((self.root / ".lanekeeper").exists())

    def test_process_adapter_writes_logs_under_overridden_home(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            ProcessAdapter(self.root)
        self.assertTrue((self.root / ".agents" / "logs").is_dir())
        self.assertFalse((self.root / ".lanekeeper").exists())

    def test_default_config_worktree_dir_follows_override(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            self.assertEqual(Config.default("demo").worktree_dir, ".agents/worktrees")
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(Config.default("demo").worktree_dir, ".lanekeeper/worktrees")

    def test_explicit_config_value_still_wins_over_default(self):
        """An operator's configured path is not overridden by the env default."""
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            cfg = Config.from_dict({"defaults": {"worktree_dir": "custom/trees"}})
            self.assertEqual(cfg.worktree_dir, "custom/trees")


if __name__ == "__main__":
    unittest.main()
