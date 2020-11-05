from setuptools import setup

setup(
    name="quetz-repodata_patching",
    install_requires="quetz",
    entry_points={"quetz": ["quetz-repodata_patching = quetz_repodata_patching.main"]},
    packages=["quetz_repodata_patching"],
)
