from setuptools import setup

setup(
    name="quetz-tos",
    install_requires="quetz",
    entry_points={
        "quetz": ["quetz-tos = quetz_tos.main"],
        "quetz.models": ["quetz-tos = quetz_tos.db_models"],
    },
    packages=["quetz_tos"],
)
