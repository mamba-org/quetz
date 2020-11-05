from setuptools import setup

setup(
    name="quetz-runexports",
    install_requires="quetz",
    entry_points={"quetz": ["quetz-runexports = quetz_runexports.main"]},
    packages=["quetz_runexports"],
)
