"""`init` splits by feature, not by technology layer — issue #23.

The mechanism never needed changing: a lane is an allow-list of globs, and a feature
lane is one that lists a slice of every layer. What was wrong was the default. On a
feature-organised repository `init` still wrote backend/frontend/platform, which is
the split that turns an ordinary ticket — service, schema, route, page, test — into a
four-way escalation against four lanes.
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import load_config

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _cli_harness import output_of, run_cli  # noqa: E402


def _git(root, *args):
    return subprocess.run(["git", *args], cwd=str(root), check=True,
                          capture_output=True, text=True, encoding="utf-8")


class RepoTestCase(unittest.TestCase):
    files: tuple = ()

    def setUp(self):
        self.root = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, str(self.root), ignore_errors=True)
        _git(self.root, "init", "-q", "-b", "main", ".")
        _git(self.root, "config", "user.email", "t@t.c")
        _git(self.root, "config", "user.name", "t")
        for rel in self.files:
            target = self.root / rel
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("x\n", encoding="utf-8")
        _git(self.root, "add", "-A")
        _git(self.root, "commit", "-qm", "init")


class TestFeatureOrganisedRepository(RepoTestCase):
    """Every name here appears on both sides of the stack, which is what makes it a
    feature and not a layer."""

    files = (
        "backend/app/modules/checkout/service.py",
        "backend/app/modules/checkout/schema.py",
        "backend/app/modules/catalog/service.py",
        "backend/app/modules/catalog/schema.py",
        "frontend/src/components/checkout/CheckoutPage.tsx",
        "frontend/src/components/checkout/Cart.tsx",
        "frontend/src/components/catalog/CatalogList.tsx",
        "frontend/src/components/catalog/Item.tsx",
    )

    def test_lanes_are_features(self):
        res = run_cli(["init", "--name", "Shop"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        lanes = load_config(self.root).lanes
        self.assertIn("checkout", lanes, output_of(res))
        self.assertIn("catalog", lanes, output_of(res))
        self.assertNotIn("backend", lanes, output_of(res))
        self.assertNotIn("frontend", lanes, output_of(res))

    def test_a_feature_lane_owns_both_sides_of_the_stack(self):
        run_cli(["init", "--name", "Shop"], cwd=self.root)
        allow = load_config(self.root).lanes["checkout"].allow
        joined = " ".join(allow)
        self.assertIn("backend/app/modules/checkout", joined)
        self.assertIn("frontend/src/components/checkout", joined)

    def test_it_does_not_call_them_technology_layers(self):
        res = run_cli(["init", "--name", "Shop"], cwd=self.root)
        self.assertIn("feature slices", res.stdout, output_of(res))
        self.assertNotIn("These are technology layers", res.stdout, output_of(res))

    def test_layers_flag_still_gives_the_old_split(self):
        res = run_cli(["init", "--name", "Shop", "--layers"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        lanes = load_config(self.root).lanes
        self.assertNotIn("checkout", lanes, output_of(res))
        self.assertIn("These are technology layers", res.stdout, output_of(res))


class TestLayerOrganisedRepository(RepoTestCase):
    """No name repeats across the stack, so there is no feature to find and the
    fallback has to keep working — and keep saying what it is."""

    files = (
        "backend/api/routes.py",
        "backend/api/handlers.py",
        "backend/db/models.py",
        "frontend/src/App.tsx",
        "frontend/src/index.tsx",
    )

    def test_falls_back_to_layers_and_says_so(self):
        res = run_cli(["init", "--name", "Layered"], cwd=self.root)
        self.assertEqual(res.returncode, 0, output_of(res))
        self.assertIn("These are technology layers", res.stdout, output_of(res))


if __name__ == "__main__":
    unittest.main()
