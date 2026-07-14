"""Print custom_components/my_lg/manifest.json's requirements, one per
line, so CI can `pip install -r` them without ever drifting out of sync
with what the integration actually declares it needs.
"""

import json

manifest = json.load(open("custom_components/my_lg/manifest.json", encoding="utf-8"))
print("\n".join(manifest.get("requirements", [])))
