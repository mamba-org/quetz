# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import argparse
import requests
import os
from conda_verify.verify import Verify
import quetz_client


def main():
    parser = argparse.ArgumentParser(
        usage="%(prog)s url package",
        description="Uploads package to Quetz."
    )
    parser.add_argument(
        "-v", "--version", action="version",
        version=f"quetz-client version {quetz_client.__version__}"
    )

    parser.add_argument("channel_url")
    parser.add_argument("package")
    args = parser.parse_args()

    verifier = Verify()

    verifier.verify_package(path_to_package=args.package, exit_on_error=True)

    head, tail = os.path.split(args.package)
    file_name = tail
    package_name = file_name.split('-')[0]

    files = [('files', open(args.package, 'rb'))]

    api_key = os.getenv('QUETZ_API_KEY')

    response = requests.post(f'{args.channel_url}/packages/{package_name}/files/',
                             files=files,
                             headers={'X-API-Key': api_key})

    print(response.status_code)
