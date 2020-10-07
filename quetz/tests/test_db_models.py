"""Tests for the database models"""
# Copyright 2020 QuantStack
# Distributed under the terms of the Modified BSD License.

import uuid

from quetz.db_models import User


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
