from setuptools import setup

setup(
    name="quetz-transmutation",
    install_requires=[],
    version="0.1.0",
    entry_points={
        "quetz.jobs": ["quetz-transmutation = quetz_transmutation.jobs"],
    },
    packages=["quetz_transmutation"],
)
