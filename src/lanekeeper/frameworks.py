"""Detects which environment variable names a project's frontend can actually read.

A generated `.env` that carries only port numbers does not connect anything. Every
browser build tool exposes a *subset* of the environment to client code, selected by
prefix: Vite exposes `VITE_*` and nothing else, Next.js exposes `NEXT_PUBLIC_*`, Create
React App exposes `REACT_APP_*`. A frontend handed `API_PORT=8002` therefore cannot see
it, falls through to whatever default is compiled into its source, and silently talks to
some other server — which is the precise failure this tool exists to prevent.

So the URL a frontend needs must be written under the prefix that frontend reads. This
module works out which prefixes apply by looking at the dependencies the repository
declares, and the result is written into `config.yaml` at `init` time as ordinary,
editable configuration — never applied from here at runtime.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Set

#: Dependency name -> the prefix that build tool exposes to client-side code.
CLIENT_ENV_PREFIX_BY_DEPENDENCY: Dict[str, str] = {
    "vite": "VITE_",
    "next": "NEXT_PUBLIC_",
    "react-scripts": "REACT_APP_",
    "nuxt": "NUXT_PUBLIC_",
    "@sveltejs/kit": "PUBLIC_",
    "gatsby": "GATSBY_",
    "expo": "EXPO_PUBLIC_",
    "@remix-run/react": "PUBLIC_",
    "astro": "PUBLIC_",
    "@angular/core": "NG_APP_",
}

#: Directories that never hold a project's own manifest.
IGNORED_DIRS = {
    ".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build",
    "target", "vendor", ".next", ".nuxt", "coverage", ".pytest_cache",
}

#: How deep to look for a manifest. A frontend normally sits at the root or one level
#: down (`frontend/`, `web/`, `apps/web/`), so two levels covers the realistic layouts
#: without walking a large repository.
MAX_MANIFEST_DEPTH = 2


def find_package_manifests(root: Path, max_depth: int = MAX_MANIFEST_DEPTH) -> List[Path]:
    """Locates `package.json` files near the top of the repository."""
    found: List[Path] = []

    def walk(directory: Path, depth: int) -> None:
        manifest = directory / "package.json"
        if manifest.is_file():
            found.append(manifest)
        if depth >= max_depth:
            return
        try:
            children = sorted(p for p in directory.iterdir() if p.is_dir())
        except OSError:
            return
        for child in children:
            if child.name in IGNORED_DIRS or child.name.startswith("."):
                continue
            walk(child, depth + 1)

    walk(root, 0)
    return found


def declared_dependencies(manifest: Path) -> Set[str]:
    """Every dependency name a manifest declares, across all dependency sections."""
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    if not isinstance(data, dict):
        return set()
    names: Set[str] = set()
    for section in ("dependencies", "devDependencies", "peerDependencies", "optionalDependencies"):
        block = data.get(section)
        if isinstance(block, dict):
            names.update(str(k) for k in block)
    return names


def detect_client_prefixes(root: Path) -> Set[str]:
    """The client-visible env prefixes this repository's frontends actually read."""
    prefixes: Set[str] = set()
    for manifest in find_package_manifests(root):
        for dependency in declared_dependencies(manifest):
            prefix = CLIENT_ENV_PREFIX_BY_DEPENDENCY.get(dependency)
            if prefix:
                prefixes.add(prefix)
    return prefixes


def default_url_templates(root: Path) -> Dict[str, str]:
    """Builds the `environment.url_templates` block to write into a new config.

    Three cases, in order of how much the repository tells us:

    * A recognised build tool  -> its prefix, so the browser bundle can read the URL.
    * A `package.json` but no recognised tool -> every known prefix, because guessing
      wrong here means silent cross-talk while an unused variable costs nothing.
    * No manifest at all -> the unprefixed pair only; this is not a JS project.

    Placeholders are expanded against the agent's own generated values, so every URL
    resolves to that agent's own ports. Unresolvable templates are dropped rather than
    emitted half-expanded — see ``EnvironmentManager.generate_env_vars``.
    """
    backend_url = "http://${HOST}:${BACKEND_PORT}"
    templates: Dict[str, str] = {
        "API_URL": backend_url,
        "BACKEND_URL": backend_url,
        "FRONTEND_URL": "http://${HOST}:${FRONTEND_PORT}",
    }

    manifests = find_package_manifests(root)
    if not manifests:
        return templates

    prefixes = detect_client_prefixes(root)
    if not prefixes:
        prefixes = set(CLIENT_ENV_PREFIX_BY_DEPENDENCY.values())

    for prefix in sorted(prefixes):
        templates[f"{prefix}API_URL"] = backend_url

    return templates
