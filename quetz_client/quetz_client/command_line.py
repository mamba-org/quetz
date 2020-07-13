# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import argparse
import requests
import os
from urllib.parse import urlparse, urlunparse

from conda_verify.verify import Verify

import quetz_client


def main():
    parser = argparse.ArgumentParser(
        usage="%(prog)s url package",
        description="Uploads package to Quetz."
    )

    parser.add_argument(
        "--verify-ignore",
        type=str,
        help="Ignore specific checks. Each check must be separated by a single comma")

    parser.add_argument(
        "-v", "--version", action="version",
        version=f"quetz-client version {quetz_client.__version__}"
    )

    parser.add_argument("channel_url")
    parser.add_argument("packages", nargs='+')
    args = parser.parse_args()

    channel_url = args.channel_url
    parts = urlparse(channel_url)
    if parts.path[:4] != "/api":
        parts = parts._replace(path=f"/api{parts.path}")
        channel_url = urlunparse(parts)

    verifier = Verify()

    verify_ignore = args.verify_ignore.split(',') if args.verify_ignore else None
    for package in args.packages:
        verifier.verify_package(path_to_package=package, checks_to_ignore=verify_ignore,
                                exit_on_error=True,)

    files = [('files', open(package, 'rb')) for package in args.packages]

    api_key = os.getenv('QUETZ_API_KEY')

    response = requests.post(f'{channel_url}/files/',
                             files=files,
                             headers={'X-API-Key': api_key})

    print(response.status_code)
