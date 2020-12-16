"""Tests for the database models"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import uuid
from pathlib import Path

import pytest

from quetz.config import Config
from quetz.dao import Dao
from quetz.db_models import PackageVersion, User
from quetz.rest_models import Channel, Package


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
    dao: Dao,
    config: Config,
):
    channel_name = "test-channel"
    package_name = "test-package"
    dao.create_channel(
        Channel(name=channel_name, private=False), user_id=user.id, role="owner"
    )
    dao.create_package(
        channel_name, Package(name=package_name), user_id=user.id, role="owner"
    )

    def factory(version):
        filename = Path(f"test-package-{version}-0.tar.bz2")
        package_format = "tarbz2"
        package_info = "{}"
        package_version = dao.create_version(
            channel_name,
            package_name,
            package_format,
            "linux-64",
            str(version),
            0,
            "",
            str(filename),
            package_info,
            user.id,
            size=11,
        )
        return package_version

    return factory


v = PackageVersion.version


@pytest.mark.parametrize(
    "versions,query,expected_versions",
    [
        (["0.1", "0.2"], v < "0.2", {"0.1"}),
        (["0.11", "0.2"], v < "0.2", set()),
        (["0.2.0", "0.12.0", "1.0.0"], v < "0.2", set()),
        (["0.2.0", "0.12.0", "1.0.0"], v < "0.12", {"0.2.0"}),
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
