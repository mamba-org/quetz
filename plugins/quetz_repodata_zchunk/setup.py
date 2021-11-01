from setuptools import setup

setup(
    name="quetz-repodata_zchunk",
    install_requires=[],
    entry_points={"quetz": ["quetz-repodata_zchunk = quetz_repodata_zchunk.main"]},
    packages=["quetz_repodata_zchunk"],
)
