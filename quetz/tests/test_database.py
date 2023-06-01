import pytest

from quetz.database import sanitize_db_url


@pytest.mark.parametrize(
    "input_url,expected_output_url",
    (
        (
            "sqlite:///./quetz.sqlite",
            "sqlite:///./quetz.sqlite",
        ),  # No password, no effect
        (
            "postgresql+psycopg2://postgres_user:postgres_password@localhost:5432/postgres",  # noqa: E501
            "postgresql+psycopg2://postgres_user:***@localhost:5432/postgres",
        ),
        ("A:B@C:1111/DB", "A:***@C:1111/DB"),
        ("THISISNOTAURL", "THISISNOTAURL"),
    ),
)
def test_sanitize_db_url(input_url, expected_output_url):
    assert sanitize_db_url(input_url) == expected_output_url
