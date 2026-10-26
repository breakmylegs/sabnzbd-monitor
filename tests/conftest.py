import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN = os.path.dirname(HERE)
ROOT = os.path.dirname(os.path.dirname(PLUGIN))

sys.path.insert(0, os.path.join(PLUGIN, "py_modules"))
# In the monorepo, plugin_core lives in shared/py until vendor_shared.py copies it.
if not os.path.isdir(os.path.join(PLUGIN, "py_modules", "plugin_core")):
    sys.path.insert(1, os.path.join(ROOT, "shared", "py"))
if os.path.isdir(os.path.join(ROOT, "tools")):
    sys.path.insert(1, os.path.join(ROOT, "tools"))
# In a mirror, the mock servers are vendored into tests/mocks.
elif os.path.isdir(os.path.join(HERE, "mocks")):
    sys.path.insert(1, os.path.join(HERE, "mocks"))
