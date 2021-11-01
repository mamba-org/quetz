from setuptools import setup

setup(
    name="quetz-dictauthenticator",
    install_requires=[],
    entry_points={
        "quetz.authenticator": [
            "dictauthenticator = quetz_dictauthenticator:DictionaryAuthenticator"
        ]
    },
    packages=["quetz_dictauthenticator"],
)
