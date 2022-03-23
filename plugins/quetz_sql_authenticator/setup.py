# type: ignore

from setuptools import setup

setup(
    name="quetz-sql-authenticator",
    install_requires=[
        "sqlmodel"
    ],
    entry_points={
        "quetz.authenticator": [
            "sql-authenticator = quetz_sql_authenticator:SQLAuthenticator"
        ],
        "console_scripts": [
            "quetz-sql-authenticator = quetz_sql_authenticator.cli:_cli"
        ],
    },
    packages=["quetz_sql_authenticator"],
)
