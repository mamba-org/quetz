from setuptools import setup

setup(
    name="quetz-content_trust",
    install_requires=["conda_content_trust"],
    entry_points={
        "quetz": ["quetz-content_trust = quetz_content_trust.main"],
        "quetz.migrations": ["quetz-content_trust = quetz_content_trust.migrations"],
        "quetz.models": ["quetz-content_trust = quetz_content_trust.db_models"],
    },
    packages=[
        "quetz_content_trust",
        "quetz_content_trust.migrations",
        "quetz_content_trust.migrations.versions",
    ],
)
