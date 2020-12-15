from setuptools import setup

setup(
    name="quetz-harvester",
    install_requires="quetz",
    entry_points={"quetz": ["quetz-harvester = quetz_harvester.main"]},
    packages=["quetz_harvester"],
)
