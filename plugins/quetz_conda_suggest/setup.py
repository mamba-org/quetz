from setuptools import setup

setup(
    name="quetz-conda_suggest",
    install_requires="quetz",
    entry_points={"quetz": ["quetz-conda_suggest = quetz_conda_suggest.main"]},
    packages=["quetz_conda_suggest"],
)
