"""Import every my_lg platform module and print OK for each.

Run from inside custom_components/ so `import my_lg` resolves the same
way it does inside a real Home Assistant installation.
"""

import importlib
import os
import sys

# Running as `python path/to/check_imports.py` puts this script's own
# directory on sys.path, not the current working directory - so the
# working directory (expected to be custom_components/, per the
# workflow's `working-directory:` setting) has to be added explicitly
# for `import my_lg` to resolve.
sys.path.insert(0, os.getcwd())

# Defensive shim: some Home Assistant versions only expose the older
# AddEntitiesCallback name. Only fills it in if missing, so this is a
# no-op against any version that already has it.
from homeassistant.helpers import entity_platform

if not hasattr(entity_platform, "AddConfigEntryEntitiesCallback"):
    entity_platform.AddConfigEntryEntitiesCallback = entity_platform.AddEntitiesCallback

MODULES = [
    "my_lg",
    "my_lg.binary_sensor",
    "my_lg.climate",
    "my_lg.config_flow",
    "my_lg.const",
    "my_lg.coordinator_course",
    "my_lg.coordinator_pat",
    "my_lg.device_router",
    "my_lg.humidifier",
    "my_lg.mqtt",
    "my_lg.sensor",
    "my_lg.switch",
]

for name in MODULES:
    importlib.import_module(name)
    print(f"OK  {name}")
