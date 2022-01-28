import json
from pathlib import Path

if __name__ == "__main__":
    key_mgr_file = Path.cwd() / "test_quetz/channels/channel0/key_mgr.json"

    j = dict()
    with open(key_mgr_file, "r") as f:
        j = json.load(f)

    j["signed"]["delegations"]["pkg_mgr"]["pubkeys"] = ["some_new_key"]
    with open(key_mgr_file, "w") as f:
        json.dump(j, f)
