"""Repositories and backlogs the step-2 tests divide.

The big one is the tree behind `examples/feature-lanes.yaml` — a mid-size e-commerce
SaaS split into feature slices, modelled on a real 1,360-file product. It is here
because it is the case #38 cares about: a repository that a technology-layer split gets
wrong, where every feature owns files on both sides of the stack.
"""

from lanekeeper.trackers.base import TrackedIssue

#: Feature slices, each owning backend and frontend files, as the worked example does.
FEATURE_TREE = {
    "catalog": [
        "backend/app/domains/catalog/service.py",
        "backend/app/domains/catalog/repository.py",
        "frontend/src/components/catalog/ProductGrid.tsx",
        "frontend/src/components/catalog/ProductCard.tsx",
    ],
    "checkout": [
        "backend/app/domains/checkout/service.py",
        "backend/app/domains/checkout/addresses.py",
        "frontend/src/components/checkout/CartSummary.tsx",
    ],
    "payments": [
        "backend/app/domains/payments/service.py",
        "backend/app/domains/payments/stripe_provider.py",
        "frontend/src/components/payments/PayButton.tsx",
    ],
    "auth": [
        "backend/app/domains/auth/service.py",
        "frontend/src/components/auth/LoginForm.tsx",
    ],
    "reviews": [
        "backend/app/domains/reviews/service.py",
        "frontend/src/components/reviews/ReviewList.tsx",
    ],
}

#: Files owned by no feature: the spine every slice plugs into.
SHARED_FILES = [
    "backend/app/main.py",
    "backend/app/config/settings.py",
    "frontend/src/App.tsx",
    "README.md",
]


def feature_files():
    """Every tracked file in the feature-organised repository."""
    files = [path for paths in FEATURE_TREE.values() for path in paths]
    return sorted(files + SHARED_FILES)


def layer_files():
    """A repository laid out purely by technology layer.

    `ROLE_BY_DIR_NAME` reads this as `backend` and `frontend`. Step 2 must read it as
    nothing at all rather than proposing two layers as if they were features.
    """
    return sorted([
        "backend/app/api/routes.py",
        "backend/app/api/handlers.py",
        "backend/app/models/user.py",
        "frontend/src/components/Button.tsx",
        "frontend/src/pages/Home.tsx",
        "frontend/src/utils/format.ts",
    ])


def ticket(ref, title, paths=(), lane="", body_extra=""):
    """A ticket as the issue form renders it into a GitHub issue body."""
    sections = [f"### What needs to be done?\n\n{title}\n"]
    if lane:
        sections.insert(0, f"### Lane (which feature this belongs to)\n\n{lane}\n")
    if body_extra:
        sections.append(f"### Evidence\n\n{body_extra}\n")
    listed = "\n".join(paths) if paths else "_No response_"
    sections.append(f"### Allowed File Paths\n\n{listed}\n")
    return TrackedIssue(ref=str(ref), title=title, body="\n".join(sections),
                        labels=("task",), state="open",
                        url=f"https://example.test/{ref}")


def feature_backlog():
    """Tickets filed through the form against the feature-organised repository."""
    return [
        ticket(1, "Show variant pictures on the product page",
               ["backend/app/domains/catalog/service.py",
                "frontend/src/components/catalog/ProductGrid.tsx"]),
        ticket(2, "Sort the product grid by price",
               ["frontend/src/components/catalog/ProductCard.tsx",
                "backend/app/domains/catalog/repository.py"]),
        ticket(3, "Collect a delivery address before payment",
               ["backend/app/domains/checkout/addresses.py",
                "frontend/src/components/checkout/CartSummary.tsx"]),
        ticket(4, "Retry a declined card once",
               ["backend/app/domains/payments/stripe_provider.py"]),
        ticket(5, "Sign in with a one-time code",
               ["backend/app/domains/auth/service.py",
                "frontend/src/components/auth/LoginForm.tsx"]),
    ]
