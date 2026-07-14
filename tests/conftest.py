"""Shared pytest configuration for the my_lg test suite.

Adds the custom component's parent directory to sys.path so
`custom_components.my_lg` (and `my_lg` for modules that import each
other with relative `from . import ...`) can be imported without
installing the package, and applies a small defensive compatibility
shim for Home Assistant helper names that have moved across versions.
"""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
CUSTOM_COMPONENTS_DIR = REPO_ROOT / "custom_components"
TESTS_DIR = Path(__file__).resolve().parent

# Insert custom_components/ itself so `import my_lg` and my_lg's internal
# `from . import X` / `from .const import Y` relative imports resolve
# exactly like they do inside a real Home Assistant installation (where
# custom_components/my_lg is imported as a top-level package named
# "my_lg" via the custom_components namespace package machinery).
if str(CUSTOM_COMPONENTS_DIR) not in sys.path:
    sys.path.insert(0, str(CUSTOM_COMPONENTS_DIR))

# Insert tests/ itself so step definitions under tests/step_defs/ can do
# `import keywords` regardless of how pytest's own rootdir/conftest-based
# sys.path insertion behaves for the subdirectory they live in.
if str(TESTS_DIR) not in sys.path:
    sys.path.insert(0, str(TESTS_DIR))


def _apply_ha_compat_shims() -> None:
    """Backfill helper names across supported Home Assistant versions.

    `AddConfigEntryEntitiesCallback` was renamed/introduced at different
    points across Home Assistant releases; some pinned/cached versions
    only expose the older `AddEntitiesCallback`. Only fills the name in
    if it's actually missing, so this is a no-op (and safe) against any
    Home Assistant version that already has it.
    """
    from homeassistant.helpers import entity_platform

    if not hasattr(entity_platform, "AddConfigEntryEntitiesCallback"):
        entity_platform.AddConfigEntryEntitiesCallback = (
            entity_platform.AddEntitiesCallback
        )


_apply_ha_compat_shims()
