"""The second source: the features a repository already has, read from its files.

The tickets are the first source and the better one — a filer stating which files their
work touches is a fact, and this is a reading. But a half-built project's tickets often
say less than its folder tree does, and on such a project going and reading the code is
the fallback, not an error.

**This module never uses `layout.ROLE_BY_DIR_NAME`.** That table answers "what kind of
code is this" and returns `backend`, which is the model #23 exists to remove. The
question here is "which feature is this", and the test that separates the two is whether
a name appears under more than one top-level root: `catalog` under `backend/…/domains/`
and again under `frontend/…/components/` is a feature slice, while `api` appearing only
under `backend/` is a layer inside one stack and is not proposed as anything.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Sequence, Tuple

from ..layout import tracked_files
from .models import CodeSlice
from . import names as naming


def slices(root: Path, settings, files: Sequence[str] = None) -> Tuple[List[CodeSlice], str]:
    """The feature slices this repository appears to have, and a note on the reading.

    The note is returned rather than logged because a proposal drawn from an unreadable
    tree and a proposal drawn from a tidy one look identical on the page, and only one
    of them deserves to be trusted.
    """
    listed = list(files) if files is not None else tracked_files(root)
    if not listed:
        # A project with nothing saved in it yet and a project whose file list could
        # not be read look identical from here, and telling somebody to go and debug
        # their setup when the true answer is "there is nothing here yet" is the worse
        # of the two mistakes.
        return [], ("This project has no files saved in it yet that I can see, so "
                    "everything below comes from the tickets alone.")

    directories = _feature_directories(listed, settings)
    by_name: Dict[str, List[str]] = defaultdict(list)
    for directory, name in directories.items():
        by_name[name].append(directory)
    named_files = _feature_files(listed, set(by_name), settings)

    thresholds = settings.thresholds
    feature_containers = {c.lower() for c in settings.feature_containers}

    found: List[CodeSlice] = []
    for name, dirs in sorted(by_name.items()):
        # A feature does not always have a directory on both sides. `auth` is the
        # standing example: a whole `backend/app/auth/` on one side, and on the other
        # `useAuth.ts`, `authStore.ts`, `LoginPage.tsx` sitting loose among their
        # neighbours. Reading only directories called it a one-sided name and dropped
        # it, which is exactly the feature a layer split gets wrong.
        files_named = named_files.get(name, [])
        roots = ({d.split("/")[0] for d in dirs}
                 | {f.split("/")[0] for f in files_named})
        under_feature_container = any(
            _parent_name(d) in feature_containers for d in dirs)
        # Appearing under two roots means the name survives a change of technology,
        # which is what makes it a feature rather than a layer. A child of `domains/`
        # or `features/` is one by construction and does not need the second root.
        if len(roots) < thresholds.min_slice_roots and not under_feature_container:
            continue
        file_count = sum(1 for f in listed if any(f.startswith(d + "/") for d in dirs))
        file_count += len(files_named)
        if file_count < thresholds.min_slice_files:
            continue
        found.append(CodeSlice(
            name=name,
            paths=tuple([f"{d}/**" for d in sorted(dirs)] + sorted(files_named)),
            file_count=file_count,
            evidence=tuple(sorted(dirs) + sorted(files_named)),
        ))

    note = (f"I read {len(listed)} files that this project keeps under version control."
            if found else
            f"I read {len(listed)} files that this project keeps under version "
            "control, and could not see any part of it that appears on both sides of "
            "the stack, so I have nothing to add to what the tickets say.")
    return found, note


def paths_for(name: str, found: Sequence[CodeSlice]) -> Tuple[str, ...]:
    """The paths of the slice with this name, or nothing."""
    for slice_ in found:
        if slice_.name == name:
            return slice_.paths
    return ()


def _feature_directories(files: Sequence[str], settings) -> Dict[str, str]:
    """Every directory that names a feature, mapped to the name it carries."""
    result: Dict[str, str] = {}
    for path in files:
        parts = path.split("/")
        for depth in range(1, len(parts)):
            directory = "/".join(parts[:depth])
            if directory in result:
                continue
            name = _directory_name(directory, settings)
            if name:
                result[directory] = name
    return result


def _feature_files(files: Sequence[str], known: set, settings) -> Dict[str, List[str]]:
    """Files whose own name says which feature they serve.

    Only for names a directory has already established. A filename alone is thin
    evidence — `format.ts` and `Button.tsx` name nothing — and inventing features from
    it would fill the proposal with words nobody would recognise. Used to answer one
    question: does a feature this project demonstrably has also reach into a part of
    the tree that has no directory for it?
    """
    result: Dict[str, List[str]] = defaultdict(list)
    for path in files:
        parent_parts = path.split("/")[:-1]
        for name in naming.words_in_filename(path.split("/")[-1], settings):
            if name not in known:
                continue
            if parent_parts[-1:] == [name]:
                break                # already covered by its own directory
            result[name].append(path)
            break                    # one file belongs to one feature
    return result


def _directory_name(directory: str, settings) -> str:
    """The feature a directory names, judged on its own last segment.

    `candidates` is asked about the directory as a path, and only a name coming from
    the last segment counts: `backend/app/domains/catalog` names `catalog`, while
    `backend/app/domains` names nothing at all.
    """
    last = directory.split("/")[-1]
    if last.startswith(".") or "." in last:
        return ""
    found = naming.candidates(directory, settings)
    return found[0] if found and found[0] == last.lower() else ""


def _parent_name(directory: str) -> str:
    parts = directory.split("/")
    return parts[-2].lower() if len(parts) > 1 else ""
