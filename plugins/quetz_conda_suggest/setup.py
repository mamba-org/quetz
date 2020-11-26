from setuptools import setup

setup(
    name="quetz-conda_suggest",
    install_requires="quetz",
    entry_points={
        "quetz": ["quetz-conda_suggest = quetz_conda_suggest.main"],
        "quetz.migrations": ["quetz-conda_suggest = quetz_conda_suggest.migrations"],
        "quetz.models": ["quetz-conda_suggest = quetz_conda_suggest.db_models"],
    },
    packages=[
        "quetz_conda_suggest",
        "quetz_conda_suggest.migrations",
        "quetz_conda_suggest.migrations.versions",
    ],
)
