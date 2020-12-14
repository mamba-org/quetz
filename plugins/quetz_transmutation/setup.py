from setuptools import setup

setup(
    name="quetz-transmutation",
    install_requires="quetz",
    entry_points={"quetz": ["quetz-transmutation = quetz_transmutation.main"]},
    packages=["quetz_transmutation"],
)
