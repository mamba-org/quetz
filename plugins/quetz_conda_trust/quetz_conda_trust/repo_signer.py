import os
import shutil
from pathlib import Path

import conda_content_trust.authentication as cct_authentication
import conda_content_trust.common as cct_common
import conda_content_trust.metadata_construction as cct_metadata_construction
import conda_content_trust.root_signing as cct_root_signing
import conda_content_trust.signing as cct_signing
import rich.console

console = rich.console.Console()


class RepoSigner:
    keys = {
        "root": [
            '1aed4d30459fa8bd8609ad4e0d182827ed6d3904',
            'c3b532977ffadc4095c676bea9a2880061e3662c',
        ],
        "key_mgr": [
            {
                "private": "c9c2060d7e0d93616c2654840b4983d00221d8b6b69c850107da74b42168f937",  # noqa: E501
                "public": "013ddd714962866d12ba5bae273f14d48c89cf0773dee2dbf6d4561e521c83f7",  # noqa: E501
            },
        ],
        "pkg_mgr": [
            {
                "private": "f3cdab14740066fb277651ec4f96b9f6c3e3eb3f812269797b9656074cd52133",  # noqa: E501
                "public": "f46b5a7caa43640744186564c098955147daa8bac4443887bc64d8bfee3d3569",  # noqa: E501
            }
        ],
    }

    def normalize_keys(self, keys):
        out = {}
        for ik, iv in keys.items():
            out[ik] = []
            for el in iv:
                if isinstance(el, str):
                    el = el.lower()
                    print(el)
                    keyval = cct_root_signing.fetch_keyval_from_gpg(el)
                    res = {"fingerprint": el, "public": keyval}
                elif isinstance(el, dict):
                    res = {
                        "private": el["private"].lower(),
                        "public": el["public"].lower(),
                    }
                out[ik].append(res)

        return out

    def create_root(self, keys):
        root_keys = keys["root"]

        root_pubkeys = [k["public"] for k in root_keys]
        key_mgr_pubkeys = [k["public"] for k in keys["key_mgr"]]

        root_version = 1

        root_md = cct_metadata_construction.build_root_metadata(
            root_pubkeys=root_pubkeys[0:1],
            root_threshold=1,
            root_version=root_version,
            key_mgr_pubkeys=key_mgr_pubkeys,
            key_mgr_threshold=1,
        )

        # Wrap the metadata in a signing envelope.
        root_md = cct_signing.wrap_as_signable(root_md)

        root_md_serialized_unsigned = cct_common.canonserialize(root_md)

        root_filepath = self.folder / f"{root_version}.root.json"

        print("Writing out: ", root_filepath)
        # Write unsigned sample root metadata.
        with open(root_filepath, "wb") as fout:
            fout.write(root_md_serialized_unsigned)

        # This overwrites the file with a signed version of the file.
        cct_root_signing.sign_root_metadata_via_gpg(
            root_filepath, root_keys[0]["fingerprint"]
        )

        # Load untrusted signed root metadata.
        signed_root_md = cct_common.load_metadata_from_file(root_filepath)

        cct_authentication.verify_signable(signed_root_md, root_pubkeys, 1, gpg=True)

        console.print("[green]Root metadata signed & verified!")

    def create_key_mgr(self, keys):

        private_key_key_mgr = cct_common.PrivateKey.from_hex(
            keys["key_mgr"][0]["private"]
        )
        pkg_mgr_pub_keys = [k["public"] for k in keys["pkg_mgr"]]
        key_mgr = cct_metadata_construction.build_delegating_metadata(
            metadata_type="key_mgr",  # 'root' or 'key_mgr'
            delegations={"pkg_mgr": {"pubkeys": pkg_mgr_pub_keys, "threshold": 1}},
            version=1,
            # timestamp   default: now
            # expiration  default: now plus root expiration default duration
        )

        key_mgr = cct_signing.wrap_as_signable(key_mgr)

        # sign dictionary in place
        cct_signing.sign_signable(key_mgr, private_key_key_mgr)

        key_mgr_serialized = cct_common.canonserialize(key_mgr)
        with open(self.folder / "key_mgr.json", "wb") as fobj:
            fobj.write(key_mgr_serialized)

        # let's run a verification
        root_metadata = cct_common.load_metadata_from_file(self.folder / "1.root.json")
        key_mgr_metadata = cct_common.load_metadata_from_file(
            self.folder / "key_mgr.json"
        )

        cct_common.checkformat_signable(root_metadata)

        if "delegations" not in root_metadata["signed"]:
            raise ValueError('Expected "delegations" entry in root metadata.')

        root_delegations = root_metadata["signed"]["delegations"]  # for brevity
        cct_common.checkformat_delegations(root_delegations)
        if "key_mgr" not in root_delegations:
            raise ValueError(
                'Missing expected delegation to "key_mgr" in root metadata.'
            )
        cct_common.checkformat_delegation(root_delegations["key_mgr"])

        # Doing delegation processing.
        cct_authentication.verify_delegation("key_mgr", key_mgr_metadata, root_metadata)

        console.print(
            "[green]Success: key mgr metadata verified based on root metadata."
        )

        return key_mgr

    def sign_repodata(self, repodata_fn, keys):
        final_fn = self.in_folder / "repodata_signed.json"
        print("copy", repodata_fn, final_fn)
        shutil.copyfile(repodata_fn, final_fn)

        pkg_mgr_key = keys["pkg_mgr"][0]["private"]
        cct_signing.sign_all_in_repodata(str(final_fn), pkg_mgr_key)
        console.print(f"[green]Signed [bold]{final_fn}[/bold]")

    def __init__(self, in_folder):
        self.in_folder = Path(in_folder).resolve()
        self.folder = self.in_folder.parent

        self.keys = self.normalize_keys(self.keys)
        console.print("Using keys:", self.keys)

        console.print("Using folder:", self.folder)

        self.create_root(self.keys)
        self.create_key_mgr(self.keys)
        f = os.path.join(self.in_folder, "repodata.json")
        if os.path.isfile(f):
            self.sign_repodata(Path(f), self.keys)
