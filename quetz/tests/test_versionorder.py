# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

# This code was largely taken from upstream conda
# File: tests/models/test_version.py
# https://github.com/conda/conda/blob/master/tests/models/test_version.py

# Copyright (C) 2012 Anaconda, Inc
# SPDX-License-Identifier: BSD-3-Clause


from copy import copy
from random import shuffle

import pytest

from quetz.dao import Dao
from quetz.rest_models import Channel, Package
from quetz.versionorder import VersionOrder


@pytest.fixture
def package_name():
    return "my-package"


@pytest.fixture
def channel_name():
    return "my-channel"


def test_versionorder():
    versions = [
        ("0.4", [[0], [0], [4]]),
        ("0.4.0", [[0], [0], [4], [0]]),
        ("0.4.1a.vc11", [[0], [0], [4], [1, 'a'], [0, 'vc', 11]]),
        ("0.4.1.rc", [[0], [0], [4], [1], [0, 'rc']]),
        ("0.4.1.vc11", [[0], [0], [4], [1], [0, 'vc', 11]]),
        ("0.4.1", [[0], [0], [4], [1]]),
        ("0.5*", [[0], [0], [5, '*']]),
        ("0.5a1", [[0], [0], [5, 'a', 1]]),
        ("0.5b3", [[0], [0], [5, 'b', 3]]),
        ("0.5C1", [[0], [0], [5, 'c', 1]]),
        ("0.5z", [[0], [0], [5, 'z']]),
        ("0.5za", [[0], [0], [5, 'za']]),
        ("0.5", [[0], [0], [5]]),
        ("0.5_5", [[0], [0], [5], [5]]),
        ("0.5-5", [[0], [0], [5], [5]]),
        ("0.9.6", [[0], [0], [9], [6]]),
        ("0.960923", [[0], [0], [960923]]),
        ("1.0", [[0], [1], [0]]),
        ("1.0.4a3", [[0], [1], [0], [4, 'a', 3]]),
        ("1.0.4b1", [[0], [1], [0], [4, 'b', 1]]),
        ("1.0.4", [[0], [1], [0], [4]]),
        ("1.1dev1", [[0], [1], [1, 'DEV', 1]]),
        ("1.1_", [[0], [1], [1, '_']]),
        ("1.1a1", [[0], [1], [1, 'a', 1]]),
        ("1.1.dev1", [[0], [1], [1], [0, 'DEV', 1]]),
        ("1.1.a1", [[0], [1], [1], [0, 'a', 1]]),
        ("1.1", [[0], [1], [1]]),
        ("1.1.post1", [[0], [1], [1], [0, float('inf'), 1]]),
        ("1.1.1dev1", [[0], [1], [1], [1, 'DEV', 1]]),
        ("1.1.1rc1", [[0], [1], [1], [1, 'rc', 1]]),
        ("1.1.1", [[0], [1], [1], [1]]),
        ("1.1.1post1", [[0], [1], [1], [1, float('inf'), 1]]),
        ("1.1post1", [[0], [1], [1, float('inf'), 1]]),
        ("2g6", [[0], [2, 'g', 6]]),
        ("2.0b1pr0", [[0], [2], [0, 'b', 1, 'pr', 0]]),
        ("2.2be.ta29", [[0], [2], [2, 'be'], [0, 'ta', 29]]),
        ("2.2be5ta29", [[0], [2], [2, 'be', 5, 'ta', 29]]),
        ("2.2beta29", [[0], [2], [2, 'beta', 29]]),
        ("2.2.0.1", [[0], [2], [2], [0], [1]]),
        ("3.1.1.6", [[0], [3], [1], [1], [6]]),
        ("3.2.p.r0", [[0], [3], [2], [0, 'p'], [0, 'r', 0]]),
        ("3.2.pr0", [[0], [3], [2], [0, 'pr', 0]]),
        ("3.2.pr.1", [[0], [3], [2], [0, 'pr'], [1]]),
        ("5.5.kw", [[0], [5], [5], [0, 'kw']]),
        ("11g", [[0], [11, 'g']]),
        ("14.3.1", [[0], [14], [3], [1]]),
        (
            "14.3.1.post26.g9d75ca2",
            [[0], [14], [3], [1], [0, float('inf'), 26], [0, 'g', 9, 'd', 75, 'ca', 2]],
        ),
        ("1996.07.12", [[0], [1996], [7], [12]]),
        ("1!0.4.1", [[1], [0], [4], [1]]),
        ("1!3.1.1.6", [[1], [3], [1], [1], [6]]),
        ("2!0.4.1", [[2], [0], [4], [1]]),
    ]

    # check parser
    versions = [(v, VersionOrder(v), l) for v, l in versions]
    for s, v, l in versions:
        # we don't use caching here
        # assert VersionOrder(v) is v
        assert str(v) == s.lower().replace('-', '_')
        assert v.version == l
    assert VersionOrder("0.4.1.rc") == VersionOrder("  0.4.1.RC  ")
    assert VersionOrder("  0.4.1.RC  ") == VersionOrder("0.4.1.rc")

    for ver in ("", "", "  ", "3.5&1", "5.5++", "5.5..mw", "!", "a!1.0", "a!b!1.0"):
        with pytest.raises(ValueError):
            VersionOrder(ver)

    # check __eq__
    assert VersionOrder("  0.4.rc  ") == VersionOrder("0.4.RC")
    assert VersionOrder("0.4") == VersionOrder("0.4.0")
    assert VersionOrder("0.4") != VersionOrder("0.4.1")
    assert VersionOrder("0.4.a1") == VersionOrder("0.4.0a1")
    assert VersionOrder("0.4.a1") != VersionOrder("0.4.1a1")

    # check __lt__
    assert sorted(versions, key=lambda x: x[1]) == versions

    # check startswith
    assert VersionOrder("0.4.1").startswith(VersionOrder("0"))
    assert VersionOrder("0.4.1").startswith(VersionOrder("0.4"))
    assert VersionOrder("0.4.1p1").startswith(VersionOrder("0.4"))
    assert VersionOrder("0.4.1p1").startswith(VersionOrder("0.4.1p"))
    assert not VersionOrder("0.4.1p1").startswith(VersionOrder("0.4.1q1"))
    assert not VersionOrder("0.4").startswith(VersionOrder("0.4.1"))
    assert VersionOrder("0.4.1+1.3").startswith(VersionOrder("0.4.1"))
    assert VersionOrder("0.4.1+1.3").startswith(VersionOrder("0.4.1+1"))
    assert not VersionOrder("0.4.1").startswith(VersionOrder("0.4.1+1.3"))
    assert not VersionOrder("0.4.1+1").startswith(VersionOrder("0.4.1+1.3"))


