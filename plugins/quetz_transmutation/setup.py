from setuptools import setup

setup(
    name="quetz-transmutation",
    install_requires="quetz",
    entry_points={
        "quetz": ["quetz-transmutation = quetz_transmutation.main"],
        "quetz.jobs": ["quetz-transmutation = quetz_transmutation.jobs"],
    },
    packages=["quetz_transmutation"],
)
