import pytest

from quetz.authentication import auth_dao
from quetz.db_models import Email
from quetz.errors import ValidationError


def find_email(emails, e):
    for eo in emails:
        if eo.email == e:
            return eo
    raise KeyError("Missing email from list")


def test_get_user_by_identity_new_user(dao, config):

    profile = {
        "id": 4567,
        "login": "bartosz",
        "name": "bartosz",
        "avatar_url": "url",
    }
    provider = "github"

    user = auth_dao.get_user_by_identity(dao, provider, profile, config)

    assert user.username == 'bartosz'
    assert user.identities[0].provider == 'github'
    assert user.identities[0].identity_id == '4567'


def test_add_user_with_emails(dao, config):
    profile = {
        "id": 1234,
        "login": "wolfv",
        "name": "wolfv",
        "avatar_url": "url",
        "emails": [
            {"email": "w.vollprecht@abcdef.com", "verified": True, "primary": True},
            {
                "email": "wolf.vollprecht@lasersight.net",
                "verified": False,
                "primary": False,
            },
        ],
    }
    provider = "github"

    user = auth_dao.get_user_by_identity(
        dao, provider=provider, profile=profile, config=config
    )

    assert user.username == "wolfv"
    assert len(user.emails) == 1
    e = find_email(user.emails, "w.vollprecht@abcdef.com")
    assert e.email == "w.vollprecht@abcdef.com"
    assert e.verified is True
    assert e.primary is True

    profile["emails"][1]["verified"] = True

    user = auth_dao.get_user_by_identity(
        dao, provider=provider, profile=profile, config=config
    )

    e = find_email(user.emails, "wolf.vollprecht@lasersight.net")
    assert e.email == "wolf.vollprecht@lasersight.net"

    profile["emails"].append(
        {
            "email": "another.email@github.net",
            "verified": True,
            "primary": False,
        }
    )

    user = auth_dao.get_user_by_identity(
        dao, provider=provider, profile=profile, config=config
    )

    e = find_email(user.emails, "another.email@github.net")
    assert e.email == "another.email@github.net"

    profile["emails"] = profile["emails"][1:]
    profile["emails"][0]["primary"] = True
    profile["login"] = "franky"

    user = auth_dao.get_user_by_identity(
        dao, provider=provider, profile=profile, config=config
    )

    assert len(user.emails) == 2
    # assert user.username == "franky"
    e = find_email(user.emails, "wolf.vollprecht@lasersight.net")
    assert e.email == "wolf.vollprecht@lasersight.net"
    assert e.primary is True

    with pytest.raises(KeyError):
        e = find_email(user.emails, "w.vollprecht@abcdef.com")

    # Make sure that the email is properly deleted
    assert (
        dao.db.query(Email)
        .filter(Email.email == "w.vollprecht@abcdef.com")
        .one_or_none()
        is None
    )


def test_add_user_with_same_email(dao, config):
    profile = {
        "id": 1234,
        "login": "wolfv",
        "name": "wolfv",
        "avatar_url": "url",
        "emails": [
            {"email": "w.vollprecht@abcdef.com", "verified": True, "primary": True},
            {
                "email": "wolf.vollprecht@lasersight.net",
                "verified": True,
                "primary": False,
            },
        ],
    }
    provider = "github"

    profile2 = {
        "id": 1234,
        "login": "gitlab_wolfv",
        "name": "Wolf Vollprecht",
        "avatar_url": "url",
        "emails": [
            {
                "email": "wolf.vollprecht@lasersight.net",
                "verified": True,
                "primary": False,
            },
        ],
    }
    provider2 = "gitlab"

    user = auth_dao.get_user_by_identity(
        dao, provider=provider, profile=profile, config=config
    )

    assert user.username == "wolfv"
    e = find_email(user.emails, "w.vollprecht@abcdef.com")
    assert e.email == "w.vollprecht@abcdef.com"
    assert len(user.emails) == 2
    assert e.verified is True
    assert e.primary is True

    with pytest.raises(ValidationError):
        user = auth_dao.get_user_by_identity(
            dao, provider=provider2, profile=profile2, config=config
        )