def test_openssl_convention():
    openssl = [
        VersionOrder(k)
        for k in (
            '1.0.1dev',
            '1.0.1_',  # <- this
            '1.0.1a',
            '1.0.1b',
            '1.0.1c',
            '1.0.1d',
            '1.0.1r',
            '1.0.1rc',
            '1.0.1rc1',
            '1.0.1rc2',
            '1.0.1s',
            '1.0.1',  # <- compared to this
            '1.0.1post.a',
            '1.0.1post.b',
            '1.0.1post.z',
            '1.0.1post.za',
            '1.0.2',
        )
    ]
    shuffled = copy(openssl)
    shuffle(shuffled)
    assert sorted(shuffled) == openssl


def test_pep440():
    # this list must be in sorted order (slightly modified from the PEP 440 test suite
    # https://github.com/pypa/packaging/blob/master/tests/test_version.py)
    VERSIONS = [
        # Implicit epoch of 0
        "1.0a1",
        "1.0a2.dev456",
        "1.0a12.dev456",
        "1.0a12",
        "1.0b1.dev456",
        "1.0b2",
        "1.0b2.post345.dev456",
        "1.0b2.post345",
        "1.0c1.dev456",
        "1.0c1",
        "1.0c3",
        "1.0rc2",
        "1.0.dev456",
        "1.0",
        "1.0.post456.dev34",
        "1.0.post456",
        "1.1.dev1",
        "1.2.r32+123456",
        "1.2.rev33+123456",
        "1.2+abc",
        "1.2+abc123def",
        "1.2+abc123",
        "1.2+123abc",
        "1.2+123abc456",
        "1.2+1234.abc",
        "1.2+123456",
        # Explicit epoch of 1
        "1!1.0a1",
        "1!1.0a2.dev456",
        "1!1.0a12.dev456",
        "1!1.0a12",
        "1!1.0b1.dev456",
        "1!1.0b2",
        "1!1.0b2.post345.dev456",
        "1!1.0b2.post345",
        "1!1.0c1.dev456",
        "1!1.0c1",
        "1!1.0c3",
        "1!1.0rc2",
        "1!1.0.dev456",
        "1!1.0",
        "1!1.0.post456.dev34",
        "1!1.0.post456",
        "1!1.1.dev1",
        "1!1.2.r32+123456",
        "1!1.2.rev33+123456",
        "1!1.2+abc",
        "1!1.2+abc123def",
        "1!1.2+abc123",
        "1!1.2+123abc",
        "1!1.2+123abc456",
        "1!1.2+1234.abc",
        "1!1.2+123456",
    ]

    version = [VersionOrder(v) for v in VERSIONS]

    vcopy = copy(version)
    shuffle(vcopy)

    assert version == sorted(vcopy)


def test_hexrd():
    VERSIONS = ['0.3.0.dev', '0.3.3']
    vos = [VersionOrder(v) for v in VERSIONS]
    assert sorted(vos) == vos


@pytest.fixture
def package_with_versions(channel_name, package_name, dao, user, db):

    channel_data = Channel(name=channel_name, private=False)
    package_data = Package(name=package_name)

    dao.create_channel(channel_data, user.id, "owner")
    package = dao.create_package(channel_name, package_data, user.id, "owner")
    package_format = "tarbz2"
    package_info = "{}"

    versions = [
        ("0.1.0", 0),
        ("1.0.0", 0),
        ("0.0.1", 0),
        ("0.0.2", 0),
        ("0.0.3", 0),
        ("1.0.0", 1),
        ("1.0.0", 2),
        ("0.1.0", 5),
        ("0.1.0", 2),
    ]
    package_versions = []
    for ver, build_str in versions:
        package_version = dao.create_version(
            channel_name,
            package_name,
            package_format,
            "linux-64",
            ver,
            build_str,
            "",
            f"{package_name}-{ver}-{build_str}.tar.bz2",
            package_info,
            user.id,
            size=0,
        )
        package_versions.append(package_version)

    yield package

    for package_version in package_versions:
        db.delete(package_version)
        db.commit()


def test_package_version(
    db, dao: Dao, channel_name, package_name, package_with_versions
):
    res = dao.get_package_versions(package_with_versions)
    res_versions = [(VersionOrder(x[0].version), x[0].build_number) for x in res]

    assert sorted(res_versions, reverse=True) == res_versions
