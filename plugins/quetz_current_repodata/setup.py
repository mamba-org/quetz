from setuptools import setup

setup(
    name="quetz-current_repodata",
    install_requires=[],
    entry_points={"quetz": ["quetz-current_repodata = quetz_current_repodata.main"]},
    packages=["quetz_current_repodata"],
)
