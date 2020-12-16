"""Tests for the database models"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import uuid

import pytest

from quetz.config import Config
from quetz.db_models import Channel, Package, PackageVersion, User


def test_user(db):
    user = User(id=uuid.uuid4().bytes, username='paul')
    db.add(user)
    db.commit()

    assert len(db.query(User).all()) == 1

    found = User.find(db, 'paul')
    assert found.username == user.username
    found = User.find(db, 'dave')
    assert found is None

    db.delete(user)
    db.commit()


@pytest.fixture
def version_factory(
    db,
    user,
    config: Config,
):
    channel_name = "test-channel"
    package_name = "test-package"

    channel = Channel(name=channel_name, private=False)
    package = Package(channel=channel, name=package_name)
    db.add(channel)
    db.add(package)
    db.commit()

    def factory(version):
        filename = f"test-package-{version}-0.tar.bz2"
        package_format = "tarbz2"
        package_info = "{}"
        pver = PackageVersion(
            id=uuid.uuid4().bytes,
            channel_name=channel_name,
            package_name=package_name,
            package_format=package_format,
            platform="linux-64",
            version=str(version),
            build_number=0,
            build_string="0",
            filename=str(filename),
            info=package_info,
            uploader_id=user.id,
            size=11,
        )
        db.add(pver)
        db.commit()

        return pver

    return factory


v = PackageVersion.smart_version


@pytest.mark.parametrize(
    "versions,query,expected_versions",
    [
        (["0.1", "0.2"], v < "0.2", {"0.1"}),
        (["0.11", "0.2"], v < "0.2", set()),
        (["0.2.0", "0.12.0", "1.0.0"], v < "0.2", set()),
        (["0.2.0", "0.12.0", "1.0.0"], v < "0.12", {"0.2.0"}),
        # (["0.2.0.alpha"], v < "0.2.0", {"0.2.0.alpha"}),
    ],
)
def test_package_version_comparison(
    version_factory, db, versions, query, expected_versions
):
    for version in versions:
        version_factory(version)

    packages = db.query(PackageVersion).filter(query).all()

    obtained_versions = {p.version for p in packages}

    assert expected_versions == obtained_versions
