import os
import shutil
from pathlib import Path

import conda_content_trust.signing as cct_signing


class RepoSigner:
    def sign_repodata(self, repodata_fn, pkg_mgr_key):
        final_fn = self.in_folder / "repodata_signed.json"
        print("copy", repodata_fn, final_fn)
        shutil.copyfile(repodata_fn, final_fn)

        cct_signing.sign_all_in_repodata(str(final_fn), pkg_mgr_key)
        print(f"Signed {final_fn}")

    def __init__(self, in_folder, pkg_mgr_key):
        self.in_folder = Path(in_folder).resolve()

        f = os.path.join(self.in_folder, "repodata.json")
        if os.path.isfile(f):
            self.sign_repodata(Path(f), pkg_mgr_key)
