"""Detection of the env-var prefixes a repository's frontends can actually read."""

import json
import tempfile
import unittest
from pathlib import Path

from lanekeeper.frameworks import (
    declared_dependencies,
    default_url_templates,
    detect_client_prefixes,
    find_package_manifests,
)


class TestFrameworkDetection(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.tmp_dir.name, ignore_errors=True)

    def _manifest(self, relative: str, deps: dict, section: str = "devDependencies"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({section: deps}), encoding="utf-8")
        return path

    def test_detects_vite_in_a_subdirectory(self):
        self._manifest("frontend/package.json", {"vite": "^5.4.0"})
        self.assertEqual(detect_client_prefixes(self.root), {"VITE_"})

    def test_detects_next_and_reports_its_public_prefix(self):
        self._manifest("package.json", {"next": "15.0.0"}, section="dependencies")
        self.assertEqual(detect_client_prefixes(self.root), {"NEXT_PUBLIC_"})

    def test_detects_several_frontends_in_one_repository(self):
        self._manifest("apps/web/package.json", {"next": "15.0.0"})
        self._manifest("apps/admin/package.json", {"vite": "^5.0.0"})
        self.assertEqual(detect_client_prefixes(self.root), {"NEXT_PUBLIC_", "VITE_"})

    def test_ignores_node_modules(self):
        self._manifest("node_modules/vite/package.json", {"vite": "^5.0.0"})
        self.assertEqual(find_package_manifests(self.root), [])

    def test_malformed_manifest_is_not_fatal(self):
        path = self.root / "package.json"
        path.write_text("{ not json", encoding="utf-8")
        self.assertEqual(declared_dependencies(path), set())
        self.assertEqual(detect_client_prefixes(self.root), set())

    def test_vite_project_gets_a_vite_readable_api_url(self):
        """The regression this module exists for.

        A Vite bundle can only read `VITE_*`. Without this variable the frontend falls
        through to whatever server is compiled into its source — in the field, another
        agent's backend, or an unrelated process on the default port.
        """
        self._manifest("frontend/package.json", {"vite": "^5.4.0"})
        templates = default_url_templates(self.root)
        self.assertIn("VITE_API_URL", templates)
        self.assertEqual(templates["VITE_API_URL"], "http://${HOST}:${BACKEND_PORT}")

    def test_non_javascript_project_gets_no_frontend_prefixes(self):
        (self.root / "main.py").write_text("print('hi')\n", encoding="utf-8")
        templates = default_url_templates(self.root)
        self.assertEqual(set(templates), {"API_URL", "BACKEND_URL", "FRONTEND_URL"})

    def test_unrecognised_javascript_project_gets_every_known_prefix(self):
        """Guessing wrong costs an unused variable; guessing nothing costs cross-talk."""
        self._manifest("package.json", {"some-unknown-bundler": "1.0.0"})
        templates = default_url_templates(self.root)
        self.assertIn("VITE_API_URL", templates)
        self.assertIn("NEXT_PUBLIC_API_URL", templates)


if __name__ == "__main__":
    unittest.main()
