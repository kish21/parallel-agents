"""Reading feature slices out of a repository — and refusing to read layers as features.

The assertion that carries #23 is `test_a_layer_split_yields_no_slices`. `layout.py`'s
`ROLE_BY_DIR_NAME` reads `backend/` and `frontend/` as two things worth splitting; this
module has to read them as no statement about features at all, because a lane per layer
is the model the whole project argues against.
"""

import sys
import unittest
from pathlib import Path

from lanekeeper.config import DivideConfig, DivideThresholds
from lanekeeper.divide import codebase, names as naming

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _divide_fixtures import feature_files, layer_files  # noqa: E402


class CodebaseTestCase(unittest.TestCase):
    def setUp(self):
        self.settings = DivideConfig()

    def names(self, files, settings=None):
        found, _ = codebase.slices(Path("."), settings or self.settings, files=files)
        return [s.name for s in found]

    def test_a_name_on_both_sides_of_the_stack_is_a_feature(self):
        found = self.names(feature_files())
        self.assertIn("catalog", found)
        self.assertIn("checkout", found)
        self.assertIn("payments", found)

    def test_a_layer_split_yields_no_slices(self):
        """#23, mechanically. Two technology layers are not two features."""
        found = self.names(layer_files())
        self.assertEqual(found, [])
        for layer in ("backend", "frontend", "api", "models", "components", "pages"):
            self.assertNotIn(layer, found)

    def test_a_child_of_a_feature_container_counts_on_one_side_alone(self):
        files = [
            "services/domains/billing/charge.py",
            "services/domains/billing/refund.py",
            "services/main.py",
        ]
        self.assertIn("billing", self.names(files))

    def test_a_directory_below_the_file_threshold_is_not_a_slice(self):
        settings = DivideConfig(thresholds=DivideThresholds(min_slice_files=3))
        files = [
            "backend/app/domains/tiny/one.py",
            "frontend/src/components/tiny/One.tsx",
        ]
        self.assertEqual(self.names(files, settings), [])

    def test_the_root_threshold_is_configuration(self):
        """Proving the rule is a setting, not a constant buried in the code."""
        loose = DivideConfig(thresholds=DivideThresholds(min_slice_roots=1))
        files = ["backend/app/api/routes.py", "backend/app/api/handlers.py"]
        self.assertEqual(self.names(files), [])
        # With one root required, a directory that names something still has to get
        # past the generic-name list, which `api` does not.
        self.assertEqual(self.names(files, loose), [])

    def test_a_word_list_change_changes_the_reading(self):
        files = ["backend/app/reports/a.py", "frontend/src/reports/B.tsx"]
        self.assertIn("reports", self.names(files))
        blocked = DivideConfig(generic_dirs=DivideConfig().generic_dirs + ["reports"])
        self.assertNotIn("reports", self.names(files, blocked))

    def test_a_project_with_no_files_says_so_rather_than_proposing_nothing_quietly(self):
        """And says the true thing: nothing saved here yet, not "I failed to read it".

        The two look identical from here, and sending somebody to debug their setup
        when the answer is "this project is new" is the worse of the two mistakes.
        """
        found, note = codebase.slices(Path("."), self.settings, files=[])
        self.assertEqual(found, [])
        self.assertIn("no files saved in it yet", note)
        self.assertIn("from the tickets alone", note)

    def test_the_evidence_names_the_directories_it_read(self):
        found, _ = codebase.slices(Path("."), self.settings, files=feature_files())
        catalog = next(s for s in found if s.name == "catalog")
        self.assertEqual(catalog.evidence,
                         ("backend/app/domains/catalog",
                          "frontend/src/components/catalog"))
        self.assertTrue(all(p.endswith("/**") for p in catalog.paths))

    def test_a_filename_gives_up_its_words_rather_than_a_mash_of_them(self):
        """`useAuth.ts` is about auth. `useauth` is about nothing and is in no project."""
        settings = DivideConfig()
        self.assertEqual(naming.words_in_filename("useAuth.ts", settings), ["auth"])
        self.assertEqual(naming.from_filename("useAuth.ts", settings), "auth")
        self.assertEqual(naming.from_filename("LoginPage.tsx", settings), "login")
        self.assertEqual(naming.from_filename("index.ts", settings), "")
        self.assertIn("product", naming.words_in_filename("ProductGrid.tsx", settings))

    def test_a_feature_reaching_into_a_tree_by_filename_alone_is_found(self):
        """The `auth` case: a directory on one side, loose files on the other."""
        files = [
            "backend/app/auth/service.py",
            "backend/app/auth/tokens.py",
            "frontend/src/hooks/useAuth.ts",
            "frontend/src/store/authStore.ts",
        ]
        found, _ = codebase.slices(Path("."), self.settings, files=files)
        names = [s.name for s in found]
        self.assertIn("auth", names)
        auth = next(s for s in found if s.name == "auth")
        self.assertIn("frontend/src/hooks/useAuth.ts", auth.paths)

    def test_a_filename_alone_never_invents_a_feature(self):
        """Thin evidence. `format.ts` and `Button.tsx` name nothing worth splitting."""
        files = ["frontend/src/utils/format.ts", "frontend/src/utils/Button.tsx"]
        found, _ = codebase.slices(Path("."), self.settings, files=files)
        self.assertEqual([s.name for s in found], [])

    def test_the_reading_is_stable_across_file_order(self):
        files = feature_files()
        self.assertEqual(self.names(files), self.names(list(reversed(files))))


if __name__ == "__main__":
    unittest.main()
