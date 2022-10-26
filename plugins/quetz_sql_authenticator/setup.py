# type: ignore

from setuptools import setup

setup(
    name="quetz-sql-authenticator",
    install_requires=["passlib"],
    entry_points={
        "quetz": ["quetz-sql-authenticator = quetz_sql_authenticator.main"],
        "quetz.authenticator": [
            "sql-authenticator = quetz_sql_authenticator.main:SQLAuthenticator"
        ],
        "console_scripts": [
            "quetz-sql-authenticator = quetz_sql_authenticator.cli:_cli"
        ],
        "quetz.migrations": [
            "quetz-sql-authenticator = quetz_sql_authenticator.migrations"
        ],
        "quetz.models": ["quetz-sql-authenticator = quetz_sql_authenticator.db_models"],
    },
    packages=[
        "quetz_sql_authenticator",
        "quetz_sql_authenticator.migrations",
        "quetz_sql_authenticator.migrations.versions",
    ],
)
