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
    parser.add_argument("packages", nargs='+')
    args = parser.parse_args()

    verifier = Verify()
    for package in args.packages:
        verifier.verify_package(path_to_package=package, exit_on_error=True)

    files = [('files', open(package, 'rb')) for package in args.packages]

    api_key = os.getenv('QUETZ_API_KEY')

    response = requests.post(f'{args.channel_url}/files/',
                             files=files,
                             headers={'X-API-Key': api_key})

    print(response.status_code)
