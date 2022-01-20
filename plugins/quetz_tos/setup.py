from setuptools import setup

setup(
    name="quetz-tos",
    install_requires="quetz-server",
    entry_points={
        "quetz": ["quetz-tos = quetz_tos.main"],
        "quetz.models": ["quetz-tos = quetz_tos.db_models"],
        "quetz.migrations": ["quetz-tos = quetz_tos.migrations"],
    },
    packages=[
        "quetz_tos",
        "quetz_tos.migrations",
        "quetz_tos.migrations.versions",
    ],
)
