from setuptools import setup

setup(
    name="quetz-sync",
    install_requires="quetz",
    entry_points={"quetz": ["quetz-sync = quetz-sync"]},
    py_modules=["main"],
)
