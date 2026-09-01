import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from lanekeeper import paths
from lanekeeper.adapters.process_adapter import ProcessAdapter
from lanekeeper.cli import ensure_gitignore
from lanekeeper.config import Config
from lanekeeper.state import StateManager


class PathsTestCase(unittest.TestCase):
    """Isolates each test from the developer's own environment and cwd."""

    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)


class TestHomeDirname(PathsTestCase):
    """The directory name resolves from the environment, with a safe default."""

    def test_defaults_when_unset(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.home_dirname(self.root), ".lanekeeper")

    def test_environment_overrides_default(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            self.assertEqual(paths.home_dirname(self.root), ".agents")

    def test_blank_value_falls_back_to_default(self):
        for blank in ("", "   "):
            with self.subTest(blank=blank):
                with mock.patch.dict(os.environ, {paths.ENV_HOME: blank}):
                    self.assertEqual(paths.home_dirname(self.root), ".lanekeeper")

    def test_resolved_per_call_not_at_import(self):
        """A value set after import must still take effect."""
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".first"}):
            self.assertEqual(paths.home_dirname(self.root), ".first")
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".second"}):
            self.assertEqual(paths.home_dirname(self.root), ".second")


class TestHomeValidation(PathsTestCase):
    """An override that would escape the repository is refused, not obeyed."""

    def test_absolute_path_rejected(self):
        absolute = "C:\\lanekeeper" if os.name == "nt" else "/tmp/lanekeeper"
        with mock.patch.dict(os.environ, {paths.ENV_HOME: absolute}):
            with self.assertRaises(paths.InvalidHomeError):
                paths.home_dirname(self.root)

    def test_parent_traversal_rejected(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: "../outside"}):
            with self.assertRaises(paths.InvalidHomeError):
                paths.home_dirname(self.root)

    def test_nested_relative_name_allowed(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: "build/lanekeeper"}):
            self.assertEqual(paths.home_dirname(self.root), "build/lanekeeper")


class TestDerivedPaths(PathsTestCase):
    """Every path derives from the one directory name."""

    def test_joined_onto_root_when_given(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.config_path(self.root), self.root / ".lanekeeper" / "config.yaml")
            self.assertEqual(paths.state_dir(self.root), self.root / ".lanekeeper" / "state")
            self.assertEqual(paths.logs_dir(self.root), self.root / ".lanekeeper" / "logs")
            self.assertEqual(paths.worktrees_dir(self.root), self.root / ".lanekeeper" / "worktrees")
            self.assertEqual(paths.capabilities_dir(self.root), self.root / ".lanekeeper" / "capabilities")

    def test_override_reaches_every_derived_path(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            self.assertEqual(paths.home(self.root), self.root / ".agents")
            self.assertEqual(paths.config_path(self.root), self.root / ".agents" / "config.yaml")
            self.assertEqual(paths.state_dir(self.root), self.root / ".agents" / "state")
            self.assertEqual(paths.logs_dir(self.root), self.root / ".agents" / "logs")
            self.assertEqual(paths.capabilities_dir(self.root), self.root / ".agents" / "capabilities")
            self.assertEqual(paths.default_worktree_dir(self.root), ".agents/worktrees")
            self.assertEqual(
                paths.ignored_prefixes(self.root),
                (".agents/state/", ".agents/logs/", ".agents/worktrees/", ".agents/start/", ".git/"))
            self.assertEqual(paths.policy_paths(self.root),
                             (".agents/config.yaml", ".agents/capabilities/"))

    def test_display_strings_use_forward_slashes(self):
        """These are shown to users and written into files read on every platform."""
        with mock.patch.dict(os.environ, {}, clear=True):
            self.assertEqual(paths.display_config_path(self.root), ".lanekeeper/config.yaml")
            self.assertEqual(paths.display_capabilities_dir(self.root), ".lanekeeper/capabilities/")
            self.assertEqual(paths.default_worktree_dir(self.root), ".lanekeeper/worktrees")
            for value in (paths.display_config_path(self.root), paths.default_worktree_dir(self.root)):
                self.assertNotIn("\\", value)

    def test_ignored_prefixes_always_include_git(self):
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            self.assertIn(".git/", paths.ignored_prefixes(self.root))


class TestConsumersHonourOverride(PathsTestCase):
    """The override must reach real behaviour, not just the paths module."""

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

    def test_explicit_config_value_still_wins_over_default(self):
        """An operator's configured path is not overridden by the env default."""
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            cfg = Config.from_dict({"defaults": {"worktree_dir": "custom/trees"}})
            self.assertEqual(cfg.worktree_dir, "custom/trees")

    def test_generated_gitignore_follows_override(self):
        """A stale directory name here would let agent state reach a commit."""
        with mock.patch.dict(os.environ, {paths.ENV_HOME: ".agents"}):
            ensure_gitignore(self.root)
        content = (self.root / ".gitignore").read_text(encoding="utf-8")
        self.assertIn("/.agents/*", content)
        self.assertIn("!/.agents/config.yaml", content)
        self.assertNotIn(".lanekeeper", content)


if __name__ == "__main__":
    unittest.main()
