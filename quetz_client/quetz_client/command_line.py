# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import argparse
import os
import sys
import webbrowser
from urllib.parse import urljoin, urlparse, urlunparse

import appdirs
import requests
import toml

try:
    from conda_verify.verify import Verify

    verify_available = True
except ImportError:
    verify_available = False

import quetz_client

ALLOWED_SUBCOMMANDS = ["upload", "apikey", "create-channel"]

config_dir = appdirs.user_config_dir("quetz_client")
api_keys_location = os.path.join(config_dir, 'config.toml')


def get_installed_api_key(address):
    parsed_server = urlparse(address)
    server = parsed_server.netloc

    if os.environ.get('QUETZ_API_KEY'):
        return os.environ['QUETZ_API_KEY']

    if os.path.exists(api_keys_location):
        keys = toml.load(api_keys_location)
    else:
        raise RuntimeError(f"No API Key for {parsed_server.netloc} found.")
    if keys.get(server):
        return keys[server]


def get_api_key(args):
    parsed_server = urlparse(args.server)

    api_keys_frontend = urljoin(args.server, "/#/api-keys")
    webbrowser.open_new_tab(api_keys_frontend)
    print("Please paste the API key:")
    api_key = input()

    if not os.path.exists(config_dir):
        os.makedirs(config_dir)

    if os.path.exists(api_keys_location):
        with open(api_keys_location) as fo:
            keys = toml.load(api_keys_location)
    else:
        keys = {}
    keys.update({parsed_server.netloc: api_key})

    with open(api_keys_location, 'w') as fo:
        toml.dump(keys, fo)


def create_channel(args):
    url = urljoin(args.server, '/api/channels')
    api_key = get_installed_api_key(args.server)
    json_data = {
        "name": args.name,
        "description": args.description,
        "private": args.private,
        # "mirror_channel_url": "string",
        # "mirror_mode": "string"
    }
    response = requests.post(url, json=json_data, headers={'X-API-Key': api_key})
    print(response.json())


def urljoin_all(pieces):
    parts = urlparse(pieces[0])
    result = urljoin(f'{parts.scheme}://{parts.netloc}', '/'.join(pieces))
    return result


def upload_packages(args):
    channel = args.channel
    if channel.isalnum():
        # this looks like a channel name, no URL given
        print(f"Posting file to {channel}")
        channel_url = urljoin_all([args.server, "api/channels", channel])
        print("Channel url: ", channel_url)
    else:
        parts = urlparse(channel)
        if parts.path[:4] != "/api":
            parts = parts._replace(path=f"/api{parts.path}")
            channel_url = urlunparse(parts)
        else:
            channel_url = channel

    package_file_names = args.packages
    # Find packages in directory if the single package argument is a directory
    if len(package_file_names) == 1 and os.path.isdir(package_file_names[0]):
        path = package_file_names.pop()
        for root, dirs, files in os.walk(path):
            for file in files:
                if '.json.' not in file and (
                    file.endswith('.tar.bz2') or file.endswith('.conda')
                ):
                    package_file_names.append(os.path.join(root, file))

    if args.verify and not verify_available:
        raise RuntimeError("Cannot verify package: conda-verify is not installed.")

    if args.verify and verify_available:
        verifier = Verify()

        verify_ignore = args.verify_ignore.split(',') if args.verify_ignore else None
        for package in package_file_names:
            verifier.verify_package(
                path_to_package=package,
                checks_to_ignore=verify_ignore,
                exit_on_error=True,
            )

    files = [('files', open(package, 'rb')) for package in package_file_names]

    if args.force:
        files.append(('force', (None, 'true')))

    api_key = get_installed_api_key(channel_url)
    url = f'{channel_url}/files/'
    if args.dry_run:
        package_lines = "\n  ".join(package_file_names)
        print(
            f'QUETZ_API_KEY found: {not not api_key}\n'
            f'URL: {url}\n'
            f'packages:\n  {package_lines} '
        )
    else:
        response = requests.post(url, files=files, headers={'X-API-Key': api_key})

        if response.status_code != 201:
            print(
                'Request failed:\n'
                f'  HTTP status code: {response.status_code}\n'
                f'  Message: {str(response.content.decode("utf-8"))}'
            )
            sys.exit(1)


def main():

    parser = argparse.ArgumentParser()

    subparsers = parser.add_subparsers(
        title='subcommands',
        description='valid subcommands',
        help='additional help',
        dest='cmd',
    )

    upload_parser = subparsers.add_parser(
        'upload',
        usage="%(prog)s channel_url packages",
        description="Uploads package to Quetz.",
    )

    upload_parser.add_argument(
        "--dry-run",
        action='store_true',
        help="Print what would happen, without uploading the package(s)",
    )

    upload_parser.add_argument(
        "--verify", action='store_true', help="Verify package(s) with conda-verify"
    )

    upload_parser.add_argument(
        "--verify-ignore",
        type=str,
        help="Ignore specific checks. Each check must be separated by a single comma",
    )

    upload_parser.add_argument(
        "--force",
        action='store_true',
        help=(
            "Allow overwriting an exiting package version. "
            "(Only allowed with channel owner role)"
        ),
    )

    upload_parser.add_argument("-s", "--server", default="https://beta.mamba.pm")

    upload_parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"quetz-client version {quetz_client.__version__}",
    )

    upload_parser.add_argument("channel")
    upload_parser.add_argument("packages", nargs='+', help="package(s) or build root")

    api_key_parser = subparsers.add_parser(
        'apikey', usage="%(prog)s", description="Obtain an API key from quetz."
    )

    api_key_parser.add_argument("server", nargs='?', default="https://beta.mamba.pm")

    create_channel_parser = subparsers.add_parser(
        'create-channel', usage="%(prog)s", description="Create a channel."
    )

    # create_channel_parser = channel_parser.add_parser(
    #     'create', usage="%(prog)s", description="Create channel."
    # )

    create_channel_parser.add_argument("name")
    create_channel_parser.add_argument(
        "-s", "--server", default="https://beta.mamba.pm"
    )
    create_channel_parser.add_argument("-d", "--description", default="")
    create_channel_parser.add_argument("-p", "--private", action='store_true')

    # This first pass of parsing is used to find one of the allowed subcommands.
    # If there is no subcommand, then "upload" is used by default.
    firstp = argparse.ArgumentParser()
    args, extras = firstp.parse_known_args()

    if extras[0] not in ALLOWED_SUBCOMMANDS:
        extras.insert(0, "upload")

    args = parser.parse_args(extras)

    if args.cmd == 'apikey':
        get_api_key(args)
    elif args.cmd == 'upload':
        return upload_packages(args)
    elif args.cmd == 'create-channel':
        return create_channel(args)
