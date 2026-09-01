"""Does the division recover the worked example's lanes from its paths alone?

#38 asks for this against MarkVid, the real 1,360-file product the example is modelled
on. That checkout is not on this machine, so this is the stand-in and is labelled as
one: `examples/feature-lanes.yaml` is that product's 17-lane split, so its own `allow`
patterns are turned back into a file tree and step 2 is asked to read the features out
of it, with nothing else to go on.

**What it actually recovers, measured rather than hoped for.** Nine lane names exactly
(`auth`, `cart`, `catalog`, `checkout`, `fulfilment`, `notifications`, `payments`,
`reviews`, `search`), and four more as the head word of a compound name — `admin` for
`admin-console`, `seller` for `seller-portal`, `pricing` and `promotions` for
`pricing-promotions`, `recommendations` for `recommendations-cost`. Thirteen of
seventeen, recognisably the same split.

The four it does not find are `platform`, `storefront`, `new-modules` and
`market-research` — and the example's own annotations call every one of them a residue
or greenfield lane rather than a feature slice. A reading of the files should not invent
them, so not finding them is the right answer, not a shortfall.
"""

import sys
import unittest
from pathlib import Path

import yaml

from lanekeeper.config import DivideConfig
from lanekeeper.divide import codebase

sys.path.insert(0, str(Path(__file__).resolve().parent))

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "feature-lanes.yaml"

#: Lanes the example describes as residue or greenfield rather than a feature slice.
NOT_FEATURE_SLICES = {"platform", "storefront", "new-modules", "market-research"}

#: Lanes whose name is a compound; the reading finds the feature, not the wording.
COMPOUND = {
    "admin-console": "admin",
    "seller-portal": "seller",
    "pricing-promotions": "pricing",
    "recommendations-cost": "recommendations",
}


def tree_from(document) -> list:
    """The example's own patterns, turned back into the files they describe."""
    files = []

    def expand(pattern):
        stem = pattern.replace("**", "").rstrip("/")
        if pattern.endswith("/**"):
            return [f"{stem}/one.py", f"{stem}/two.py"]
        if "*" in pattern:
            return [stem.replace("*", "x")]
        return [pattern]

    for body in (document.get("lanes") or {}).values():
        for pattern in (body or {}).get("allow", []):
            files += expand(pattern)
    for zone in (document.get("shared") or {}).values():
        for pattern in zone.get("paths", []):
            files += expand(pattern)
    return sorted({f for f in files if f})


class WorkedExampleTestCase(unittest.TestCase):
    def setUp(self):
        self.document = yaml.safe_load(EXAMPLE.read_text(encoding="utf-8"))
        self.files = tree_from(self.document)
        found, _ = codebase.slices(Path("."), DivideConfig(), files=self.files)
        self.found = {slice_.name for slice_ in found}

    def test_the_example_is_the_shape_this_test_assumes(self):
        self.assertGreater(len(self.files), 300)
        self.assertEqual(len(self.document["lanes"]), 17)

    def test_every_feature_slice_is_recovered(self):
        missed = []
        for name in self.document["lanes"]:
            if name in NOT_FEATURE_SLICES:
                continue
            if name in self.found or COMPOUND.get(name) in self.found:
                continue
            missed.append(name)
        self.assertEqual(missed, [], f"features the reading did not find: {missed}")

    def test_a_feature_with_a_directory_on_one_side_only_is_still_found(self):
        """`auth` owns a backend directory and, on the front end, loose files.

        Reading directories alone called that a one-sided name and dropped it — which
        is exactly the feature a technology-layer split gets wrong.
        """
        self.assertIn("auth", self.found)

    def test_no_technology_layer_is_proposed_as_a_feature(self):
        for layer in ("backend", "frontend", "app", "api", "db", "infra", "schemas",
                      "components", "pages", "data", "platform"):
            self.assertNotIn(layer, self.found)

    def test_the_residue_lanes_are_not_invented(self):
        """They are decisions about what is left over, not things the files can say."""
        for name in NOT_FEATURE_SLICES:
            self.assertNotIn(name, self.found)


if __name__ == "__main__":
    unittest.main()
