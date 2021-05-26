from setuptools import setup

setup(
    name="quetz-conda_trust",
    install_requires=["quetz", "conda_content_trust"],
    entry_points={"quetz": ["quetz-conda_trust = quetz_conda_trust.main"]},
    packages=["quetz_conda_trust"],
)
