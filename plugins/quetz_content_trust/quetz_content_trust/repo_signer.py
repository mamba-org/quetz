import os
from pathlib import Path

import conda_content_trust.signing as cct_signing


class RepoSigner:
    def sign_repodata(self, repodata_fn, private_key):
        final_fn = self.in_folder / "repodata.json"

        cct_signing.sign_all_in_repodata(str(final_fn), private_key)

    def __init__(self, in_folder, private_key):
        self.in_folder = Path(in_folder).resolve()

        f = os.path.join(self.in_folder, "repodata.json")
        if os.path.isfile(f):
            self.sign_repodata(Path(f), private_key)
