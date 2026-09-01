"""Finding the product description that coverage is judged against.

The order of preference is the whole point: PRODUCT.md is product-playbook's own output
and the intended path; a README is the fallback; nothing is an honest answer that must
not be papered over.
"""

import tempfile
import unittest
from pathlib import Path

from lanekeeper.config import IntakeConfig
from lanekeeper.intake.models import SpecSource
from lanekeeper.intake.spec import extract_features, resolve_spec

PRODUCT_MD = """# MyApp

## Vision
Something inspiring.

## Scope
- Checkout — cart to confirmed order
- Search
- **Billing**

### Out of scope
- Mobile app

## Plan
- Recommendations
"""

README_MD = """# MyApp

## Features
- Uploads
- Sharing
"""


class TestResolveSpec(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.settings = IntakeConfig()

    def tearDown(self):
        self.tmp.cleanup()

    def _write(self, name, text):
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def test_product_md_is_preferred_over_readme(self):
        self._write("PRODUCT.md", PRODUCT_MD)
        self._write("README.md", README_MD)
        spec = resolve_spec(self.root, self.settings)
        self.assertIs(spec.source, SpecSource.PRODUCT_MD)
        self.assertEqual(spec.path, "PRODUCT.md")
        names = [f.name for f in spec.features]
        self.assertIn("Checkout", names)
        self.assertNotIn("Uploads", names)

    def test_readme_is_the_fallback(self):
        self._write("README.md", README_MD)
        spec = resolve_spec(self.root, self.settings)
        self.assertIs(spec.source, SpecSource.DOCS)
        self.assertEqual([f.name for f in spec.features], ["Uploads", "Sharing"])

    def test_nothing_to_compare_against_is_an_answer(self):
        spec = resolve_spec(self.root, self.settings)
        self.assertIs(spec.source, SpecSource.NONE)
        self.assertFalse(spec.has_features)
        self.assertEqual(spec.path, None)

    def test_a_product_md_without_a_feature_section_falls_through(self):
        self._write("PRODUCT.md", "# MyApp\n\n## Vision\nSomething.\n")
        self._write("README.md", README_MD)
        spec = resolve_spec(self.root, self.settings)
        self.assertIs(spec.source, SpecSource.DOCS)
        self.assertEqual(spec.path, "README.md")
        # Both files were looked at, so a bad read is visible rather than silent.
        self.assertEqual(spec.considered, ("PRODUCT.md", "README.md"))

    def test_the_source_list_is_configuration(self):
        self._write("docs/plan.md", "## Scope\n- Imports\n")
        settings = IntakeConfig(spec_sources=["docs/plan.md"])
        spec = resolve_spec(self.root, settings)
        self.assertEqual([f.name for f in spec.features], ["Imports"])


class TestExtractFeatures(unittest.TestCase):
    def test_reads_only_the_configured_sections(self):
        features = [f.name for f in extract_features(PRODUCT_MD, ["Scope", "Plan"])]
        self.assertEqual(features, ["Checkout", "Search", "Billing", "Recommendations"])

    def test_out_of_scope_is_not_a_feature_list(self):
        names = [f.name for f in extract_features(PRODUCT_MD, ["Scope"])]
        self.assertNotIn("Mobile app", names)

    def test_the_name_is_the_feature_not_the_sentence(self):
        text = "## Scope\n- Billing — Stripe checkout, invoices and refunds\n"
        self.assertEqual([f.name for f in extract_features(text, ["Scope"])], ["Billing"])

    def test_markup_and_links_are_stripped(self):
        text = "## Scope\n- [`Voice`](docs/voice.md)\n"
        self.assertEqual([f.name for f in extract_features(text, ["Scope"])], ["Voice"])

    def test_task_list_boxes_and_numbers_are_bullets(self):
        text = "## Plan\n1. Uploads\n- [ ] Exports\n"
        self.assertEqual([f.name for f in extract_features(text, ["Plan"])],
                         ["Uploads", "Exports"])

    def test_collection_stops_at_the_next_section(self):
        text = "## Scope\n- Checkout\n\n## Risks\n- Vendor lock-in\n"
        self.assertEqual([f.name for f in extract_features(text, ["Scope"])], ["Checkout"])


class TestAwkwardDocuments(unittest.TestCase):
    """The documents people actually write, not the tidy one in the example."""

    def test_a_code_block_does_not_end_the_feature_list(self):
        # A `# comment` inside a fenced block looks exactly like a level-1 heading, and
        # treating it as one silently swallowed every feature listed after it — the
        # worst shape of bug here, because the result is a confident false COVERED.
        text = ("## Scope\n"
                "- Checkout\n\n"
                "```bash\n"
                "# install the dependencies\n"
                "npm install\n"
                "```\n\n"
                "- Billing\n")
        self.assertEqual([f.name for f in extract_features(text, ["Scope"])],
                         ["Checkout", "Billing"])

    def test_a_colon_separates_a_name_from_its_explanation(self):
        text = "## Scope\n- **Billing**: Stripe checkout, invoices and refunds\n"
        self.assertEqual([f.name for f in extract_features(text, ["Scope"])], ["Billing"])

    def test_a_hyphenated_name_survives(self):
        text = "## Scope\n- Auto-save\n"
        self.assertEqual([f.name for f in extract_features(text, ["Scope"])], ["Auto-save"])

    def test_an_in_scope_section_after_an_exclusion_is_read_again(self):
        text = ("## Scope\n"
                "### Core\n- Checkout\n"
                "### Out of scope\n- Mobile app\n"
                "### Later\n- Billing\n")
        self.assertEqual([f.name for f in extract_features(text, ["Scope"])],
                         ["Checkout", "Billing"])


class TestConfiguredPathsStayInTheProject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_a_source_climbing_out_of_the_project_is_refused(self):
        # A configured path is joined onto the repository root, so `..` or an absolute
        # path would read a file outside the project — the same thing `paths` refuses
        # for lanekeeper's own directory.
        outside = self.root.parent / "OUTSIDE_SPEC.md"
        outside.write_text("## Scope\n- Secrets\n", encoding="utf-8")
        try:
            settings = IntakeConfig(spec_sources=["../OUTSIDE_SPEC.md", str(outside)])
            spec = resolve_spec(self.root, settings)
            self.assertIs(spec.source, SpecSource.NONE)
            self.assertEqual(spec.considered, ())
        finally:
            outside.unlink()




if __name__ == "__main__":
    unittest.main()
