import json
import os
import re

PLUGIN = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def test_manifest_matches_folder_and_has_no_root_flag():
    with open(os.path.join(PLUGIN, "plugin.json"), encoding="utf-8") as handle:
        manifest = json.load(handle)
    with open(os.path.join(PLUGIN, "package.json"), encoding="utf-8") as handle:
        package = json.load(handle)
    # Decky lists plugins by plugin.json name, so it is the display name the
    # panel uses. The id stays in package.json, the zip and the folder.
    with open(os.path.join(PLUGIN, "src", "index.tsx"), encoding="utf-8") as handle:
        source = handle.read()
    assert manifest["name"] == re.search(r'\nconst PLUGIN_NAME = "([^"]+)";', source).group(1)
    assert "\n    name: PLUGIN_NAME," in source
    assert "name={PLUGIN_NAME}" in source
    assert manifest["name"] != package["name"]
    assert manifest["api_version"] == 1
    assert "root" not in manifest["flags"] and "_root" not in manifest["flags"]
    assert package["type"] == "module"
