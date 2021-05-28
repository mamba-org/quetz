from setuptools import setup

setup(
    name="quetz-conda_trust",
    install_requires=["quetz", "conda_content_trust"],
    entry_points={
        "quetz": ["quetz-conda_trust = quetz_conda_trust.main"],
        "quetz.migrations": ["quetz-conda_trust = quetz_conda_trust.migrations"],
        "quetz.models": ["quetz-conda_trust = quetz_conda_trust.db_models"],
    },
    packages=[
        "quetz_conda_trust",
        "quetz_conda_trust.migrations",
        "quetz_conda_trust.migrations.versions",
    ],
)
